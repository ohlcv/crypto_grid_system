# src/exchange/bitget/bitget_client.py

from decimal import Decimal
import threading
import time
from typing import Dict, Optional, List

from src.exchange.base_client import (
    BaseClient, FillResponse, InstType, OrderRequest, OrderResponse,
    OrderType, OrderSide, TradeSide
)

from src.exchange.bitget.bitget_client.bgapi_client import BitgetAPIClient
from src.exchange.bitget.bitget_client.bgws_client import BGWebSocketClient
from src.utils.logger.log_helper import ws_logger

class BitgetClient(BaseClient):
    """Bitget交易所客户端实现"""

    def __init__(self, api_key: str, api_secret: str, passphrase: str, inst_type: InstType):
        super().__init__(inst_type)
        self.logger = ws_logger
        self.logger.info(f"[{self.inst_type.name}] 开始初始化 {inst_type.value} 客户端")
        
        self.exchange_str = "bitget"
        self.rest_api = BitgetAPIClient(api_key, api_secret, passphrase, inst_type)
        
        self.public_ws = None
        self.private_ws = None
        self._init_websockets(api_key, api_secret, passphrase)
        
        self.logger.info(f"[{self.inst_type.name}] {inst_type.name} 客户端初始化完成")

    def _init_websockets(self, api_key: str, api_secret: str, passphrase: str):
        """初始化WebSocket连接"""
        try:
            self.public_ws = BGWebSocketClient(
                is_private=False,
                inst_type=self.inst_type
            )
            self.private_ws = BGWebSocketClient(
                is_private=True,
                api_key=api_key,
                api_secret=api_secret,
                passphrase=passphrase,
                inst_type=self.inst_type
            )
            self._connect_ws_signals()
            
        except Exception as e:
            self.logger.error(f"[{self.inst_type.name}] WebSocket初始化失败: {e}")
            raise

    def connect(self) -> bool:
        """建立连接"""
        try:
            self.logger.info(f"[{self.inst_type.name}] 开始建立连接")
            public_ok = self.public_ws.connect()
            private_ok = self.private_ws.connect()
            
            if public_ok and private_ok:
                self._connected = True
                self.connection_status.emit(True)
                return True
            return False
            
        except Exception as e:
            self.logger.error(f"[{self.inst_type.name}] 连接失败: {e}")
            self._handle_error("connection", str(e))
            return False

    def disconnect(self) -> bool:
        """断开连接"""
        try:
            if self.public_ws:
                self.public_ws.disconnect()
            if self.private_ws:
                self.private_ws.disconnect()
                
            self._connected = False
            self.connection_status.emit(False)
            return True
            
        except Exception as e:
            self.logger.error(f"断开连接失败: {e}")
            return False

    def _connect_ws_signals(self):
        """连接WebSocket信号"""
        # 公共WS信号
        self.public_ws.connected.connect(self._handle_public_connected)
        self.public_ws.disconnected.connect(self._handle_public_disconnected)
        self.public_ws.error.connect(lambda e: self._handle_error("ws_public", str(e)))

        # 私有WS信号 
        self.private_ws.connected.connect(self._handle_private_connected)
        self.private_ws.disconnected.connect(self._handle_private_disconnected)
        self.private_ws.error.connect(lambda e: self._handle_error("ws_private", str(e)))

        # 公共WS行情数据处理
        self.public_ws.tick_received.connect(self._process_public_tick)  # 直接转发行情
        # 私有WS订单和仓位更新
        self.private_ws.order_updated.connect(self._process_order_update)  # 转发订单更新
        self.private_ws.position_updated.connect(self._process_position_update)  # 转发仓位更新
        self.private_ws.balance_updated.connect(self._process_balance_update)  # 转发余额更新

    def _handle_public_connected(self):
        """处理公共WS连接成功"""
        self.logger.info(f"[{self.inst_type.name}] 公共WebSocket已连接")
        self.public_connected.emit()
        self._check_connection_status()

    def _handle_public_disconnected(self):
        """处理公共WS断开连接"""
        self.logger.info(f"[{self.inst_type.name}] 公共WebSocket已断开")
        self.public_disconnected.emit()
        self._check_connection_status()

    def _handle_private_connected(self):
        """处理私有WS连接成功"""
        self.logger.info(f"[{self.inst_type.name}] 私有WebSocket已连接")
        self.private_connected.emit()
        self._check_connection_status()

    def _handle_private_disconnected(self):
        """处理私有WS断开连接"""
        self.logger.info(f"[{self.inst_type.name}] 私有WebSocket已断开")
        self.private_disconnected.emit()
        self._check_connection_status()

    def _check_connection_status(self):
        """检查整体连接状态"""
        try:
            ws_status = self.get_ws_status()
            current_status = ws_status["public"] and ws_status["private"]
            
            if self._connected != current_status:
                self._connected = current_status
                self.logger.info(f"[{self.inst_type.name}] 连接状态更新: {current_status}")
                self.connection_status.emit(current_status)
                
        except Exception as e:
            self.logger.error(f"[{self.inst_type.name}] 检查连接状态失败: {e}")

    def _handle_error(self, error_type: str, error_message: str):
        """统一错误处理"""
        self.logger.error(f"[{self.inst_type.name}] 错误类型: {error_type} 信息: {error_message}")
        self.error_occurred.emit(f"{error_type}: {error_message}")
        
        # WebSocket错误时检查连接状态
        if error_type.startswith("ws_"):
            self._check_connection_status()

    def update_credentials(self, api_key: str, api_secret: str, passphrase: str):
        """更新API凭证"""
        try:
            self.logger.info("更新API凭证")
            self.disconnect()
            self.rest_api = BitgetAPIClient(api_key, api_secret, passphrase, self.inst_type)
            self._init_websockets(api_key, api_secret, passphrase)
            self.connect()
        except Exception as e:
            self.logger.error(f"更新API凭证失败: {e}")
            raise

    def _process_public_tick(self, symbol: str, data: dict):
        """处理公共行情数据并转发信号"""
        self.tick_received.emit(symbol, data)

    def _process_order_update(self, order_id: str, data: dict):
        self.order_updated.emit(order_id, data)

    def _process_position_update(self, symbol: str, data: dict):
        self.position_updated.emit(symbol, data)

    def _process_balance_update(self, asset: str, data: dict):
        self.balance_updated.emit(asset, data)

    def subscribe_pair(self, pair: str, channels: List[str], strategy_uid: str) -> bool:
        """订阅交易对行情"""
        try:
            self.logger.info(f"订阅行情 - 交易对: {pair} 频道: {channels}")
            
            # 确保WebSocket已连接
            if not self.public_ws or not self.public_ws.is_connected:
                raise RuntimeError("公共WebSocket未连接")
            
            # 规范化交易对格式 (BTC/USDT -> BTCUSDT)
            symbol = pair.replace("/", "").upper()  # 确保调用 upper()
            
            # 发送订阅请求
            return self.public_ws.subscribe(
                symbol=symbol,
                channels=channels,
                inst_type="SPOT" if self.inst_type == InstType.SPOT else "USDT-FUTURES"
            )
            
        except Exception as e:
            self.logger.error(f"订阅行情失败: {e}")
            return False

    def unsubscribe_pair(self, pair: str, channels: List[str], strategy_uid: str) -> bool:
        """取消订阅行情"""
        try:
            self.logger.info(f"取消订阅 - 交易对: {pair} 频道: {channels}")
            
            symbol = pair.replace("/", "").upper()
            return self.public_ws.unsubscribe(
                symbol=symbol,
                channels=channels,
                inst_type="SPOT" if self.inst_type == InstType.SPOT else "USDT-FUTURES"
            )
            
        except Exception as e:
            self.logger.error(f"取消订阅失败: {e}")
            return False

    def update_credentials(self, api_key: str, api_secret: str, passphrase: str):
        """更新API凭证"""
        try:
            self.logger.info("更新API凭证")
            
            # 先断开现有连接
            self.disconnect()
            
            # 更新REST API客户端
            self.rest_api = BitgetAPIClient(
                api_key, api_secret, passphrase, 
                self.inst_type
            )
            
            # 重新初始化WS客户端
            self._init_websockets(api_key, api_secret, passphrase)
            
            # 重新连接
            self.connect()
            
        except Exception as e:
            self.logger.error(f"更新API凭证失败: {e}")
            raise