# src/ui/components/strategy_manager_wrapper.py

import os
import json
import uuid
import threading
import traceback
from enum import Enum
from decimal import Decimal
from datetime import datetime
from typing import Optional, Dict, List
from qtpy.QtCore import QObject, Signal

from src.exchange.base_client import InstType, BaseClient, PositionSide, SymbolConfig
from src.exchange.client_factory import ExchangeClientFactory
from src.strategy.grid.grid_core import GridData
from src.strategy.grid.grid_strategy_manager import GridStrategyManager
from src.utils.common.common import create_file_if_not_exists


class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Enum):
            return obj.value  # 将枚举转换为其值
        if isinstance(obj, Decimal):
            return float(obj)  # 将 Decimal 转换为 float
        return super().default(obj)
    
class StrategyManagerWrapper(QObject):
    """策略管理器包装类,处理策略的创建、管理和数据持久化"""

    # 信号定义
    strategy_added = Signal(str)  # uid
    strategy_deleted = Signal(str)  # uid
    strategy_updated = Signal(str)  # uid
    strategy_error = Signal(str, str)  # uid, error_msg
    strategy_started = Signal(str)  # uid
    strategy_stopped = Signal(str)  # uid
    strategies_saved = Signal(str)  # message
    strategies_loaded = Signal(str)  # message
    data_saved = Signal(str)  # message
    data_loaded = Signal(str)  # message
    save_error = Signal(str)  # error_message
    load_error = Signal(str)  # error_message

    def __init__(self, inst_type: InstType, client_factory: ExchangeClientFactory):
        super().__init__()
        self.inst_type = inst_type
        self.client_factory = client_factory
        self.strategy_manager = GridStrategyManager()
        self._subscriptions = {}  # pair -> set(strategy_uids)
        
        # 设置数据保存路径，使用 .value 获取枚举值并转为小写
        self.data_path = os.path.join(
            './data', 
            'grid_strategy', 
            f'{inst_type.value.lower()}_strategies.json'
        )
        
        # 保存线程控制
        self._save_thread = None
        self._load_thread = None
        
        # 连接策略管理器信号
        self._connect_manager_signals()

    def _connect_manager_signals(self):
        """连接策略管理器的信号"""
        self.strategy_manager.signals.strategy_started.connect(lambda uid: self.strategy_started.emit(uid))
        self.strategy_manager.signals.strategy_stopped.connect(lambda uid: self.strategy_stopped.emit(uid))
        self.strategy_manager.signals.strategy_error.connect(lambda uid, msg: self.strategy_error.emit(uid, msg))
        self.strategy_manager.signals.strategy_status_changed.connect(lambda uid, status: self.strategy_updated.emit(uid))
        self.strategy_manager.signals.save_requested.connect(self.save_strategies)

    def _subscribe_pair(self, pair: str, uid: str, client: BaseClient) -> bool:
        print(f"\n[StrategyManagerWrapper] 订阅交易对 {pair} - 策略 {uid}")
        if pair not in self._subscriptions:
            self._subscriptions[pair] = set()
            success = client.subscribe_pair(pair, ["ticker"], uid)
            if not success:
                print(f"[StrategyManagerWrapper] 订阅失败")
                return False
        self._subscriptions[pair].add(uid)
        print(f"[StrategyManagerWrapper] 当前订阅: {self._subscriptions}")
        return True
        
    def _unsubscribe_pair(self, pair: str, uid: str, client: BaseClient):
        print(f"\n[StrategyManagerWrapper] 取消订阅 {pair} - 策略 {uid}")
        if pair not in self._subscriptions:
            return
        self._subscriptions[pair].discard(uid)
        if not self._subscriptions[pair]:
            client.unsubscribe_pair(pair, ["ticker"], uid)
            del self._subscriptions[pair]
        print(f"[StrategyManagerWrapper] 当前订阅: {self._subscriptions}")

    def _manage_subscription(self, pair: str, uid: str, client: BaseClient, subscribe: bool = True) -> bool:
        try:
            if subscribe:
                if pair not in self._subscriptions:
                    self._subscriptions[pair] = set()
                    print(f"[StrategyManagerWrapper] 订阅交易对: {pair}")
                    success = client.subscribe_pair(pair, ["ticker"], uid)
                    if not success:
                        print(f"[StrategyManagerWrapper] 订阅失败: {pair}")
                        return False
                self._subscriptions[pair].add(uid)
            else:
                if pair in self._subscriptions:
                    self._subscriptions[pair].discard(uid)
                    if not self._subscriptions[pair]:
                        client.unsubscribe_pair(pair, ["ticker"], uid)
                        del self._subscriptions[pair]
            return True
        except Exception as e:
            print(f"[StrategyManagerWrapper] 订阅管理错误: {e}")
            print(f"[StrategyManagerWrapper] 错误详情: {traceback.format_exc()}")
            return False

    def process_market_data(self, pair: str, data: dict):
        try:
            self.strategy_manager.process_market_data(pair, data)
        except Exception as e:
            error_msg = f"处理市场数据失败: {str(e)}"
            print(f"[StrategyManagerWrapper] {error_msg}")
            print(f"[StrategyManagerWrapper] 错误详情: {traceback.format_exc()}")
            self.strategy_error.emit("", error_msg)

    def _handle_strategy_updated(self, uid: str):
        """处理策略更新事件的统一入口"""
        try:
            # print(f"[StrategyManagerWrapper] 收到策略更新信号: {uid}")
            # 转发信号给UI
            self.strategy_updated.emit(uid)
        except Exception as e:
            print(f"[StrategyManagerWrapper] 处理策略更新事件失败: {e}")
            print(f"[StrategyManagerWrapper] 错误详情: {traceback.format_exc()}")

    def create_strategy(self, symbol_config: SymbolConfig, exchange: str, is_long: bool = True) -> Optional[str]:
        """创建空白策略模板"""
        try:
            uid = str(uuid.uuid4())[:8]
            print(f"\n[StrategyManagerWrapper] === 创建策略模板 {uid} ===")
            
            # 仅创建基础数据结构
            grid_data = GridData(uid, symbol_config, exchange, self.inst_type)
            grid_data.set_direction(is_long)
            grid_data.operations = {"开仓": True, "平仓": True}
            grid_data.status = "已添加"
            
            # 保存到数据字典
            self.strategy_manager._data[uid] = grid_data
            self.strategy_added.emit(uid)
            
            # 保存到文件
            self.save_strategies(show_message=False)
            return uid
            
        except Exception as e:
            error_msg = f"创建策略失败: {str(e)}"
            print(f"[StrategyManagerWrapper] {error_msg}")
            self.strategy_error.emit("", error_msg)
            return None

    def start_strategy(self, uid: str, exchange_client: BaseClient) -> bool:
        """启动策略,初始化交易器和连接"""
        print(f"\n[StrategyManagerWrapper] === 启动策略 {uid} ===")
        try:
            grid_data = self.strategy_manager.get_strategy_data(uid)
            if not grid_data:
                error_msg = "未找到策略数据"
                print(f"[StrategyManagerWrapper] {error_msg}")
                self.strategy_error.emit(uid, error_msg)
                return False

            if self.strategy_manager.is_strategy_running(uid):
                error_msg = "策略已在运行中"
                print(f"[StrategyManagerWrapper] {error_msg}")
                self.strategy_error.emit(uid, error_msg)
                return False

            # 1. 清理旧的交易器和信号
            self._cleanup_strategy_connections(uid)

            # 2. 连接 grid_data 的数据更新信号
            grid_data.data_updated.connect(self._handle_strategy_updated)

            # 3. 创建并初始化交易器
            trader = self._create_trader(uid)
            if not trader:
                return False

            # 4. 设置交易所客户端
            trader.set_client(exchange_client)

            # 5. 订阅行情
            if not self._manage_subscription(grid_data.symbol_config.pair, uid, exchange_client, True):
                error_msg = "订阅行情失败"
                print(f"[StrategyManagerWrapper] {error_msg}")
                self.strategy_error.emit(uid, error_msg)
                return False

            # 6. 启动策略
            if trader.start():
                self.strategy_started.emit(uid)
                grid_data.status = "运行中"
                grid_data.data_updated.emit(uid)
                print(f"[StrategyManagerWrapper] 策略启动完成: {uid}")
                return True

            error_msg = "策略启动失败"
            print(f"[StrategyManagerWrapper] {error_msg}")
            self.strategy_error.emit(uid, error_msg)
            return False

        except Exception as e:
            error_msg = f"启动策略失败: {str(e)}"
            print(f"[StrategyManagerWrapper] {error_msg}")
            print(f"[StrategyManagerWrapper] 错误详情: {traceback.format_exc()}")
            self.strategy_error.emit(uid, error_msg)
            return False

    def _create_trader(self, uid: str):
        """创建并初始化交易器"""
        try:
            from src.strategy.grid.grid_trader import GridTrader
            trader = GridTrader(self.strategy_manager, uid)
            # 使用交易器提供的方法连接信号
            trader.connect_signals(
                error_slot=self.strategy_manager._handle_strategy_error,
                save_slot=self.strategy_manager._handle_save_request
            )
            self.strategy_manager._strategies[uid] = trader
            return trader
        except Exception as e:
            error_msg = f"创建交易器失败: {str(e)}"
            print(f"[StrategyManagerWrapper] {error_msg}")
            self.strategy_error.emit(uid, error_msg)
            return None

    def _cleanup_strategy_connections(self, uid: str):
        """清理策略相关的所有连接"""
        print(f"[StrategyManagerWrapper] 清理策略连接: {uid}")
        
        # 1. 清理交易器
        if uid in self.strategy_manager._strategies:
            trader = self.strategy_manager._strategies[uid]
            # 使用交易器提供的方法断开信号
            trader.disconnect_signals()
            trader.stop()
            del self.strategy_manager._strategies[uid]

        # 2. 清理数据信号
        grid_data = self.strategy_manager._data.get(uid)
        if grid_data:
            try:
                grid_data.data_updated.disconnect(self._handle_strategy_updated)
            except TypeError:
                pass

    def stop_strategy(self, uid: str, exchange_client: BaseClient) -> bool:
        """停止策略并清理连接"""
        try:
            grid_data = self.strategy_manager.get_strategy_data(uid)
            if not grid_data:
                error_msg = "策略数据不存在"
                print(f"[StrategyManagerWrapper] {error_msg}")
                self.strategy_error.emit(uid, error_msg)
                return False

            # 1. 取消行情订阅
            if not self._manage_subscription(grid_data.symbol_config.pair, uid, exchange_client, False):
                print(f"[StrategyManagerWrapper] 警告: 取消订阅失败")

            # 2. 停止策略运行
            if not self.strategy_manager.stop_strategy(uid):
                error_msg = "停止策略失败"
                print(f"[StrategyManagerWrapper] {error_msg}")
                self.strategy_error.emit(uid, error_msg)
                return False

            # 3. 清理连接
            self._cleanup_strategy_connections(uid)

            self.save_strategies(show_message=False)
            return True

        except Exception as e:
            error_msg = f"停止策略失败: {str(e)}"
            print(f"[StrategyManagerWrapper] {error_msg}")
            print(f"[StrategyManagerWrapper] 错误详情: {traceback.format_exc()}")
            self.strategy_error.emit(uid, error_msg)
            return False

    def delete_strategy(self, uid: str, exchange_client: Optional[BaseClient] = None) -> bool:
        try:
            grid_data = self.strategy_manager.get_strategy_data(uid)
            if not grid_data:
                error_msg = "策略数据不存在"
                print(f"[StrategyManagerWrapper] {error_msg}")
                self.strategy_error.emit(uid, error_msg)
                return False

            if exchange_client and self.strategy_manager.is_strategy_running(uid):
                if not self._manage_subscription(grid_data.symbol_config.pair, uid, exchange_client, False):
                    error_msg = "取消订阅失败"
                    print(f"[StrategyManagerWrapper] {error_msg}")
                    self.strategy_error.emit(uid, error_msg)
                    # 继续执行，不影响删除流程

            if not self.strategy_manager.delete_strategy(uid):
                error_msg = "删除策略失败"
                print(f"[StrategyManagerWrapper] {error_msg}")
                self.strategy_error.emit(uid, error_msg)
                return False

            self.strategy_deleted.emit(uid)
            self.save_strategies(show_message=False)
            return True

        except Exception as e:
            error_msg = f"删除策略失败（未预期错误）: {str(e)}"
            print(f"[StrategyManagerWrapper] {error_msg}")
            print(f"[StrategyManagerWrapper] 错误详情: {traceback.format_exc()}")
            self.strategy_error.emit(uid, error_msg)
            return False
        
    def stop_all_strategies(self, exchange_client: BaseClient):
        try:
            running_strategies = [
                uid for uid in self.strategy_manager._data.keys()
                if self.strategy_manager.is_strategy_running(uid)
            ]

            success_count = 0
            for uid in running_strategies:
                if self.stop_strategy(uid, exchange_client):
                    success_count += 1
                else:
                    print(f"[StrategyManagerWrapper] 停止策略 {uid} 失败")

            return success_count, len(running_strategies)

        except Exception as e:
            error_msg = f"停止所有策略失败（未预期错误）: {str(e)}"
            print(f"[StrategyManagerWrapper] {error_msg}")
            print(f"[StrategyManagerWrapper] 错误详情: {traceback.format_exc()}")
            self.strategy_error.emit("", error_msg)
            return 0, 0

    def close_position(self, uid: str, exchange_client: BaseClient) -> tuple[bool, str]:
        """处理平仓请求"""
        try:
            grid_data = self.strategy_manager.get_strategy_data(uid)
            if not grid_data:
                error_msg = "策略数据不存在"
                self.strategy_error.emit(uid, error_msg)
                return False, error_msg

            if self.strategy_manager.is_strategy_running(uid):
                error_msg = "请先停止策略再进行平仓操作"
                self.strategy_error.emit(uid, error_msg)
                return False, error_msg

            success, message = self.strategy_manager.close_positions(uid, exchange_client)
            if not success:
                self.strategy_error.emit(uid, message)
            return success, message

        except Exception as e:
            error_msg = f"平仓失败: {str(e)}"
            print(f"[StrategyManagerWrapper] {error_msg}")
            print(f"[StrategyManagerWrapper] 错误详情: {traceback.format_exc()}")
            self.strategy_error.emit(uid, error_msg)
            return False, error_msg

    def get_strategy_data(self, uid: str) -> Optional[GridData]:
        return self.strategy_manager.get_strategy_data(uid)

    def get_all_strategy_uids(self) -> List[str]:
        return list(self.strategy_manager._data.keys())

    def is_strategy_running(self, uid: str) -> bool:
        return self.strategy_manager.is_strategy_running(uid)

    def has_running_strategies(self) -> bool:
        return self.strategy_manager.has_running_strategies()

    def load_strategies(self, show_message: bool = True):
        """从文件加载策略数据"""
        def _load():
            try:
                if not os.path.exists(self.data_path):
                    print(f"[StrategyManagerWrapper] 策略配置文件不存在: {self.data_path}")
                    if show_message:
                        self.strategies_loaded.emit("无历史策略数据")
                    return

                print(f"[StrategyManagerWrapper] 开始加载策略配置")
                with open(self.data_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                if not isinstance(data, dict) or 'strategies' not in data:
                    error_msg = "无效的策略数据格式"
                    print(f"[StrategyManagerWrapper] {error_msg}")
                    if show_message:
                        self.load_error.emit(error_msg)
                    return

                # 清空现有数据
                self.strategy_manager._data.clear()
                loaded_count = 0

                for uid, strategy_data in data['strategies'].items():
                    try:
                        # 从JSON创建策略数据
                        grid_data = GridData.from_dict(strategy_data)
                        
                        # 更新状态
                        if grid_data.status == "运行中":
                            grid_data.status = "已停止"  # 启动时重置运行状态
                            
                        self.strategy_manager._data[uid] = grid_data
                        self.strategy_added.emit(uid)
                        loaded_count += 1
                        print(f"[StrategyManagerWrapper] 加载策略 {uid} 成功")

                    except Exception as e:
                        print(f"[StrategyManagerWrapper] 加载策略 {uid} 失败: {e}")
                        print(f"错误详情: {traceback.format_exc()}")
                        continue

                print(f"[StrategyManagerWrapper] 完成加载,共 {loaded_count} 个策略")
                self.strategies_loaded.emit(f"已加载 {loaded_count} 个策略")
                if show_message:
                    self.strategies_loaded.emit(f"已加载 {loaded_count} 个策略")

            except Exception as e:
                error_msg = f"加载策略数据失败: {str(e)}"
                print(f"[StrategyManagerWrapper] {error_msg}")
                print(f"错误详情: {traceback.format_exc()}")
                if show_message:
                    self.load_error.emit(error_msg)
            finally:
                self._load_thread = None

        # 确保不重复加载
        if self._load_thread and self._load_thread.is_alive():
            print("[StrategyManagerWrapper] 已有加载操作在进行中...")
            return
            
        self._load_thread = threading.Thread(
            name=f"Strategy-Load-{id(self)}",
            target=_load,
            daemon=True
        )
        self._load_thread.start()

    def save_strategies(self, show_message: bool = True):
        """保存策略数据到文件"""
        def _save():
            try:
                print(f"[StrategyManagerWrapper] 开始保存策略配置")
                data = {
                    'inst_type': self.inst_type.value,
                    'strategies': {},
                    'running_strategies': []
                }
                
                for uid in list(self.strategy_manager._data.keys()):
                    grid_data = self.strategy_manager.get_strategy_data(uid)
                    if not grid_data:
                        print(f"[StrategyManagerWrapper] 未找到策略数据: {uid}")
                        continue
                        
                    data['strategies'][uid] = grid_data.to_dict()
                    print(f"[StrategyManagerWrapper] 保存策略 {uid}")
                    
                # 确保目录存在
                os.makedirs(os.path.dirname(self.data_path), exist_ok=True)
                
                # 保存到临时文件
                temp_path = f"{self.data_path}.tmp"
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4, ensure_ascii=False, cls=CustomJSONEncoder)
                    
                # 替换原文件
                if os.path.exists(self.data_path):
                    os.replace(temp_path, self.data_path)
                else:
                    os.rename(temp_path, self.data_path)
                
                print(f"[StrategyManagerWrapper] 策略配置已保存到 {self.data_path}")
                if show_message:
                    self.strategies_saved.emit("策略数据保存成功")

            except Exception as e:
                error_msg = f"保存策略数据失败: {str(e)}"
                print(f"[StrategyManagerWrapper] {error_msg}")
                print(f"错误详情: {traceback.format_exc()}")
                if show_message:
                    self.save_error.emit(error_msg)
            finally:
                self._save_thread = None

        # 确保不重复保存
        if self._save_thread and self._save_thread.is_alive():
            print("[StrategyManagerWrapper] 已有保存操作在进行中...")
            return
            
        self._save_thread = threading.Thread(
            name=f"Strategy-Save-{id(self)}",
            target=_save,
            daemon=True
        )
        self._save_thread.start()