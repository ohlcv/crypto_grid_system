# src/exchange/client_factory.py

from enum import Enum
import threading
import time
import traceback
from typing import Optional, Dict, Protocol, Type
from qtpy.QtCore import QObject, Signal

from .base_client import BaseClient, ExchangeType
from .bitget.bitget_client import BitgetClient
from qtpy.QtWidgets import QApplication
from qtpy.QtCore import QTimer


class ClientStatus(Enum):
    """客户端状态"""
    INITIALIZING = "初始化"
    CONNECTING = "连接中" 
    VALIDATING = "验证中"
    READY = "就绪"
    FAILED = "失败"
    DISCONNECTED = "已断开"

class ExchangeValidator(Protocol):
    """交易所账户验证接口"""
    def validate_account(self, client: BaseClient) -> bool:
        """验证账户"""
        raise NotImplementedError

class BitgetValidator:
    """Bitget验证器"""
    WHITELIST_UIDS = ["5197445181", "5176387297", "3295149482"]  
    ALLOWED_INVITER_IDS = ["5197445181", "5176387297"]
    # WHITELIST_UIDS = []  
    # ALLOWED_INVITER_IDS = []

    def validate_account(self, client: BaseClient) -> bool:
        try:
            response = client.rest_api.get_account_info()
            if response.get('code') == '00000':
                data = response.get('data', {})
                user_id = data.get('userId')
                inviter_id = data.get('inviterId')
                
                # 检查白名单
                if user_id in self.WHITELIST_UIDS:
                    return True
                    
                # 检查邀请人
                if inviter_id in self.ALLOWED_INVITER_IDS:
                    return True
                    
            return False
        except Exception as e:
            print(f"Bitget验证失败: {e}")
            return False

class ExchangeValidatorRegistry:
    """交易所验证器注册表"""
    def __init__(self):
        self._validators: Dict[str, ExchangeValidator] = {
            "bitget": BitgetValidator(),
            # "binance": BinanceValidator(),
            # "okx": OkxValidator()
        }
    
    def get_validator(self, exchange: str) -> Optional[ExchangeValidator]:
        return self._validators.get(exchange.lower())

class ExchangeClientFactory(QObject):
    """交易所客户端工厂，管理不同交易所的客户端实例"""
    
    # 定义信号
    client_created = Signal(object)  # BaseClient
    client_error = Signal(str)  # error message
    validation_failed = Signal(str)  # validation error message
    client_status_changed = Signal(str, str)  # tab_id, status

    def __init__(self):
        super().__init__()
        self._clients: Dict[str, BaseClient] = {}
        self._client_threads: Dict[str, threading.Thread] = {}
        self._client_status: Dict[str, ClientStatus] = {}
        self._lock = threading.Lock()
        self._validator_registry = ExchangeValidatorRegistry()
        
        # 注册支持的交易所
        self._exchange_classes = {
            "bitget": BitgetClient,
            # "okx": OkxClient,  # 需要实现
        }

    def create_client(self, tab_id: str, exchange: str, api_config: dict, inst_type: ExchangeType) -> Optional[BaseClient]:
        """创建交易所客户端实例"""
        try:
            with self._lock:
                if tab_id in self._clients:
                    self.destroy_client(tab_id)
                
                client_class = self._exchange_classes.get(exchange)
                if not client_class:
                    raise ValueError(f"Unsupported exchange: {exchange}")
                
                # 创建客户端
                client = client_class(
                    api_key=api_config.get('api_key', ''),
                    api_secret=api_config.get('api_secret', ''),
                    passphrase=api_config.get('passphrase', ''),
                    inst_type=inst_type
                )
                
                # 设置初始状态
                self._clients[tab_id] = client
                self._client_status[tab_id] = ClientStatus.INITIALIZING
                self.client_status_changed.emit(tab_id, ClientStatus.INITIALIZING.value)
                
                # 连接客户端信号
                client.connection_status.connect(
                    lambda connected: self._handle_client_connected(tab_id, connected)
                )
                
                # 启动连接线程
                thread = threading.Thread(
                    target=self._run_client,
                    args=(client, tab_id),
                    name=f"Exchange-{exchange}-{tab_id}",
                    daemon=True
                )
                self._client_threads[tab_id] = thread
                thread.start()
                
                return client
                
        except Exception as e:
            self.client_error.emit(f"创建客户端失败: {str(e)}")
            return None
            
    def _run_client(self, client: BaseClient, tab_id: str):
        """在独立线程中运行客户端"""
        try:
            # 更新状态为连接中
            self._update_status(tab_id, ClientStatus.CONNECTING)
            
            # 连接客户端
            client.connect()
            
            # 等待连接完成
            max_wait = 10  # 最大等待秒数
            start = time.time()
            while not client.is_connected:
                time.sleep(0.1)
                if time.time() - start > max_wait:
                    raise TimeoutError("连接超时")
            
            # 验证账户
            self._update_status(tab_id, ClientStatus.VALIDATING)
            validator = self._validator_registry.get_validator(client.exchange)
            if validator:
                if not validator.validate_account(client):
                    raise ValueError("账户验证失败，请使用邀请链接注册后再使用！")
                    
            # 验证成功,更新状态为就绪        
            self._update_status(tab_id, ClientStatus.READY)
            self.client_created.emit(client)
            
        except Exception as e:
            self._update_status(tab_id, ClientStatus.FAILED)
            self.client_error.emit(str(e))
            self.destroy_client(tab_id)

    def _update_status(self, tab_id: str, status: ClientStatus):
        """更新客户端状态"""
        with self._lock:
            self._client_status[tab_id] = status
            self.client_status_changed.emit(tab_id, status.value)

    def _handle_client_connected(self, tab_id: str, connected: bool):
        """处理客户端连接状态变化"""
        if not connected:
            self._update_status(tab_id, ClientStatus.DISCONNECTED)

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
                    # print(f"已删除客户端引用: {tab_id}")
                    
                # except Exception as e:
                #     print(f"销毁客户端时出错: {str(e)}")
            
            if thread:
                # try:
                # print(f"清理线程: {tab_id}")
                if tab_id in self._client_threads:
                    del self._client_threads[tab_id]
                    # print(f"已删除线程引用: {tab_id}")
                # except Exception as e:
                #     print(f"清理线程时出错: {str(e)}")
            
            print(f"客户端销毁完成: {tab_id}")

    def get_supported_exchanges(self):
        """返回所有已注册的交易所"""
        return list(self._exchange_classes.keys())

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