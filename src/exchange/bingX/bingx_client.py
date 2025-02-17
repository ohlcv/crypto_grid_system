# src/exchange/bingx/bingx_client.py

"""
BingX交易所客户端实现，继承BaseClient基类
"""

import time
import traceback
from typing import Dict, List, Optional
from decimal import Decimal
from qtpy.QtCore import Qt
import threading
from src.exchange.base_client import (
    BaseClient, ExchangeType, OrderRequest, OrderType,
    OrderSide, TradeSide
)
from .bingx_rest_api import BingXRestAPI
from .websocket.bingx_ws_client import BingXWebSocketClient
from .exceptions import BingXAPIException

class BingXClient(BaseClient):
    """BingX交易所客户端"""

    def __init__(self, api_key: str, api_secret: str, passphrase: str, inst_type: ExchangeType):
        """初始化BingX客户端
        
        Args:
            api_key: API密钥
            api_secret: API密钥
            passphrase: API密码
            inst_type: 交易类型(现货/合约)
        """
        super().__init__(inst_type)
        self._api_key = api_key
        self._api_secret = api_secret
        self._passphrase = passphrase
        self._connected = False
        self._lock = threading.Lock()
        self.exchange = "bingx"

        # 初始化REST API客户端
        self.rest_api = BingXRestAPI(
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase,
            is_spot=(inst_type == ExchangeType.SPOT)
        )

        # 初始化WebSocket客户端
        self._public_ws = BingXWebSocketClient(is_private=False)
        self._private_ws = BingXWebSocketClient(
            is_private=True,
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase
        )

        # 连接WebSocket信号
        self._connect_ws_signals()

    def _connect_ws_signals(self):
        """连接WebSocket信号"""
        # 公共WebSocket信号
        self._public_ws.message_received.connect(self._handle_public_message)
        self._public_ws.error.connect(lambda e: self._handle_error("ws_public", e))
        self._public_ws.connected.connect(self._handle_public_connected)
        self._public_ws.disconnected.connect(self._handle_public_disconnected)

        # 私有WebSocket信号
        self._private_ws.message_received.connect(self._handle_private_message)
        self._private_ws.error.connect(lambda e: self._handle_error("ws_private", e))
        self._private_ws.connected.connect(self._handle_private_connected)
        self._private_ws.disconnected.connect(self._handle_private_disconnected)

    def connect(self) -> bool:
        """建立连接"""
        try:
            # 启动WebSocket连接
            self._public_ws.connect()
            self._private_ws.connect()
            return True
        except Exception as e:
            self.logger.error(f"连接失败: {e}")
            self._handle_error("connection", str(e))
            return False

    def disconnect(self) -> bool:
        """断开连接"""
        try:
            self._public_ws.disconnect()
            self._private_ws.disconnect()
            self._connected = False
            return True
        except Exception as e:
            self.logger.error(f"断开连接失败: {e}")
            return False

    def get_ws_status(self) -> Dict[str, bool]:
        """获取WebSocket连接状态"""
        return {
            "public": self._public_ws.is_connected,
            "private": self._private_ws.is_connected
        }

    def subscribe_pair(self, pair: str, channels: List[str], strategy_uid: str) -> bool:
        """订阅交易对数据
        
        Args:
            pair: 交易对名称
            channels: 频道列表
            strategy_uid: 策略ID
            
        Returns:
            是否订阅成功
        """
        try:
            pair = pair.replace('/', '')
            for channel in channels:
                self._public_ws.subscribe(channel, pair)
            return True
        except Exception as e:
            self.logger.error(f"订阅失败: {e}")
            return False

    def unsubscribe_pair(self, pair: str, channels: List[str], strategy_uid: str) -> bool:
        """取消订阅
        
        Args:
            pair: 交易对名称
            channels: 频道列表
            strategy_uid: 策略ID
            
        Returns:
            是否取消成功
        """
        try:
            pair = pair.replace('/', '')
            for channel in channels:
                self._public_ws.unsubscribe(channel, pair)
            return True
        except Exception as e:
            self.logger.error(f"取消订阅失败: {e}")
            return False

    def _handle_public_message(self, message: dict):
        """处理公共WebSocket消息"""
        try:
            if message.get("channel") == "ticker":
                pair = message.get("symbol")
                data = message.get("data")
                if pair and data:
                    self.tick_received.emit(pair, data)
        except Exception as e:
            self.logger.error(f"处理公共消息错误: {e}")

    def _handle_private_message(self, message: dict):
        """处理私有WebSocket消息"""
        try:
            if message.get("channel") == "orders":
                order_data = message.get("data")
                if order_data:
                    client_oid = order_data.get("clientOrderId", "")
                    self.order_updated.emit(client_oid, order_data)
        except Exception as e:
            self.logger.error(f"处理私有消息错误: {e}")

    def _handle_public_connected(self):
        """处理公共WS连接成功"""
        self._check_connection_status()

    def _handle_private_connected(self):
        """处理私有WS连接成功"""
        self._check_connection_status()

    def _handle_public_disconnected(self):
        """处理公共WS断开连接"""
        self._check_connection_status()

    def _handle_private_disconnected(self):
        """处理私有WS断开连接"""
        self._check_connection_status()

    def _check_connection_status(self):
        """检查连接状态"""
        current_status = self.is_connected
        if self._connected != current_status:
            self._connected = current_status
            if current_status:
                self.connected.emit()
            else:
                self.disconnected.emit()
            self.connection_status.emit(current_status)

    def _handle_error(self, error_type: str, error_message: str):
        """处理错误"""
        self.error_occurred.emit(f"{error_type} error: {error_message}")

    def place_order(self, request: OrderRequest) -> bool:
        """下单
        
        Args:
            request: 订单请求
            
        Returns:
            是否下单成功
        """
        try:
            # 转换订单参数
            side = "buy" if request.side == OrderSide.BUY else "sell"
            order_type = "market" if request.order_type == OrderType.MARKET else "limit"
            
            response = self.rest_api.place_order(
                symbol=request.symbol.replace('/', ''),
                side=side,
                order_type=order_type,
                quantity=request.volume,
                price=request.price,
                client_order_id=request.client_order_id
            )
            return True
        except BingXAPIException as e:
            self.logger.error(f"下单失败: {e}")
            return False

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        """撤单
        
        Args:
            order_id: 订单ID
            symbol: 交易对
            
        Returns:
            是否撤单成功
        """
        try:
            self.rest_api.cancel_order(
                symbol=symbol.replace('/', ''),
                order_id=order_id
            )
            return True
        except BingXAPIException as e:
            self.logger.error(f"撤单失败: {e}")
            return False