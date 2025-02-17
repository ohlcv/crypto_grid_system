# src/exchange/client_factory.py

from enum import Enum
import threading
import time
import traceback
from typing import List, Optional, Dict, Protocol, Type
from qtpy.QtCore import QObject, Signal

from src.exchange.bingX.bingx_client import BingXClient

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
    WHITELIST_UIDS = ["5197445181", "5176387297", "3295149482"]  # 白名单用户ID列表
    ALLOWED_INVITER_IDS = ["5197445181", "5176387297"]  # 允许的邀请者ID列表
    # WHITELIST_UIDS = []  
    # ALLOWED_INVITER_IDS = []

    def validate_account(self, client: BaseClient) -> bool:
        try:
            response = client.rest_api.get_account_info()
            print(f"[BitgetValidator] 获取账户信息响应: {response}")
            if response.get('code') == '00000':
                data = response.get('data', {})
                user_id = data.get('userId')
                inviter_id = data.get('inviterId')
                print(f"[BitgetValidator] userId: {user_id}, inviterId: {inviter_id}")
                
                # 检查白名单
                if user_id in self.WHITELIST_UIDS:
                    print(f"[BitgetValidator] userId {user_id} 在白名单中，验证成功")
                    return True
                    
                # 检查邀请人
                if inviter_id in self.ALLOWED_INVITER_IDS:
                    print(f"[BitgetValidator] inviterId {inviter_id} 在允许列表中，验证成功")
                    return True
                
                print(f"[BitgetValidator] userId 和 inviterId 均未通过验证")
                return False
            else:
                print(f"[BitgetValidator] 响应码不为 '00000'，验证失败")
                return False
        except Exception as e:
            print(f"[BitgetValidator] 验证过程中发生异常: {e}")
            return False

class BingXValidator:
    """BingX验证器"""
    def validate_account(self, client: BaseClient) -> bool:
        try:
            # 首先检查WebSocket连接
            ws_status = client.get_ws_status()
            if not ws_status.get("public") or not ws_status.get("private"):
                print("[BingXValidator] WebSocket连接失败")
                return False

            # 然后验证API权限
            response = client.rest_api.get_account_info()
            if response and isinstance(response, dict):
                print("[BingXValidator] API验证成功")
                return True
                
            print("[BingXValidator] API验证失败")
            return False
            
        except Exception as e:
            print(f"[BingXValidator] 验证失败: {e}")
            return False

class ExchangeValidatorRegistry:
    """交易所配置注册中心（单例模式）"""
    _instance = None
    
    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """初始化注册表"""
        # 交易所验证器映射
        self._validators = {
            "bitget": BitgetValidator(),
            "bingx": BingXValidator()
        }
        
        # 交易所支持类型配置
        self._exchange_support = {
            "bitget": {
                ExchangeType.SPOT: True,
                ExchangeType.FUTURES: True
            },
            "bingx": {
                ExchangeType.SPOT: False,
                ExchangeType.FUTURES: True
            }
        }
        
        # 交易所客户端类映射
        self._client_classes = {
            "bitget": BitgetClient,
            "bingx": BingXClient
        }
    
    def get_validator(self, exchange: str) -> Optional[ExchangeValidator]:
        """获取交易所验证器"""
        return self._validators.get(exchange.lower())

    def get_client_class(self, exchange: str) -> Optional[Type[BaseClient]]:
        """获取交易所客户端类"""
        return self._client_classes.get(exchange.lower())

    def get_supported_types(self, exchange: str) -> Dict[ExchangeType, bool]:
        """获取交易所支持的交易类型"""
        return self._exchange_support.get(exchange.lower(), {})

    def get_all_exchanges(self) -> List[str]:
        """获取所有注册的交易所"""
        return list(self._client_classes.keys())

    def get_available_exchanges(self, inst_type: ExchangeType) -> List[str]:
        """获取支持指定交易类型的交易所列表"""
        return [
            exchange for exchange, support in self._exchange_support.items()
            if support.get(inst_type, False)
        ]
    
class ExchangeClientFactory(QObject):
    """整合后的客户端工厂"""
    client_created = Signal(object)
    client_error = Signal(str)
    validation_failed = Signal(str)
    client_status_changed = Signal(str, str)

    def __init__(self):
        super().__init__()
        self._clients: Dict[str, BaseClient] = {}
        self._client_threads: Dict[str, threading.Thread] = {}
        self._client_status: Dict[str, ClientStatus] = {}
        self._lock = threading.Lock()
        self.registry = ExchangeValidatorRegistry()  # 使用单例注册中心

    def create_client(self, tab_id: str, exchange: str, api_config: dict, inst_type: ExchangeType) -> Optional[BaseClient]:
        try:
            with self._lock:
                # 从注册中心获取配置
                if not self.registry.get_supported_types(exchange).get(inst_type, False):
                    raise ValueError(f"{exchange} does not support {inst_type.value}")

                client_class = self.registry.get_client_class(exchange)
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
        try:
            # 添加状态跟踪防止重复验证
            self._validation_attempted = False
            
            # 更新状态为连接中
            self._update_status(tab_id, ClientStatus.CONNECTING)
            
            # 连接客户端
            client.connect()
            
            # 等待连接完成
            max_wait = 10  
            start = time.time()
            while not client.is_connected:
                time.sleep(0.1)
                if time.time() - start > max_wait:
                    raise TimeoutError("连接超时")
            
            # 只验证一次
            if not self._validation_attempted:
                self._validation_attempted = True
                self._update_status(tab_id, ClientStatus.VALIDATING)
                validator = self.registry.get_validator(client.exchange)
                if validator:
                    if not validator.validate_account(client):
                        self._update_status(tab_id, ClientStatus.FAILED) 
                        # 只发送一次验证失败消息
                        self.validation_failed.emit("账户验证失败，请使用邀请链接注册后再使用！")
                        return
                        
            # 验证成功,更新状态为就绪        
            self._update_status(tab_id, ClientStatus.READY)
            self.client_created.emit(client)
            
        except Exception as e:
            if not self._validation_attempted:  # 确保错误消息也只发送一次
                self._update_status(tab_id, ClientStatus.FAILED)
                self.client_error.emit(str(e))
        finally:
            if self._client_status.get(tab_id) == ClientStatus.FAILED:
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

    def get_supported_exchanges(self, inst_type: ExchangeType = None) -> list:
        """获取支持的交易所列表
        
        Args:
            inst_type: 交易类型,如果指定则只返回支持该类型的交易所
        """
        if inst_type is None:
            return list(self._exchange_classes.keys())
            
        return [
            exchange for exchange, support in self.registry._exchange_support.items()
            if support.get(inst_type, False)
        ]
    
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