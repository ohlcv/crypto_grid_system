#!/usr/bin/python
import json
import math
import threading
import time
import traceback
from threading import Timer
from zlib import crc32

import websocket

from ..consts import GET
from .. import consts as c, utils

WS_OP_LOGIN = 'login'
WS_OP_SUBSCRIBE = "subscribe"
WS_OP_UNSUBSCRIBE = "unsubscribe"


def handle(message):
    print("default:" + message)


def handel_error(message):
    print("default_error:" + message)


class BitgetWsClient:

    def __init__(self, url, need_login=False):
        utils.check_none(url, "url")
        self.__need_login = need_login
        self.__connection = False
        self.__login_status = False
        self.__reconnect_status = False
        self.__api_key = None
        self.__api_secret_key = None
        self.__passphrase = None
        self.__all_suribe = set()
        self.__listener = handle
        self.__error_listener = handel_error
        self.__url = url
        self.__scribe_map = {}
        self.__allbooks_map = {}

    def build(self):
        self.__ws_client = self.__init_client()
        __thread = threading.Thread(target=self.connect)
        __thread.start()

        while not self.has_connect():
            print("start connecting... url: ", self.__url)
            time.sleep(1)

        if self.__need_login:
            self.__login()

        self.__keep_connected(25)

        return self

    def get_ws_client(self):
        return self.__ws_client

    def api_key(self, api_key):
        self.__api_key = api_key
        return self

    def api_secret_key(self, api_secret_key):
        self.__api_secret_key = api_secret_key
        return self

    def passphrase(self, passphrase):
        self.__passphrase = passphrase
        return self

    def listener(self, listener):
        self.__listener = listener
        return self

    def error_listener(self, error_listener):
        self.__error_listener = error_listener
        return self

    def has_connect(self):
        print(f"Checking connection status: {self.__connection}")
        return self.__connection

    def __init_client(self):
        try:
            return websocket.WebSocketApp(self.__url,
                                          on_open=self.__on_open,
                                          on_message=self.__on_message,
                                          on_error=self.__on_error,
                                          on_close=self.__on_close)

        except Exception as ex:
            print(ex)

    def __login(self):
        """登录并等待成功"""
        utils.check_none(self.__api_key, "api key")
        utils.check_none(self.__api_secret_key, "api secret key")
        utils.check_none(self.__passphrase, "passphrase")
        timestamp = int(round(time.time()))
        sign = utils.sign(utils.pre_hash(timestamp, GET, c.REQUEST_PATH), self.__api_secret_key)
        if c.SIGN_TYPE == c.RSA:
            sign = utils.signByRSA(utils.pre_hash(timestamp, GET, c.REQUEST_PATH), self.__api_secret_key)
        ws_login_req = WsLoginReq(self.__api_key, self.__passphrase, str(timestamp), sign)
        self.send_message(WS_OP_LOGIN, [ws_login_req])
        print("logging in......")
        start_time = time.time()
        while not self.__login_status:
            time.sleep(0.1)  # 缩短等待时间
            if time.time() - start_time > 5:  # 设置5秒超时
                print("Login timeout")
                break
        print(f"Login status: {self.__login_status}")
        return self.__login_status

    def connect(self):
        try:
            self.__ws_client.run_forever(ping_timeout=10)
        except Exception as ex:
            print(ex)

    def __keep_connected(self, interval):
        try:
            __timer_thread = Timer(interval, self.__keep_connected, (interval,))
            __timer_thread.start()
            self.__ws_client.send("ping")
        except Exception as ex:
            print(ex)

    def send_message(self, op, args):
        # 判断 op 是否为 "login"，如果是，则只打印 "login"
        if op == "login":
            args_dict = [arg.to_dict() if isinstance(arg, SubscribeReq) else arg for arg in args]
            message = json.dumps(BaseWsReq(op, args_dict), default=lambda o: o.__dict__)
            print("send message: login")
        else:
            # 确保 args 中的每个 SubscribeReq 对象都被转换为字典
            args_dict = [arg.to_dict() if isinstance(arg, SubscribeReq) else arg for arg in args]
            # 使用 custom serializer 后再进行 JSON 序列化
            message = json.dumps(BaseWsReq(op, args_dict), default=lambda o: o.__dict__)
            print("send message:" + message)

        self.__ws_client.send(message)

    def subscribe(self, channels, listener=None):

        if listener:
            for chanel in channels:
                chanel.instType = str(chanel.instType)
                self.__scribe_map[chanel] = listener

        for channel in channels:
            self.__all_suribe.add(channel)

        self.send_message(WS_OP_SUBSCRIBE, channels)

    def unsubscribe(self, channels):
        try:
            for chanel in channels:
                if chanel in self.__scribe_map:
                    del self.__scribe_map[chanel]

            for channel in channels:
                if chanel in self.__all_suribe:
                    self.__all_suribe.remove(channel)

            self.send_message(WS_OP_UNSUBSCRIBE, channels)
        except Exception as e:
            pass

    def __on_open(self, ws):
        print('connection is success....')
        self.__connection = True
        # 触发回调
        if hasattr(self, 'on_open') and callable(self.on_open):
            self.on_open()
        self.__reconnect_status = False

    def __on_message(self, ws, message):
        # print(f"[BitgetWsClient] Raw message received: {message}")
        if message == 'pong':
            # print("[BitgetWsClient] Keep connected: pong")
            if self.__listener:
                self.__listener("pong")
            return

        json_obj = json.loads(message)
        # print(f"[BitgetWsClient] Parsed message: {json_obj}")
        
        # 直接传递所有消息给监听器
        if self.__listener:
            self.__listener(message)
            
        # 处理登录消息
        if "event" in json_obj and json_obj.get("event") == "login":
            # print(f"[BitgetWsClient] Login message: {message}")
            self.__login_status = json_obj.get("code") == 0
            return

        # 处理错误消息
        if "code" in json_obj and json_obj.get("code") != 0:
            print(f"[BitgetWsClient] Error message: {message}")
            if self.__error_listener:
                self.__error_listener(message)
            return

        # 更新连接状态
        if not self.__connection:
            self.__connection = True
            print("[BitgetWsClient] Connection established by message")

    def __dict_books_info(self, dict):
        return BooksInfo(dict['asks'], dict['bids'], dict['checksum'])

    def __dict_to_subscribe_req(self, dict):
        # print(f"Creating SubscribeReq with: instId={dict.get('instId')}, coin={dict.get('coin')}")
        if "instId" in dict:
            instId = dict['instId']
            coin = None
            return SubscribeReq(dict['instType'], dict['channel'], dict['instId'])
        elif "coin" in dict:
            instId = None
            coin = dict['coin']
            return SubscribeReq(dict['instType'], dict['channel'], dict['coin'])
        else:
            raise ValueError("You must provide either 'instId' or 'coin', but not both.")
        

    def get_listener(self, json_obj):
        try:
            if json_obj.get('arg'):
                json_str = str(json_obj.get('arg')).replace("\'", "\"")
                subscribe_req = json.loads(json_str, object_hook=self.__dict_to_subscribe_req)
                return self.__scribe_map.get(subscribe_req)
        except Exception as e:
            print(json_obj.get('arg'), e)
            pass

    def __on_error(self, ws, msg):
        print("error:", msg)
        self.__close()
        if not self.__reconnect_status:
            self.__re_connect()

    def __on_close(self, ws, close_status_code, close_msg):
        print("ws is closeing ......close_status:{},close_msg:{}".format(close_status_code, close_msg))
        self.__close()
        if not self.__reconnect_status:
            self.__re_connect()

    def __re_connect(self):
        # 重连
        self.__reconnect_status = True
        print("start reconnection ...")
        self.build()
        for channel in self.__all_suribe :
            self.subscribe([channel])
        pass

    def __close(self):
        self.__login_status = False
        self.__connection = False
        self.__ws_client.close()

    def __check_sum(self, json_obj):
        # noinspection PyBroadException
        try:
            if "arg" not in json_obj or "action" not in json_obj:
                return True
            arg = str(json_obj.get('arg')).replace("\'", "\"")
            action = str(json_obj.get('action')).replace("\'", "\"")
            data = str(json_obj.get('data')).replace("\'", "\"")

            subscribe_req = json.loads(arg, object_hook=self.__dict_to_subscribe_req)

            if subscribe_req.channel != "books":
                return True

            books_info = json.loads(data, object_hook=self.__dict_books_info)[0]

            if action == "snapshot":
                self.__allbooks_map[subscribe_req] = books_info
                return True
            if action == "update":
                all_books = self.__allbooks_map[subscribe_req]
                if all_books is None:
                    return False

                all_books = all_books.merge(books_info)
                check_sum = all_books.check_sum(books_info.checksum)
                if not check_sum:
                    self.unsubscribe([subscribe_req])
                    self.subscribe([subscribe_req])
                    return False
                self.__allbooks_map[subscribe_req] = all_books
        except Exception as e:
            msg = traceback.format_exc()
            print(msg)

        return True


class BooksInfo:
    def __init__(self, asks, bids, checksum):
        self.asks = asks
        self.bids = bids
        self.checksum = checksum

    def merge(self, book_info):
        self.asks = self.innerMerge(self.asks, book_info.asks, False)
        self.bids = self.innerMerge(self.bids, book_info.bids, True)
        return self

    def innerMerge(self, all_list, update_list, is_reverse):
        price_and_value = {}
        for v in all_list:
            price_and_value[v[0]] = v

        for v in update_list:
            if v[1] == "0":
                del price_and_value[v[0]]
                continue
            price_and_value[v[0]] = v

        keys = sorted(price_and_value.keys(), reverse=is_reverse)

        result = []

        for i in keys:
            result.append(price_and_value[i])

        return result

    def check_sum(self, new_check_sum):
        crc32str = ''
        for x in range(25):
            if self.bids[x] is not None:
                crc32str = crc32str + self.bids[x][0] + ":" + self.bids[x][1] + ":"

            if self.asks[x] is not None:
                crc32str = crc32str + self.asks[x][0] + ":" + self.asks[x][1] + ":"

        crc32str = crc32str[0:len(crc32str) - 1]
        print(crc32str)
        merge_num = crc32(bytes(crc32str, encoding="utf8"))
        print("start checknum mergeVal:" + str(merge_num) + ",checkVal:" + str(new_check_sum)+",checkSin:"+str(self.__signed_int(merge_num)))
        return self.__signed_int(merge_num) == new_check_sum

    def __signed_int(self, checknum):
        int_max = math.pow(2, 31) - 1
        if checknum > int_max:
            return checknum - int_max * 2 - 2
        return checknum


class SubscribeReq:
    def __init__(self, instType, channel, instId=None, coin=None):
        if (instId is None) == (coin is None):  # 确保 instId 和 coin 只能有一个被赋值
            raise ValueError("You must provide exactly one of 'instId' or 'coin', but not both.")
        
        self.instType = instType
        self.channel = channel
        self.instId = instId
        self.coin = coin

    def __eq__(self, other) -> bool:
        return self.__dict__ == other.__dict__

    def __hash__(self) -> int:
        if self.coin is not None:
            return hash(self.instType + self.channel + self.coin)
        else:
            return hash(self.instType + self.channel + self.instId)

    def __str__(self) -> str:
        """返回对象的字符串表示"""
        return f"SubscribeReq(instType={self.instType}, channel={self.channel}, " \
               f"instId={self.instId if self.instId else 'None'}, coin={self.coin if self.coin else 'None'})"

    def to_dict(self):
        """返回对象的字典表示，方便序列化"""
        data = {
            "instType": self.instType,
            "channel": self.channel,
            "instId": self.instId,
            "coin": self.coin
        }

        # 移除 null (None) 值
        if self.instId is None:
            del data['instId']
        if self.coin is None:
            del data['coin']
        
        return data


class BaseWsReq:

    def __init__(self, op, args):
        self.op = op
        self.args = args


class WsLoginReq:

    def __init__(self, api_key, passphrase, timestamp, sign):
        self.api_key = api_key
        self.passphrase = passphrase
        self.timestamp = timestamp
        self.sign = sign
