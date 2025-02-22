from decimal import Decimal
import threading
import time
from typing import Dict, List, Optional
import json

from qtpy.QtCore import Signal
from src.exchange.base_client import BaseClient, InstType, OrderRequest, OrderResponse, PositionSide, WSRequest, OrderType, OrderSide, TradeSide
from src.utils.logger.log_helper import ws_logger, api_logger

# 导入官方 SDK 的 API 类
from src.exchange.bitget.v2.spot.account_api import AccountApi as SpotAccountApi
from src.exchange.bitget.v2.spot.market_api import MarketApi as SpotMarketApi
from src.exchange.bitget.v2.spot.order_api import SpotOrderApi
from src.exchange.bitget.v2.mix.account_api import AccountApi as MixAccountApi
from src.exchange.bitget.v2.mix.market_api import MarketApi as MixMarketApi
from src.exchange.bitget.v2.mix.order_api import MixOrderApi

# 导入 WebSocket 客户端
from src.exchange.bitget.ws.bitget_ws_client import BitgetWsClient, SubscribeReq

class BitgetClient(BaseClient):
    """Bitget交易所客户端实现"""
    
    def __init__(self, api_key: str, api_secret: str, passphrase: str, inst_type: InstType):
        super().__init__(inst_type)
        self.logger = ws_logger
        self.api_logger = api_logger
        
        self.logger.info(f"开始初始化 {inst_type.value} 客户端")
        
        # API认证信息
        self._api_key = api_key
        self._api_secret = api_secret
        self._passphrase = passphrase
        self.exchange = "bitget"
        
        # 初始化 REST API 客户端
        if inst_type == InstType.SPOT:
            self.account_api = SpotAccountApi(api_key, api_secret, passphrase)
            self.market_api = SpotMarketApi(api_key, api_secret, passphrase)
            self.order_api = SpotOrderApi(api_key, api_secret, passphrase)
        else:
            self.account_api = MixAccountApi(api_key, api_secret, passphrase)
            self.market_api = MixMarketApi(api_key, api_secret, passphrase)
            self.order_api = MixOrderApi(api_key, api_secret, passphrase)

        # 初始化 WebSocket 客户端
        self._public_ws = BitgetWsClient("wss://ws.bitget.com/v2/ws/public", need_login=False)
        self._private_ws = BitgetWsClient("wss://ws.bitget.com/v2/ws/private", need_login=True)
        self._private_ws.api_key(api_key).api_secret_key(api_secret).passphrase(passphrase)
        
        # 连接 WebSocket 信号
        self._public_ws.listener(self._handle_public_message)
        self._public_ws.error_listener(self._handle_error)
        self._private_ws.listener(self._handle_private_message)
        self._private_ws.error_listener(self._handle_error)
        
        self.logger.info(f"{inst_type.name} 客户端初始化完成")

    def connect(self, wait: bool = True) -> bool:
        """建立连接"""
        try:
            self.logger.info(f"{self.inst_type.name} 开始连接")
            
            def start_connections():
                self._public_ws.build()
                self._private_ws.build()
                
            if not wait:
                threading.Thread(
                    target=start_connections,
                    name=f"WebSocket-{self.inst_type.name}-Connect-{id(self)}",
                    daemon=True
                ).start()
                return True
                
            start_connections()
            return True
            
        except Exception as e:
            self.logger.error("连接失败", exc_info=e)
            self._handle_error("connection", str(e))
            return False

    def disconnect(self) -> bool:
        """断开连接"""
        try:
            self._public_ws.close()
            self._private_ws.close()
            self._connected = False
            self.logger.info(f"{self.inst_type.name} 连接已断开")
            return True
        except Exception as e:
            self.logger.error(f"断开连接失败: {e}")
            return False

    def _handle_public_message(self, message: str):
        """处理公共WebSocket消息"""
        try:
            data = json.loads(message)
            if "event" in data:
                return
            channel = data.get("arg", {}).get("channel")
            if channel == "ticker":
                pair = data.get("arg", {}).get("instId")
                tick_data = data.get("data", [{}])[0]
                if pair and tick_data:
                    self.tick_received.emit(pair, tick_data)
        except Exception as e:
            self.logger.error(f"处理公共消息错误: {e}")

    def _handle_private_message(self, message: str):
        """处理私有WebSocket消息"""
        try:
            data = json.loads(message)
            if "event" in data and data["event"] == "login":
                if data.get("code") == 0:
                    self.logger.info("私有WebSocket登录成功")
                return
            if "arg" in data and data["arg"].get("channel") == "orders":
                order_data = data.get("data", [{}])[0]
                if order_data:
                    self.order_updated.emit(order_data.get("clientOid", ""), order_data)
        except Exception as e:
            self.logger.error(f"处理私有消息错误: {e}")

    def _handle_error(self, error: str):
        """处理WebSocket错误"""
        self.logger.error(f"WebSocket错误: {error}")
        self.error_occurred.emit(error)

    def subscribe_pair(self, pair: str, channels: List[str], strategy_uid: str) -> bool:
        """订阅交易对行情"""
        try:
            inst_type_str = "SPOT" if self.inst_type == InstType.SPOT else "USDT-FUTURES"
            symbol = pair.replace("/", "")
            for channel in channels:
                subscribe_req = SubscribeReq(instType=inst_type_str, channel=channel, instId=symbol)
                self._public_ws.subscribe([subscribe_req])
            self.logger.info(f"订阅行情 - 交易对:{symbol} 频道:{channels} 策略:{strategy_uid}")
            return True
        except Exception as e:
            self.logger.error(f"订阅失败: {e}")
            return False

    def unsubscribe_pair(self, pair: str, channels: List[str], strategy_uid: str) -> bool:
        """取消订阅交易对行情"""
        try:
            inst_type_str = "SPOT" if self.inst_type == InstType.SPOT else "USDT-FUTURES"
            symbol = pair.replace("/", "")
            for channel in channels:
                subscribe_req = SubscribeReq(instType=inst_type_str, channel=channel, instId=symbol)
                self._public_ws.unsubscribe([subscribe_req])
            self.logger.info(f"取消订阅 - 交易对:{symbol} 频道:{channels} 策略:{strategy_uid}")
            return True
        except Exception as e:
            self.logger.error(f"取消订阅失败: {e}")
            return False

    def place_order(self, request: OrderRequest) -> OrderResponse:
        try:
            params = {
                "symbol": request.symbol.replace("/", ""),
                "orderType": request.order_type.value,
            }
            if request.inst_type == InstType.FUTURES:
                if not request.position_side:
                    raise ValueError("合约订单必须提供 position_side")
                side = "buy" if request.position_side == PositionSide.LONG else "sell"
                params.update({
                    "size": str(request.volume),
                    "side": side,
                    "tradeSide": request.trade_side.value,
                    "productType": "USDT-FUTURES",
                    "marginMode": "crossed",
                    "marginCoin": "USDT",
                })
            else:
                if request.order_type == OrderType.MARKET:
                    if request.side == OrderSide.BUY:
                        size = str(request.quote_amount) if request.quote_amount else str(request.volume * request.base_price)
                    else:
                        size = str(request.volume) if request.volume else str(request.quote_amount / request.base_price)
                else:
                    size = str(request.volume) if request.volume else str(request.quote_amount / request.base_price)
                params.update({
                    "size": size,
                    "side": request.side.value,
                })
            if request.order_type == OrderType.LIMIT:
                params["price"] = str(request.price)
            if request.client_order_id:
                params["clientOid"] = request.client_order_id

            response = self.order_api.placeOrder(params)
            if response.get('code') != '00000':
                return OrderResponse(status='failed', error_message=response.get('msg'), order_id='', side=request.side, trade_side=request.trade_side)
            order_id = response['data']['orderId']
            return OrderResponse(status='success', order_id=order_id, side=request.side, trade_side=request.trade_side)
        except Exception as e:
            self.logger.error(f"下单失败: {e}")
            return OrderResponse(status='failed', error_message=str(e), order_id='', side=request.side, trade_side=request.trade_side)

    def get_fills(self, symbol: str, order_id: str) -> List[OrderResponse]:
        try:
            params = {"symbol": symbol.replace("/", ""), "orderId": order_id}
            fills = self.order_api.fills(params)
            if fills.get('code') != '00000':
                self.logger.warning(f"获取成交记录失败: {fills.get('msg')}")
                return []
            fill_list = fills.get('data', [])
            result = []
            for fill in fill_list:
                side = OrderSide(fill.get('side', '').lower())
                trade_side = TradeSide(fill.get('tradeSide', '').lower()) if 'tradeSide' in fill else None
                filled_amount = Decimal(fill.get('size', '0')) if self.inst_type == InstType.SPOT else Decimal(fill.get('baseVolume', '0'))
                filled_price = Decimal(fill.get('priceAvg', '0')) if self.inst_type == InstType.SPOT else Decimal(fill.get('price', '0'))
                filled_value = Decimal(fill.get('amount', '0')) if self.inst_type == InstType.SPOT else Decimal(fill.get('quoteVolume', '0'))
                fee = Decimal(fill.get('feeDetail', {}).get('totalFee', '0'))
                resp = OrderResponse(
                    status='success',
                    order_id=order_id,
                    side=side,
                    trade_side=trade_side,
                    filled_amount=filled_amount,
                    filled_price=filled_price,
                    filled_value=filled_value,
                    fee=fee,
                )
                result.append(resp)
            return result
        except Exception as e:
            self.logger.error(f"获取成交记录失败: {e}")
            return []