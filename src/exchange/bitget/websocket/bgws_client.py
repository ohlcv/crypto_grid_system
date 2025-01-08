# src/exchange/bitget/websocket/bgws_client.py

from typing import Dict, Optional
import json
import time
import traceback
from qtpy.QtCore import QObject, Signal
from src.exchange.base_client import WSRequest
from src.exchange.bitget.ws.bitget_ws_client import BitgetWsClient, SubscribeReq
from src.utils.error.error_handler import error_handler
from src.utils.logger.log_helper import ws_logger

class BGWebSocketClient(QObject):
    """Bitget WebSocket客户端实现
    
    使用组合而不是继承来集成BitgetWsClient
    """
    # 定义Qt信号
    message_received = Signal(dict)  # 消息接收信号
    error = Signal(str)  # 错误信号
    connected = Signal()  # 连接成功信号
    disconnected = Signal()  # 断开连接信号

    def __init__(self, is_private: bool = False, 
                 api_key: str = None,
                 api_secret: str = None,
                 passphrase: str = None):
        super().__init__()
        
        # 初始化状态
        self._is_private = is_private
        self._is_connected = False
        self._login_status = False
        self.logger = ws_logger
        
        # 使用组合方式集成BitgetWsClient
        url = "wss://ws.bitget.com/v2/ws/private" if is_private else "wss://ws.bitget.com/v2/ws/public"
        self._ws_client = BitgetWsClient(url, need_login=is_private)
        
        # 设置API凭证(如果是私有连接)
        if is_private and all([api_key, api_secret, passphrase]):
            self._ws_client.api_key(api_key)\
                .api_secret_key(api_secret)\
                .passphrase(passphrase)
            self.logger.debug(f"验证私有参数：\n{api_key}\n{api_secret}\n{passphrase}")
        
        # 设置回调
        self._ws_client.listener(self._handle_message)
        self._ws_client.error_listener(self._handle_error)
        self._ws_client.on_open = self._handle_on_open

    def connect(self):
        """建立连接"""
        try:
            self._ws_client.build()
        except Exception as e:
            self.logger.error(f"连接失败: {str(e)}\n{traceback.format_exc()}")
            self.error.emit(str(e))

    def disconnect(self):
        """断开连接"""
        if self._ws_client:
            try:
                self._ws_client.close()
            except:
                pass
        self._is_connected = False
        self.disconnected.emit()

    def _handle_on_open(self):
        """处理WebSocket连接打开事件"""
        self._is_connected = True
        print(f"WebSocket已连接 - is_private: {self._is_private}")
        self.connected.emit()

    def _handle_error(self, error: str):
        """处理WebSocket错误"""
        try:
            self.logger.error(f"WebSocket错误: {error}")
            
            # 处理API验证失败
            try:
                error_data = json.loads(error)
                if error_data.get("code") == 30012:
                    self.logger.error("API验证失败")
                    self._is_connected = False
                    self.disconnected.emit()
                    self.error.emit("API验证失败，请检查API配置")
                    return
            except json.JSONDecodeError:
                pass
            
            # 发送错误信号
            self.error.emit(error)
            
            # 如果已连接,发送断开连接信号
            if self._is_connected:
                self._is_connected = False
                self.disconnected.emit()
                
        except Exception as e:
            self.logger.error(f"处理错误时出错: {str(e)}\n{traceback.format_exc()}")

    def _handle_message(self, message: str) -> None:
        """处理接收到的WebSocket消息"""
        try:
            # 忽略心跳消息
            if message == 'pong':
                return
                    
            # 解析消息
            data = json.loads(message)
            
            # 处理登录消息
            if "event" in data and data["event"] == "login":
                self._handle_login_response(data)
                return

            # 格式化并发送消息
            formatted_message = self._format_message(data)
            if formatted_message:
                self.message_received.emit(formatted_message)

        except Exception as e:
            self.logger.error(f"消息处理错误: {str(e)}\n{traceback.format_exc()}")

    def _handle_login_response(self, message: dict):
        """处理登录响应"""
        self.logger.debug(f"登录响应: {message}")
        if message.get("event") == "login":
            self._login_status = message.get("code") == 0
            if self._login_status:
                self.connected.emit()
            else:
                self.disconnected.emit()

    def _format_message(self, data: dict) -> Optional[dict]:
        """格式化消息以供上层应用使用"""
        try:
            # 处理订阅确认消息
            if "event" in data:
                return {
                    "type": "event",
                    "event": data.get("event"),
                    "channel": data.get("arg", {}).get("channel"),
                    "symbol": data.get("arg", {}).get("instId")
                }
                
            # 处理行情数据消息
            if "data" in data and "arg" in data:
                return {
                    "channel": data["arg"].get("channel"),
                    "symbol": data["arg"].get("instId"),
                    "ts": data.get("ts"),
                    "data": data["data"][0] if isinstance(data.get("data"), list) else data.get("data")
                }
                
            return None
            
        except Exception as e:
            self.logger.error(f"消息格式化错误: {str(e)}\n原始数据: {data}")
            return None

    @property
    def is_connected(self) -> bool:
        """连接状态"""
        return self._is_connected and (not self._is_private or self._login_status)

    def subscribe(self, request: WSRequest) -> None:
        """发送订阅请求"""
        try:
            # 创建SDK的订阅请求对象
            subscribe_req = SubscribeReq(
                instType=request.inst_type,
                channel=request.channel,
                instId=request.pair
            )
            
            # 使用SDK的订阅方法
            self._ws_client.subscribe([subscribe_req])
            self.logger.info(f"已订阅: {request.pair} - {request.channel}")
            
        except Exception as e:
            self.logger.error(f"订阅失败: {str(e)}")
            self.error.emit(f"Subscribe failed: {str(e)}")

    def unsubscribe(self, request: WSRequest) -> None:
        """发送取消订阅请求"""
        try:
            # 创建SDK的订阅请求对象
            subscribe_req = SubscribeReq(
                instType=request.inst_type,
                channel=request.channel,
                instId=request.pair
            )
            
            # 使用SDK的取消订阅方法
            self._ws_client.unsubscribe([subscribe_req])
            self.logger.info(f"已取消订阅: {request.pair} - {request.channel}")
            
        except Exception as e:
            self.logger.error(f"取消订阅失败: {str(e)}")
            self.error.emit(f"Unsubscribe failed: {str(e)}")