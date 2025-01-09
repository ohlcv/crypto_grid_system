# src/exchange/client_factory.py

import threading
import time
import traceback
from typing import Optional, Dict, Type
from qtpy.QtCore import QObject, Signal

from .base_client import BaseClient, ExchangeType
from .bitget.bitget_client import BitgetClient
from qtpy.QtWidgets import QApplication
from qtpy.QtCore import QTimer

class ExchangeClientFactory(QObject):
    """交易所客户端工厂，管理不同交易所的客户端实例"""
    
    # 定义信号
    client_created = Signal(object)  # BaseClient
    client_error = Signal(str)  # error message

    def __init__(self):
        super().__init__()
        self._clients: Dict[str, BaseClient] = {}
        self._client_threads: Dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
        
        # 注册支持的交易所
        self._exchange_classes = {
            "bitget": BitgetClient,
            # "okx": OkxClient,  # 需要实现
        }

    def get_supported_exchanges(self):
        """返回所有已注册的交易所"""
        return list(self._exchange_classes.keys())

    def create_client(self, tab_id: str, exchange: str, api_config: dict, inst_type: ExchangeType) -> Optional[BaseClient]:
        """创建交易所客户端实例"""
        print(f"\n=== 开始创建客户端 ===")
        print(f"Tab ID: {tab_id}")
        print(f"Exchange: {exchange}")
        print(f"Exchange Type: {inst_type}")
        
        with self._lock:
            # 如果已存在客户端，先销毁
            if tab_id in self._clients:
                print(f"发现已存在的客户端实例，准备销毁...")
                self.destroy_client(tab_id)
                print(f"已销毁旧客户端实例")
            
            # 获取对应的客户端类
            client_class = self._exchange_classes.get(exchange)
            if not client_class:
                raise ValueError(f"Unsupported exchange: {exchange}")
            
            print(f"准备创建新的 {client_class.__name__} 实例...")
            
            # 创建新的客户端实例
            client = client_class(
                api_key=api_config.get('api_key', ''),
                api_secret=api_config.get('api_secret', ''),
                passphrase=api_config.get('passphrase', ''),
                inst_type=inst_type
            )
            
            # 保存客户端实例
            self._clients[tab_id] = client
            
            # 创建后台连接线程，但不立即启动
            thread = threading.Thread(
                target=self._run_client,
                args=(client,),
                name=f"Exchange-{exchange}-{tab_id}",
                daemon=True
            )
            self._client_threads[tab_id] = thread
            
            # 先发送信号，让UI可以继续
            print(f"[ExchangeClientFactory] Created client instance: {client}")
            self.client_created.emit(client)
            print("=== 客户端创建完成 ===\n")
            
            # 启动连接线程
            thread.start()
            
            return client

    def _run_client(self, client: BaseClient) -> None:
        """在独立线程中运行客户端"""
        try:
            # 启动连接流程但不等待
            client.connect(wait=False)
        except Exception as e:
            print(f"客户端连接错误: {str(e)}")
            self.client_error.emit(str(e))

    def _force_close_client(self, client):
        """强制关闭客户端的所有连接"""
        # try:
        # 强制关闭公共WebSocket
        if hasattr(client, '_public_ws') and client._public_ws:
            if hasattr(client._public_ws, '_client') and client._public_ws._client:
                # 直接关闭底层WebSocket连接
                if hasattr(client._public_ws._client, '_ws_client'):
                    try:
                        client._public_ws._client._ws_client.close()
                    except:
                        pass
                client._public_ws._client = None
            client._public_ws = None

        # 强制关闭私有WebSocket
        if hasattr(client, '_private_ws') and client._private_ws:
            if hasattr(client._private_ws, '_client') and client._private_ws._client:
                # 直接关闭底层WebSocket连接
                if hasattr(client._private_ws._client, '_ws_client'):
                    try:
                        client._private_ws._client._ws_client.close()
                    except:
                        pass
                client._private_ws._client = None
            client._private_ws = None

        # except Exception as e:
        #     print(f"强制关闭连接时出错: {str(e)}")

    def destroy_client(self, tab_id: str) -> None:
        """销毁客户端实例"""
        with self._lock:
            print(f"开始销毁客户端: {tab_id}")
            
            # 获取客户端和线程实例
            client = self._clients.get(tab_id)
            thread = self._client_threads.get(tab_id)
            
            if client:
                # try:
                # 先尝试正常断开
                print("尝试正常断开连接")
                force_quit = True
                
                def try_disconnect():
                    nonlocal force_quit
                    try:
                        client.disconnect()
                        force_quit = False
                    except:
                        pass
                
                # 在新线程中尝试断开，最多等待1秒
                disconnect_thread = threading.Thread(target=try_disconnect)
                disconnect_thread.daemon = True
                disconnect_thread.start()
                disconnect_thread.join(timeout=1.0)
                
                # 如果正常断开失败，强制关闭
                if force_quit:
                    print("正常断开失败，强制关闭连接")
                    self._force_close_client(client)
                
                # 从字典中删除引用
                if tab_id in self._clients:
                    del self._clients[tab_id]
                    print(f"已删除客户端引用: {tab_id}")
                    
                # except Exception as e:
                #     print(f"销毁客户端时出错: {str(e)}")
            
            if thread:
                # try:
                print(f"清理线程: {tab_id}")
                if tab_id in self._client_threads:
                    del self._client_threads[tab_id]
                    print(f"已删除线程引用: {tab_id}")
                # except Exception as e:
                #     print(f"清理线程时出错: {str(e)}")
            
            print(f"客户端销毁完成: {tab_id}")

    def get_client(self, tab_id: str) -> Optional[BaseClient]:
        """
        获取客户端实例
        
        Args:
            tab_id: 标签页ID
            
        Returns:
            BaseClient实例，如果不存在则返回None
        """
        with self._lock:
            return self._clients.get(tab_id)