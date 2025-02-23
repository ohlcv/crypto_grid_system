# src/exchange/bitget/bgws_client.py

import json
import threading
from typing import Dict, Optional, List
from decimal import Decimal

from qtpy.QtCore import QTimer

from src.exchange.base_client import BaseWSClient, InstType
from src.exchange.bitget.consts import PRIVATE_WS_URL, PUBLIC_WS_URL
from src.exchange.bitget.ws.bitget_ws_client import BitgetWsClient, SubscribeReq

        
class BGWebSocketClient(BaseWSClient):
    """Bitget WebSocket 客户端封装"""

    def __init__(self, url: str = None, is_private: bool = False,
                 api_key: str = None, api_secret: str = None, passphrase: str = None,
                 inst_type: InstType = None):
        if url is None:
            url = PRIVATE_WS_URL if is_private else PUBLIC_WS_URL
        
        super().__init__(url, is_private)
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.inst_type = inst_type
        self._connect_lock = threading.Lock()
        self._subscriptions = {}

        # 创建 BitgetWsClient 实例
        self._ws_client = BitgetWsClient(url, need_login=is_private)
        
        # 设置认证参数
        if is_private and all([api_key, api_secret, passphrase]):
            self._ws_client.api_key(api_key)
            self._ws_client.api_secret_key(api_secret)
            self._ws_client.passphrase(passphrase)

        # 设置 BitgetWsClient 回调
        self._ws_client.on_open = self._handle_open
        self._ws_client.on_close = self._handle_close
        self._ws_client.on_error = self._handle_error

    def _handle_open(self):
        """处理WebSocket连接打开事件"""
        self._is_connected = True
        print(f"[BGWebSocketClient] {'私有' if self.is_private else '公共'}连接已打开")
        if self.is_private:
            self.private_connected.emit()
        else:
            self.public_connected.emit()

    def _handle_close(self):
        """处理WebSocket连接关闭事件"""
        self._is_connected = False
        print(f"[BGWebSocketClient] {'私有' if self.is_private else '公共'}连接已关闭")
        if self.is_private:
            self.private_disconnected.emit()
        else:
            self.public_disconnected.emit()

    def _handle_error(self, error_msg: str):
        """处理WebSocket错误事件"""
        print(f"[BGWebSocketClient] {'私有' if self.is_private else '公共'}连接错误: {error_msg}")
        self.error.emit(error_msg)
        # 触发断开信号
        self._handle_close()

    def connect(self) -> bool:
        """建立连接"""
        with self._connect_lock:
            if self._ws_client and self._is_connected:
                return True
                
            try:
                if not self._ws_client:
                    self._ws_client = BitgetWsClient(self.url, need_login=self.is_private)
                    if self.is_private and all([self.api_key, self.api_secret, self.passphrase]):
                        self._ws_client.api_key(self.api_key)
                        self._ws_client.api_secret_key(self.api_secret)
                        self._ws_client.passphrase(self.passphrase)

                # 重新设置回调
                self._ws_client.on_open = self._handle_open
                self._ws_client.on_close = self._handle_close
                self._ws_client.on_error = self._handle_error
                self._ws_client.listener(self._handle_message)
                
                # 构建并连接
                self._ws_client.build()
                return True
                
            except Exception as e:
                error_msg = f"连接失败: {str(e)}"
                print(f"[BGWebSocketClient] {error_msg}")
                self.error.emit(error_msg)
                return False

    def disconnect(self) -> bool:
        """断开连接"""
        with self._connect_lock:
            if not self._ws_client:
                return True
                
            try:
                if hasattr(self._ws_client, '_BitgetWsClient__close'):
                    getattr(self._ws_client, '_BitgetWsClient__close')()
                self._ws_client = None
                self._is_connected = False
                return True
                
            except Exception as e:
                error_msg = f"断开连接失败: {str(e)}"
                print(f"[BGWebSocketClient] {error_msg}")
                self.error.emit(error_msg)
                return False

    # 包装方法：调用 BitgetWsClient 的私有 __login
    def _login_wrapper(self):
        try:
            getattr(self._ws_client, '_BitgetWsClient__login')()  # 正确调用私有方法
        except AttributeError as e:
            self._handle_error(f"登录调用失败: {str(e)}")

    # 包装方法：调用 BitgetWsClient 的私有 __close
    def _close_wrapper(self):
        try:
            getattr(self._ws_client, '_BitgetWsClient__close')()  # 正确调用私有方法
        except AttributeError as e:
            self._handle_error(f"关闭调用失败: {str(e)}")

    def _check_connection(self):
        """检查连接状态"""
        if not self._ws_client or not self._is_connected:
            print("[BGWebSocketClient] 连接断开,尝试重连...")
            self.connect()
                
    def subscribe(self, symbol: str = None, channels: List[str] = None, **kwargs) -> bool:
        """订阅频道
        
        Args:
            symbol: 交易对
            channels: 频道列表,如 ["ticker", "depth5", "kline_1m"]
        """
        if not self._ws_client or not self._is_connected:
            return False
            
        try:
            # 规范化交易对格式 (BTC/USDT -> BTCUSDT)
            if "/" in symbol:
                symbol = symbol.replace("/", "")
                
            # 创建订阅请求
            inst_type = kwargs.get("inst_type", "SPOT")
            reqs = []
            for channel in channels:
                req = SubscribeReq(
                    instType=inst_type,
                    channel=channel,
                    instId=symbol
                )
                reqs.append(req)
                
            # 发送订阅
            self._ws_client.subscribe(reqs)
            
            # 记录订阅
            if symbol not in self._subscriptions:
                self._subscriptions[symbol] = []
            self._subscriptions[symbol].extend(channels)
            
            return True
            
        except Exception as e:
            self._handle_error(f"订阅失败 - {symbol} {channels}: {str(e)}")
            return False

    def unsubscribe(self, symbol: str = None, channels: List[str] = None, **kwargs) -> bool:
        """取消订阅"""
        if not self._ws_client:
            return True
            
        try:
            if "/" in symbol:
                symbol = symbol.replace("/", "")
                
            # 创建取消订阅请求
            inst_type = kwargs.get("inst_type", "SPOT")
            reqs = []
            for channel in channels:
                req = SubscribeReq(
                    instType=inst_type,
                    channel=channel,
                    instId=symbol
                )
                reqs.append(req)
                
            # 发送取消订阅
            self._ws_client.unsubscribe(reqs)
            
            # 移除订阅记录
            if symbol in self._subscriptions:
                for channel in channels:
                    if channel in self._subscriptions[symbol]:
                        self._subscriptions[symbol].remove(channel)
                if not self._subscriptions[symbol]:
                    del self._subscriptions[symbol]
                    
            return True
            
        except Exception as e:
            self._handle_error(f"取消订阅失败 - {symbol} {channels}: {str(e)}")
            return False
            
    def _handle_message(self, message: str):
        """处理 WebSocket 消息"""
        try:
            if message == "pong":
                return
                
            data = json.loads(message)
            self.message_received.emit(data)
            
            if "data" in data and "arg" in data:
                arg = data["arg"]
                symbol = arg.get("instId", "")
                channel = arg.get("channel", "")
                
                if channel == "ticker":
                    self.tick_received.emit(symbol, data)
                elif channel == "depth5":
                    self.depth_received.emit(symbol, data)
                elif channel.startswith("candle"):
                    interval = channel.split("_")[1]
                    self.kline_received.emit(symbol, interval, data)
                    
            elif "event" in data and data["event"] == "login":
                if data.get("code") == 0:
                    print("[BGWebSocketClient] 登录成功")
                else:
                    self._handle_error(f"登录失败: {data.get('msg', '未知错误')}")
            elif "topic" in data:
                topic = data["topic"]
                if topic == "orders":
                    order_data = data.get("data", {})
                    order_id = order_data.get("orderId")
                    self.order_updated.emit(order_id, order_data)
                elif topic == "positions":
                    pos_data = data.get("data", {})
                    symbol = pos_data.get("symbol")
                    self.position_updated.emit(symbol, pos_data)
                elif topic == "balance":
                    bal_data = data.get("data", {})
                    asset = bal_data.get("asset")
                    self.balance_updated.emit(asset, bal_data)
                    
        except Exception as e:
            self._handle_error(f"处理消息失败: {str(e)}")