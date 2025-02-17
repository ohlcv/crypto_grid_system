# src/exchange/bingx/websocket/bingx_ws_client.py

"""
BingX WebSocket客户端，处理订阅和消息分发
"""

import json
import logging
import uuid
from typing import Optional, Dict, Callable
from qtpy.QtCore import QObject, Signal

from .ws_manager import BingXWSManager

def generate_uuid() -> str:
    """生成UUID作为请求ID"""
    return str(uuid.uuid4())

class BingXWebSocketClient(QObject):
    """BingX WebSocket客户端"""
    
    # 定义信号
    message_received = Signal(dict)  # 消息接收信号
    error = Signal(str)             # 错误信号
    connected = Signal()            # 连接成功信号
    disconnected = Signal()         # 断开连接信号

    def __init__(self, 
                is_private: bool = False,
                api_key: str = None,
                api_secret: str = None,
                passphrase: str = None,
                logger: Optional[logging.Logger] = None):
        """初始化WebSocket客户端"""
        super().__init__()
        
        self.logger = logger or logging.getLogger(__name__)
        self._is_private = is_private
        self._api_key = api_key
        self._api_secret = api_secret
        self._passphrase = passphrase
        self._ws_manager: Optional[BingXWSManager] = None
        self._connected = False
        self._subscriptions: Dict[str, set] = {}

        # 设置 WebSocket Headers
        self._headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Origin': 'https://www.bingx.com',
            'Referer': 'https://www.bingx.com/'
        }

        # 根据连接类型选择正确的URL
        self._url = "wss://open-ws-swap.bingx.com/ws"  # 使用新的公共WebSocket端点
        if is_private:
            listen_key = self._get_listen_key()
            if listen_key:
                self._url = f"{self._url}?listenKey={listen_key}"

    def _get_listen_key(self) -> Optional[str]:
        """获取私有连接的listenKey"""
        if not self._is_private:
            return None
        # TODO: 调用REST API获取listenKey
        return None

    def connect(self):
        """建立WebSocket连接"""
        if self._ws_manager:
            return

        self._ws_manager = BingXWSManager(
            stream_url=self._url,
            headers=self._headers,  # 传入headers
            on_message=self._handle_message,
            on_open=self._handle_open,
            on_close=self._handle_close,
            on_error=self._handle_error,
            logger=self.logger
        )
        self._ws_manager.start()

    def disconnect(self):
        """断开WebSocket连接"""
        if self._ws_manager:
            self._ws_manager.close()
            self._ws_manager = None
            self._connected = False
            self.disconnected.emit()

    def subscribe(self, channel: str, symbol: str, callback: Optional[Callable] = None):
        """订阅特定交易对的数据流"""
        # 构造标准格式的dataType
        data_type = f"market.{channel}.{symbol}"
        
        # 添加订阅
        if data_type not in self._subscriptions:
            self._subscriptions[data_type] = set()
        if callback:
            self._subscriptions[data_type].add(callback)

        # 发送订阅请求
        request = {
            "id": generate_uuid(),
            "reqType": "sub",
            "dataType": data_type
        }
        self._send_message(request)

    def unsubscribe(self, channel: str, symbol: str):
        """取消订阅
        
        Args:
            channel: 频道名称
            symbol: 交易对
        """
        # 构造标准格式的dataType
        data_type = f"market.{channel}.{symbol}"
        
        # 发送取消订阅请求
        request = {
            "id": generate_uuid(),
            "reqType": "unsub",
            "dataType": data_type
        }
        self._send_message(request)

        # 移除订阅
        if data_type in self._subscriptions:
            del self._subscriptions[data_type]

    def _send_message(self, message: dict):
        """发送消息
        
        Args:
            message: 要发送的消息
        """
        if not self._ws_manager:
            self.logger.error("WebSocket未连接")
            return
        
        try:
            self._ws_manager.send_message(json.dumps(message))
        except Exception as e:
            self.logger.error(f"发送消息失败: {e}")
            self.error.emit(str(e))

    def _handle_message(self, _, message: str):
        """处理接收到的消息"""
        try:
            data = json.loads(message)
            
            # 处理事件类型消息
            if "event" in data:
                self._handle_event(data)
                return

            # 处理数据类型消息
            if "data" in data:
                self.message_received.emit(data)
                
                # 调用订阅回调
                stream_name = data.get("arg", {}).get("dataType")
                if stream_name in self._subscriptions:
                    for callback in self._subscriptions[stream_name]:
                        callback(data)
                        
        except Exception as e:
            self.logger.error(f"消息处理错误: {e}")
            self.error.emit(str(e))

    def _handle_event(self, event_data: dict):
        """处理事件消息"""
        event = event_data.get("event")
        if event == "login":
            self._handle_login(event_data)
        elif event == "error":
            self.error.emit(event_data.get("msg", "Unknown error"))

    def _handle_login(self, login_data: dict):
        """处理登录事件"""
        if login_data.get("code") == 0:
            self.logger.info("WebSocket登录成功")
        else:
            error_msg = f"WebSocket登录失败: {login_data.get('msg')}"
            self.logger.error(error_msg)
            self.error.emit(error_msg)

    def _handle_open(self, _):
        """处理连接打开事件"""
        self._connected = True
        self.logger.info("WebSocket连接已建立")
        self.connected.emit()

    def _handle_close(self, _):
        """处理连接关闭事件"""
        self._connected = False
        self.logger.info("WebSocket连接已关闭")
        self.disconnected.emit()

    def _handle_error(self, _, error):
        """处理错误事件"""
        self.logger.error(f"WebSocket错误: {error}")
        self.error.emit(str(error))

    @property
    def is_connected(self) -> bool:
        """连接状态"""
        return self._connected