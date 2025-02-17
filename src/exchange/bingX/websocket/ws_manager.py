# src/exchange/bingx/websocket/ws_manager.py

"""
BingX WebSocket管理器，负责WebSocket连接和数据流处理
"""

import gzip
import io
import json
import logging
import threading
from typing import Optional, Callable
from websocket import (
    WebSocket,
    WebSocketConnectionClosedException,
    create_connection
)

class BingXWSManager(threading.Thread):
    """BingX WebSocket连接管理器"""
    
    def __init__(
        self,
        stream_url: str,
        headers: dict = None,  # 添加headers参数
        on_message: Optional[Callable] = None,
        on_open: Optional[Callable] = None,
        on_close: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
        logger: Optional[logging.Logger] = None
    ):
        """初始化WebSocket管理器
        
        Args:
            stream_url: WebSocket连接URL
            headers: WebSocket连接headers
            on_message: 消息回调函数
            on_open: 连接建立回调
            on_close: 连接关闭回调
            on_error: 错误回调
            logger: 日志记录器
        """
        threading.Thread.__init__(self)
        self.logger = logger or logging.getLogger(__name__)
        self.stream_url = stream_url
        self.headers = headers or {}  # 保存headers
        self.on_message = on_message
        self.on_open = on_open
        self.on_close = on_close
        self.on_error = on_error
        self.ws: Optional[WebSocket] = None
        self._running = True

        # 创建WebSocket连接
        self.create_connection()

    def create_connection(self):
        """创建WebSocket连接"""
        try:
            self.logger.info(f"正在连接WebSocket服务器: {self.stream_url}")
            self.ws = create_connection(
                self.stream_url,
                header=self.headers,  # 使用headers
                enable_multithread=True,
                suppress_origin=True
            )
            self.logger.info("WebSocket连接已建立")
            self._callback(self.on_open)
        except Exception as e:
            self.logger.error(f"WebSocket连接失败: {e}")
            self._callback(self.on_error, e)

    def run(self):
        """线程运行函数"""
        while self._running:
            try:
                self._read_data()
            except Exception as e:
                self.logger.error(f"数据读取错误: {e}")
                if isinstance(e, WebSocketConnectionClosedException):
                    self.create_connection()
                else:
                    self._callback(self.on_error, e)

    def send_message(self, message: str):
        """发送消息
        
        Args:
            message: 要发送的消息
        """
        if not self.ws:
            self.logger.error("WebSocket未连接")
            return
        self.logger.debug(f"发送消息: {message}")
        self.ws.send(message)

    def _read_data(self):
        """读取并处理WebSocket数据"""
        if not self.ws:
            return
            
        try:
            data = self.ws.recv()
            
            # 处理心跳消息
            if data == "Ping":
                self.ws.send("Pong")
                return
                
            # 处理gzip压缩数据
            if isinstance(data, bytes):
                try:
                    compressed_data = gzip.GzipFile(fileobj=io.BytesIO(data), mode='rb')
                    data = compressed_data.read().decode('utf-8')
                except Exception as e:
                    self.logger.error(f"解压数据失败: {e}")
                    return
            
            # 回调处理消息
            self._callback(self.on_message, data)
            
        except Exception as e:
            self.logger.error(f"数据读取错误: {e}")
            raise

    def close(self):
        """关闭WebSocket连接"""
        self._running = False
        if self.ws:
            self.ws.close()
        self._callback(self.on_close)

    def _callback(self, callback: Optional[Callable], *args):
        """执行回调函数
        
        Args:
            callback: 回调函数
            args: 回调函数参数
        """
        if callback:
            try:
                callback(self, *args)
            except Exception as e:
                self.logger.error(f"回调执行错误: {e}")
                if self.on_error:
                    self.on_error(self, e)