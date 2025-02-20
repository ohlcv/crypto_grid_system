# src/exchange/client_factory.py

from enum import Enum
import threading
import time
import traceback
from typing import List, Optional, Dict, Protocol, Type
from qtpy.QtCore import QObject, Signal

from src.exchange.bingX.bingx_client import BingXClient

from .base_client import BaseClient, InstType
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
            # print(f"[BitgetValidator] 获取账户信息响应: {response}")
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
                InstType.SPOT: True,
                InstType.FUTURES: True
            },
            "bingx": {
                InstType.SPOT: False,
                InstType.FUTURES: True
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

    def get_supported_types(self, exchange: str) -> Dict[InstType, bool]:
        """获取交易所支持的交易类型"""
        return self._exchange_support.get(exchange.lower(), {})

    def get_all_exchanges(self) -> List[str]:
        """获取所有注册的交易所"""
        return list(self._client_classes.keys())

    def get_available_exchanges(self, inst_type: InstType) -> List[str]:
        """获取支持指定交易类型的交易所列表"""
        return [
            exchange for exchange, support in self._exchange_support.items()
            if support.get(inst_type, False)
        ]
    
class ExchangeClientFactory(QObject):
    """整合后的客户端工厂"""
    client_created = Signal(str, str, object)  # (tab_id, exchange_type, client)
    client_error = Signal(str)
    validation_failed = Signal(str)
    client_status_changed = Signal(str, str)

    def __init__(self):
        super().__init__()
        # 使用组合键来存储客户端
        self._clients: Dict[str, Dict[InstType, BaseClient]] = {}
        self._client_threads: Dict[str, Dict[InstType, threading.Thread]] = {} 
        self._client_status: Dict[str, Dict[InstType, ClientStatus]] = {}
        self._validation_status: Dict[str, bool] = {}
        self._lock = threading.Lock()
        self.registry = ExchangeValidatorRegistry()

    def create_client(self, tab_id: str, exchange: str, api_config: dict, inst_type: InstType) -> Optional[BaseClient]:
        try:
            with self._lock:
                # 从注册中心获取配置
                supported = self.registry.get_supported_types(exchange)
                if inst_type not in supported or not supported[inst_type]:
                    raise ValueError(f"{exchange}不支持{inst_type.value}")

                client_class = self.registry.get_client_class(exchange)
                if not client_class:
                    raise ValueError(f"Unsupported exchange: {exchange}")

                # 初始化tab_id的存储结构(如果不存在)
                if tab_id not in self._clients:
                    self._clients[tab_id] = {}
                    self._client_threads[tab_id] = {}
                    self._client_status[tab_id] = {}

                # 如果已存在相同类型的客户端，先销毁它
                if inst_type in self._clients[tab_id]:
                    self.destroy_client(tab_id, inst_type)
                
                # 创建客户端
                client = client_class(
                    api_key=api_config.get('api_key', ''),
                    api_secret=api_config.get('api_secret', ''),
                    passphrase=api_config.get('passphrase', ''),
                    inst_type=inst_type
                )
                
                # 设置初始状态
                self._clients[tab_id][inst_type] = client
                self._client_status[tab_id][inst_type] = ClientStatus.INITIALIZING
                self.client_status_changed.emit(tab_id, ClientStatus.INITIALIZING.value)
                
                # 连接客户端信号
                client.connection_status.connect(
                    lambda connected: self._handle_client_connected(tab_id, inst_type, connected)
                )
                
                # 添加 WebSocket 状态变化信号连接
                if hasattr(client, 'ws_status_changed'):
                    print(f"[ExchangeClientFactory] 连接WebSocket状态信号 - tab_id: {tab_id}")
                    client.ws_status_changed.connect(
                        lambda is_public, connected, tid=tab_id: self._forward_ws_status_to_ui(tid, is_public, connected)
                    )

                # 启动连接线程
                thread = threading.Thread(
                    target=self._run_client,
                    args=(client, tab_id, inst_type),
                    name=f"Exchange-{exchange}-{tab_id}-{inst_type.value}",
                    daemon=True
                )
                self._client_threads[tab_id][inst_type] = thread
                thread.start()
                
                return client
                
        except Exception as e:
            self.client_error.emit(f"创建客户端失败: {str(e)}")
            return None

    def destroy_client(self, tab_id: str, inst_type: Optional[InstType] = None):
        """销毁客户端实例"""
        with self._lock:
            print(f"开始销毁客户端: {tab_id}")
            
            if tab_id not in self._clients:
                return

            if inst_type:
                # 销毁特定类型的客户端
                if inst_type in self._clients[tab_id]:
                    self._destroy_specific_client(tab_id, inst_type)
            else:
                # 销毁该标签页的所有客户端
                for type_key in list(self._clients[tab_id].keys()):
                    self._destroy_specific_client(tab_id, type_key)

            # 如果tab_id下没有任何客户端了，清理这个tab_id
            if inst_type:
                if not self._clients[tab_id]:
                    self._cleanup_tab_data(tab_id)
            else:
                self._cleanup_tab_data(tab_id)

    def _destroy_specific_client(self, tab_id: str, inst_type: InstType):
        """销毁特定的客户端实例"""
        try:
            client = self._clients[tab_id][inst_type]
            
            # 先尝试正常断开
            print(f"尝试正常断开连接: {tab_id} - {inst_type.value}")
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
                print(f"正常断开失败，强制关闭连接: {tab_id} - {inst_type.value}")
                self._force_close_client(client)
            
            # 从字典中删除引用
            del self._clients[tab_id][inst_type]
            
            # 删除线程引用
            if inst_type in self._client_threads[tab_id]:
                del self._client_threads[tab_id][inst_type]
            
            # 删除状态引用
            if inst_type in self._client_status[tab_id]:
                del self._client_status[tab_id][inst_type]
                
        except Exception as e:
            print(f"销毁客户端时出错: {str(e)}")

    def _cleanup_tab_data(self, tab_id: str):
        """清理标签页相关的所有数据"""
        if tab_id in self._clients:
            del self._clients[tab_id]
        if tab_id in self._client_threads:
            del self._client_threads[tab_id]
        if tab_id in self._client_status:
            del self._client_status[tab_id]
        if tab_id in self._validation_status:
            del self._validation_status[tab_id]

    def _handle_client_connected(self, tab_id: str, inst_type: InstType, connected: bool):
        """处理客户端连接状态变化"""
        if not connected:
            if tab_id in self._client_status and inst_type in self._client_status[tab_id]:
                self._client_status[tab_id][inst_type] = ClientStatus.DISCONNECTED
                self.client_status_changed.emit(tab_id, ClientStatus.DISCONNECTED.value)

    def get_client(self, tab_id: str, inst_type: Optional[InstType] = None) -> Optional[BaseClient]:
        """获取客户端实例"""
        with self._lock:
            if tab_id not in self._clients:
                return None
            if inst_type:
                return self._clients[tab_id].get(inst_type)
            # 如果没有指定类型，返回第一个可用的客户端
            return next(iter(self._clients[tab_id].values())) if self._clients[tab_id] else None

    def _run_client(self, client: BaseClient, tab_id: str, inst_type: InstType):
        """运行客户端连接"""
        try:
            # 更新状态为连接中
            if tab_id in self._client_status and inst_type in self._client_status[tab_id]:
                self._client_status[tab_id][inst_type] = ClientStatus.CONNECTING
                self.client_status_changed.emit(tab_id, ClientStatus.CONNECTING.value)
            
            # 连接客户端
            client.connect()
            
            # 等待连接完成
            max_wait = 10  
            start = time.time()
            while not client.is_connected:
                time.sleep(0.1)
                if time.time() - start > max_wait:
                    raise TimeoutError("连接超时")
            
            # 等待WebSocket连接完成
            time.sleep(1)  # 给WebSocket一些时间完成连接
            
            # 立即进行验证
            if tab_id in self._client_status and inst_type in self._client_status[tab_id]:
                self._client_status[tab_id][inst_type] = ClientStatus.VALIDATING
                self.client_status_changed.emit(tab_id, ClientStatus.VALIDATING.value)
                
            validator = self.registry.get_validator(client.exchange)
            if validator:
                print(f"[ExchangeClientFactory] 开始验证 {client.inst_type.name} 账户")
                if not validator.validate_account(client):
                    if tab_id in self._client_status and inst_type in self._client_status[tab_id]:
                        self._client_status[tab_id][inst_type] = ClientStatus.FAILED
                    self.validation_failed.emit("账户验证失败，请使用邀请链接注册后再使用！")
                    return
                print(f"[ExchangeClientFactory] {client.inst_type.name} 账户验证成功")
                self._validation_status[tab_id] = True
                
                # 验证成功后,更新WebSocket状态
                ws_status = client.get_ws_status()
                if hasattr(client, 'ws_status_changed'):
                    client.ws_status_changed.emit(True, ws_status.get('public', False))
                    client.ws_status_changed.emit(False, ws_status.get('private', False))
                        
            # 验证成功,更新状态为就绪        
            if tab_id in self._client_status and inst_type in self._client_status[tab_id]:
                self._client_status[tab_id][inst_type] = ClientStatus.READY
                self.client_status_changed.emit(tab_id, ClientStatus.READY.value)
            self.client_created.emit(tab_id, inst_type.value, client)
            
        except Exception as e:
            if tab_id in self._client_status and inst_type in self._client_status[tab_id]:
                self._client_status[tab_id][inst_type] = ClientStatus.FAILED
            self.client_error.emit(str(e))
        finally:
            if tab_id in self._client_status and inst_type in self._client_status[tab_id]:
                if self._client_status[tab_id][inst_type] == ClientStatus.FAILED:
                    self.destroy_client(tab_id, inst_type)

    def _forward_ws_status_to_ui(self, tab_id: str, is_public: bool, connected: bool):
        """转发 WebSocket 状态到 UI"""
        # print(f"[ExchangeClientFactory] 转发WebSocket状态 - tab_id: {tab_id}, {'公有' if is_public else '私有'}: {'已连接' if connected else '未连接'}")
        
        # 获取特定的客户端
        client = self._clients.get(tab_id)
        if client and hasattr(client, 'api_manager'):
            client.api_manager.update_ws_status(is_public, connected)

    def _update_status(self, tab_id: str, status: ClientStatus):
        """更新客户端状态"""
        with self._lock:
            self._client_status[tab_id] = status
            self.client_status_changed.emit(tab_id, status.value)

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

    def get_supported_exchanges(self, inst_type: InstType = None) -> list:
        """获取支持的交易所列表
        
        Args:
            inst_type: 交易类型,如果指定则只返回支持该类型的交易所
        """
        if inst_type is None:
            return self.registry.get_all_exchanges()  # 使用注册表的现有方法
            # 或者直接使用: return list(self.registry._client_classes.keys())
            
        return [
            exchange for exchange, support in self.registry._exchange_support.items()
            if support.get(inst_type, False)
        ]