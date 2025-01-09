# src/exchange/bitget/bitget_client.py

from dataclasses import dataclass, field
import threading
import traceback
from typing import Dict, Optional, List, Set
from decimal import Decimal
from qtpy.QtCore import Signal
from qtpy.QtWidgets import QMessageBox
from qtpy.QtWidgets import QApplication
from src.exchange.bitget.v2.bg_v2_api import BitgetMixAPI, BitgetSpotAPI
from src.exchange.bitget.v2.mix.order_api import MixOrderApi
from src.exchange.bitget.v2.spot.order_api import SpotOrderApi
from src.exchange.bitget.websocket.bgws_client import BGWebSocketClient
from ..base_client import BaseClient, ExchangeType, OrderRequest, OrderResponse, WSRequest
from src.utils.logger.log_helper import ws_logger, api_logger


class SubscriptionManager:
    """订阅管理器"""
    def __init__(self):
        self._subscriptions: Dict[str, Set[str]] = {}  # pair -> set of strategy_uids
        self._valid_pairs: Set[str] = set()  # 有效的交易对集合
        self._lock = threading.Lock()

    def add_valid_pair(self, pair: str):
        """添加有效的交易对"""
        with self._lock:
            self._valid_pairs.add(pair)

    def is_valid_pair(self, pair: str) -> bool:
        """检查交易对是否有效"""
        return pair in self._valid_pairs

    def subscribe(self, pair: str, channel: str, strategy_uid: str) -> bool:
        """添加策略订阅"""
        with self._lock:
            print(f"[SubscriptionManager] 添加订阅 - 交易对: {pair}, 频道: {channel}, 策略: {strategy_uid}")
            if pair not in self._subscriptions:
                self._subscriptions[pair] = {}
            if channel not in self._subscriptions[pair]:
                self._subscriptions[pair][channel] = set()
            self._subscriptions[pair][channel].add(strategy_uid)
            self._print_subscriptions()
            return True

    def unsubscribe(self, pair: str, channel: str, strategy_uid: str) -> bool:
        """移除策略订阅"""
        with self._lock:
            print(f"[SubscriptionManager] 移除订阅 - 交易对: {pair}, 频道: {channel}, 策略: {strategy_uid}")
            if pair in self._subscriptions and channel in self._subscriptions[pair]:
                self._subscriptions[pair][channel].discard(strategy_uid)
                # 如果该频道没有订阅者，删除频道
                if not self._subscriptions[pair][channel]:
                    del self._subscriptions[pair][channel]
                # 如果该交易对没有任何频道订阅，删除交易对
                if not self._subscriptions[pair]:
                    del self._subscriptions[pair]
                self._print_subscriptions()
                return True
            return False

    def get_subscribers(self, pair: str, channel: str) -> Set[str]:
        """获取特定频道的所有订阅策略"""
        with self._lock:
            return self._subscriptions.get(pair, {}).get(channel, set()).copy()

    def has_subscribers(self, pair: str, channel: str) -> bool:
        """检查特定频道是否有订阅者"""
        with self._lock:
            return pair in self._subscriptions and channel in self._subscriptions[pair] and bool(self._subscriptions[pair][channel])

    def _print_subscriptions(self):
        """打印当前所有订阅信息"""
        print("\n[SubscriptionManager] === 当前订阅信息 ===")
        for pair, channels in self._subscriptions.items():
            print(f"交易对: {pair}")
            for channel, subscribers in channels.items():
                print(f"  频道: {channel}")
                print(f"  订阅策略: {subscribers}")
        print("=== 订阅信息结束 ===\n")

class BitgetClient(BaseClient):
    error = Signal(str)
    private_ws_connected = Signal()

    def __init__(self, api_key: str, api_secret: str, passphrase: str, inst_type: ExchangeType):
        super().__init__(inst_type)
        self._api_key = api_key
        self._api_secret = api_secret
        self._passphrase = passphrase
        self._connected = False
        self._subscriptions = set()  # 保存订阅信息
        self._subscription_manager = SubscriptionManager()

        # 创建WebSocket客户端
        self._public_ws = BGWebSocketClient(is_private=False)
        self._private_ws = BGWebSocketClient(
            is_private=True,
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase
        )

        # 创建REST API客户端
        if inst_type == ExchangeType.SPOT:
            self.rest_api = BitgetSpotAPI(api_key, api_secret, passphrase)
        else:
            self.rest_api = BitgetMixAPI(api_key, api_secret, passphrase)

        self.logger = ws_logger
        self.api_logger = api_logger
        self.logger.info(f"初始化Bitget客户端 - {inst_type.value}")

        # 连接信号
        self._connect_signals()
        self._load_valid_pair()

    def _load_valid_pair(self):
        """加载所有有效的交易对"""
        try:
            print("[BitgetClient] 调用交易所API获取所有交易对列表: ")
            response = self.rest_api.get_pairs()
            if response.get('code') == '00000':
                pair = response.get('data', [])
                for pair_info in pair:
                    self._subscription_manager.add_valid_pair(pair_info['symbol'])
                print(f"[BitgetClient] 加载了 {len(pair)} 个有效交易对")
        except Exception as e:
            print(f"[BitgetClient] 加载交易对失败: {e}")

    def _handle_private_connected(self):
        """处理私有WS连接成功"""
        print("=== 私有WebSocket连接成功 ===")
        print(f"Current connection status: public={self._public_ws.is_connected}, private={self._private_ws.is_connected}")
        self._check_connection_status()
        # 发送私有WebSocket连接成功信号
        self.private_ws_connected.emit()

    def _connect_signals(self):
        """连接WebSocket信号"""
        print("[BitgetClient] Connecting public WebSocket signals")
        self._public_ws.message_received.connect(self._handle_public_message)
        self._public_ws.error.connect(lambda e: self._handle_error("ws_public", e))
        self._public_ws.connected.connect(self._handle_public_connected)
        self._public_ws.disconnected.connect(self._handle_public_disconnected)

        print("[BitgetClient] Connecting private WebSocket signals")
        self._private_ws.message_received.connect(self._handle_private_message)
        self._private_ws.error.connect(lambda e: self._handle_error("ws_private", e))
        self._private_ws.connected.connect(self._handle_private_connected)  # 更改为新的处理方法
        self._private_ws.disconnected.connect(self._handle_private_disconnected)

    def _handle_public_connected(self):
        """处理公共WS连接成功"""
        print("=== 公共WebSocket连接成功 ===")
        print(f"Current connection status: public={self._public_ws.is_connected}, private={self._private_ws.is_connected}")
        self._check_connection_status()

    def _handle_private_connected(self):
        """处理私有WS连接成功"""
        # print("=== 私有WebSocket连接成功 ===")
        # print(f"Current connection status: public={self._public_ws.is_connected}, private={self._private_ws.is_connected}")
        self._check_connection_status()

    def _handle_public_disconnected(self):
        """处理公共WS断开连接"""
        # print("=== Public WebSocket Disconnected ===")
        # print(f"Current connection status: public={self._public_ws.is_connected}, private={self._private_ws.is_connected}")
        self._check_connection_status()

    def _handle_private_disconnected(self):
        """处理私有WS断开连接"""
        # print("=== Private WebSocket Disconnected ===")
        # print(f"Current connection status: public={self._public_ws.is_connected}, private={self._private_ws.is_connected}")
        self._check_connection_status()

    def _check_connection_status(self):
        """检查连接状态"""
        current_status = self.is_connected
        if self._connected != current_status:
            print(f"[BitgetClient] === 连接状态变化 ===")
            print(f"[BitgetClient] 之前状态: {self._connected}")
            print(f"[BitgetClient] 当前状态: {current_status}")
            
            self._connected = current_status
            # 发送状态变化信号
            if current_status:
                self.connected.emit()
            else:
                self.disconnected.emit()
            self.connection_status.emit(current_status)
            print("[BitgetClient] Emitted connection_status signal")

    def check_pair_valid(self, pair: str) -> bool:
        """检查交易对是否有效"""
        pair = pair.replace('/', '').replace('-', '')  # 删除 '/' 和 '-'
        return self._subscription_manager.is_valid_pair(pair)

    def _handle_public_message(self, message: dict):
        """处理公共WebSocket消息"""
        # print(f"[BitgetClient] 处理公共WebSocket消息: {message}")
        try:
            if message.get("type") == "event":
                return
            channel = message.get("channel")
            if channel == "ticker":
                pair = message.get("symbol")
                data = message.get("data")
                if pair and data:
                    # 减少打印，提高性能
                    self.tick_received.emit(pair, data)
        except Exception as e:
            print(f"[BitgetClient] 处理消息错误: {e}")

    def _handle_private_message(self, message: dict):
        """处理私有WebSocket消息"""
        print(f"收到私有消息: {message}")
        if message.get("channel") == "orders":
            order_data = message.get("data")
            if order_data:
                print(f"发送订单更新 - clientOid: {order_data.get('clientOid', '')}")
                self.order_updated.emit(
                    order_data.get("clientOid", ""),
                    order_data
                )

    def _resubscribe_all(self):
        """重新订阅所有频道"""
        print("=== 开始重新订阅 ===")
        print(f"订阅列表: {self._subscriptions}")
        for pair, channel in self._subscriptions:
            try:
                self.subscribe_pair(pair, [channel])
                print(f"重新订阅: {pair} - {channel}")
            except Exception as e:
                print(f"重新订阅失败 {pair} - {channel}: {str(e)}")

    def connect(self):
        """建立连接"""
        try:
            print(f"\n=== BitgetClient 开始连接 ===")
            # print(f"[BitgetClient] Public WS URL: {self._public_ws._url}")
            # print(f"[BitgetClient] Private WS URL: {self._private_ws._url}")
            
            print(f"[BitgetClient] 准备连接公共WS...")
            # 连接客户端状态变化信号
            self._public_ws.connected.connect(self._handle_public_connected)
            self._public_ws.disconnected.connect(self._handle_public_disconnected)
            self._public_ws.connect()
            self.logger.info(f"[BitgetClient] 公共WS连接已连接")
            
            print(f"[BitgetClient] 准备连接私有WS...")
            # 连接客户端状态变化信号
            self._private_ws.connected.connect(self._handle_private_connected)
            self._private_ws.disconnected.connect(self._handle_private_disconnected)
            self._private_ws.connect()
            self.logger.info(f"[BitgetClient] 私有WS连接已连接")

            return True
        except Exception as e:
            self.logger.error("WebSocket连接失败", exc_info=e)
            self._handle_error("connection", str(e))
            return False

    def disconnect(self) -> bool:
        """断开连接"""
        # print("[BitgetClient] BitgetClient开始断开连接")
        # try:
        # 先断开私有WebSocket
        if self._private_ws:
            self._private_ws.disconnect()
            print("[BitgetClient] 断开私有WebSocket")
        
        # 再断开公共WebSocket
        if self._public_ws:
            self._public_ws.disconnect()
            print("[BitgetClient] 断开公共WebSocket")
        
        # 更新状态
        self._connected = False
        print("[BitgetClient] BitgetClient连接已断开")
        return True

    def get_ws_status(self) -> Dict[str, bool]:
        status = {
            "public": (self._public_ws and self._public_ws.is_connected),
            "private": (self._private_ws and self._private_ws.is_connected 
                        and getattr(self._private_ws, '_login_status', False))
        }
        print(f"[BitgetClient] Current WS Status - public: {status['public']}, private: {status['private']}")
        return status

    def subscribe_pair(self, pair: str, channels: List[str], strategy_uid: str) -> bool:
        """订阅交易对"""
        try:
            inst_type = "SPOT" if self.inst_type == ExchangeType.SPOT else "USDT-FUTURES"
            pair = pair.replace('/', '')
            
            print(f"[BitgetClient] === 订阅交易对 ===")
            print(f"交易对: {pair}")
            print(f"频道: {channels}")
            print(f"策略ID: {strategy_uid}")
            
            # 添加策略订阅
            for channel in channels:
                if not self._subscription_manager.subscribe(pair, channel, strategy_uid):
                    return False
                
                # 如果这个频道之前没有订阅过，发送WebSocket订阅请求
                request = WSRequest(channel=channel, pair=pair, inst_type=inst_type)
                self._public_ws.subscribe(request)
            
            return True
        except Exception as e:
            print(f"[BitgetClient] 订阅失败: {e}")
            return False

    def unsubscribe_pair(self, pair: str, channels: List[str], strategy_uid: str) -> bool:
        """取消订阅"""
        try:
            inst_type = "SPOT" if self.inst_type == ExchangeType.SPOT else "USDT-FUTURES"
            pair = pair.replace('/', '')
            
            print(f"[BitgetClient] === 取消订阅 ===")
            print(f"交易对: {pair}")
            print(f"频道: {channels}")
            print(f"策略ID: {strategy_uid}")
            
            # 移除策略订阅
            for channel in channels:
                self._subscription_manager.unsubscribe(pair, channel, strategy_uid)
                
                # 如果该频道没有订阅者了，取消WebSocket订阅
                if not self._subscription_manager.has_subscribers(pair, channel):
                    request = WSRequest(channel=channel, pair=pair, inst_type=inst_type)
                    self._public_ws.unsubscribe(request)
            
            return True
        except Exception as e:
            print(f"[BitgetClient] 取消订阅失败: {e}")
            return False

    def _build_order_response(self, data: dict, request: OrderRequest) -> OrderResponse:
        """构建订单响应"""
        return OrderResponse(
            order_id=data.get("orderId", ""),
            client_order_id=request.client_order_id,
            status="success",
            pair=request.pair,
            side=request.side,
            trade_side=request.trade_side,
            volume=request.volume,
            price=request.price or Decimal('0'),
            created_time=int(data.get("cTime", 0)),
            error_message=None
        )

    def update_credentials(self, api_key: str, api_secret: str, passphrase: str):
        """更新API凭证"""
        self._api_key = api_key
        self._api_secret = api_secret
        self._passphrase = passphrase
        
        # 更新REST API客户端
        if self.inst_type == ExchangeType.SPOT:
            self.rest_api = BitgetSpotAPI(api_key, api_secret, passphrase)
        else:
            self.rest_api = BitgetMixAPI(api_key, api_secret, passphrase)

        # 需要重新连接WebSocket
        self.disconnect()
        self.connect()

    def test_connection(self) -> Dict:
        """测试API连接
        Returns:
            Dict: {
                'ws_status': Dict[str, bool],  # WebSocket连接状态
            }
        """
        try:
            return {
                'ws_status': self.get_ws_status()
            }
        except Exception as e:
            print(f"[BitgetClient] 获取连接状态失败: {e}")
            return {
                'ws_status': {
                    'public': False,
                    'private': False
                }
            }