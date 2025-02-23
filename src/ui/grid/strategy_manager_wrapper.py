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
        self.strategy_manager.strategy_started.connect(lambda uid: self.strategy_started.emit(uid))
        self.strategy_manager.strategy_stopped.connect(lambda uid: self.strategy_stopped.emit(uid))
        self.strategy_manager.strategy_error.connect(lambda uid, msg: self.strategy_error.emit(uid, msg))
        self.strategy_manager.strategy_status_changed.connect(lambda uid, status: self.strategy_updated.emit(uid))
        self.strategy_manager.save_requested.connect(self.save_strategies)  # 连接新信号

    def _subscribe_pair(self, pair: str, uid: str, client: BaseClient) -> bool:
        """订阅交易对"""
        print(f"\n[StrategyManagerWrapper] 订阅交易对 {pair} - 策略 {uid}")
        if pair not in self._subscriptions:
            self._subscriptions[pair] = set()
            # 首次订阅
            success = client.subscribe_pair(pair, ["ticker"], uid)
            if not success:
                print(f"[StrategyManagerWrapper] 订阅失败")
                return False
        self._subscriptions[pair].add(uid)
        print(f"[StrategyManagerWrapper] 当前订阅: {self._subscriptions}")
        return True
        
    def _unsubscribe_pair(self, pair: str, uid: str, client: BaseClient):
        """取消订阅"""
        print(f"\n[StrategyManagerWrapper] 取消订阅 {pair} - 策略 {uid}")
        if pair not in self._subscriptions:
            return
            
        self._subscriptions[pair].discard(uid)
        if not self._subscriptions[pair]:
            # 没有策略使用该交易对,取消订阅
            client.unsubscribe_pair(pair, ["ticker"], uid)
            del self._subscriptions[pair]
        print(f"[StrategyManagerWrapper] 当前订阅: {self._subscriptions}")

    def _manage_subscription(self, pair: str, uid: str, client: BaseClient, subscribe: bool = True) -> bool:
        try:
            if subscribe:
                if pair not in self._subscriptions:
                    self._subscriptions[pair] = set()
                    # 确保 pair 是字符串，避免传入方法对象
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
        """处理市场数据"""
        try:
            # 转发给策略管理器处理
            self.strategy_manager.process_market_data(pair, data)
        except Exception as e:
            error_msg = f"处理市场数据失败: {str(e)}"
            print(f"[StrategyManagerWrapper] {error_msg}")
            print(f"[StrategyManagerWrapper] 错误详情: {traceback.format_exc()}")
            self.strategy_error.emit("", error_msg)

    def create_strategy(self, symbol_config: SymbolConfig, exchange: str, is_long: bool = True) -> Optional[str]:
        try:
            uid = str(uuid.uuid4())[:8]
            print(f"\n[StrategyManagerWrapper] === 创建策略 {uid} ===")
            print(f"交易对: {symbol_config.pair}")
            print(f"交易所: {exchange}")
            print(f"方向: {'做多' if is_long else '做空'}")
            
            grid_data = self.strategy_manager.create_strategy(
                uid,
                symbol_config,
                exchange,
                self.inst_type,
                is_long
            )
            
            if not grid_data:
                raise ValueError("[StrategyManagerWrapper] 创建策略失败：not grid_data 返回 None")
            grid_data.operations = {"开仓": True, "平仓": True}
            grid_data.status = "已添加"
            
            self.strategy_added.emit(uid)
            self.save_strategies(show_message=False)
            return uid
        except Exception as e:
            error_msg = f"创建策略失败: {str(e)}"
            print(f"[StrategyManagerWrapper] {error_msg}")
            print(f"[StrategyManagerWrapper] 错误详情: {traceback.format_exc()}")
            self.strategy_error.emit("", error_msg)
            return None

    def start_strategy(self, uid: str, exchange_client: BaseClient) -> bool:
        try:
            grid_data = self.strategy_manager.get_strategy_data(uid)
            if not grid_data:
                raise ValueError("策略数据不存在")

            if not self._manage_subscription(grid_data.symbol_config.pair, uid, exchange_client, True):
                raise ValueError("行情订阅失败")

            if not self.strategy_manager.start_strategy(uid, exchange_client):
                self._manage_subscription(grid_data.symbol_config.pair, uid, exchange_client, False)
                raise ValueError("启动策略失败")

            self.strategy_started.emit(uid)
            self.save_strategies(show_message=False)
            return True

        except Exception as e:
            error_msg = f"启动策略失败: {str(e)}"
            print(f"[StrategyManagerWrapper] {error_msg}")
            print(f"[StrategyManagerWrapper] 错误详情: {traceback.format_exc()}")
            self.strategy_error.emit(uid, error_msg)
            return False

    def stop_strategy(self, uid: str, exchange_client: BaseClient) -> bool:
        try:
            grid_data = self.strategy_manager.get_strategy_data(uid)
            if not grid_data:
                raise ValueError("策略数据不存在")

            if not self.strategy_manager.stop_strategy(uid):
                raise ValueError("停止策略失败")

            self._manage_subscription(grid_data.symbol_config.pair, uid, exchange_client, False)
            self.strategy_stopped.emit(uid)
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
                raise ValueError("策略数据不存在")

            if exchange_client and self.strategy_manager.is_strategy_running(uid):
                self._manage_subscription(grid_data.symbol_config.pair, uid, exchange_client, False)

            if self.strategy_manager.delete_strategy(uid):
                self.strategy_deleted.emit(uid)
                self.save_strategies(show_message=False)
                return True
            return False

        except Exception as e:
            error_msg = f"删除策略失败: {str(e)}"
            print(f"[StrategyManagerWrapper] {error_msg}")
            print(f"[StrategyManagerWrapper] 错误详情: {traceback.format_exc()}")
            self.strategy_error.emit(uid, error_msg)
            return False
        
    def stop_all_strategies(self, exchange_client: BaseClient):
        """停止所有运行中的策略"""
        try:
            # 获取所有运行中的策略ID
            running_strategies = [
                uid for uid in self.strategy_manager._data.keys()
                if self.strategy_manager.is_strategy_running(uid)
            ]

            success_count = 0
            for uid in running_strategies:
                if self.stop_strategy(uid, exchange_client):
                    success_count += 1

            return success_count, len(running_strategies)

        except Exception as e:
            error_msg = f"停止策略失败: {str(e)}"
            print(f"[StrategyManagerWrapper] {error_msg}")
            print(f"[StrategyManagerWrapper] 错误详情: {traceback.format_exc()}")
            self.strategy_error.emit("", error_msg)
            return 0, 0

    def close_position(self, uid: str, exchange_client: BaseClient) -> tuple[bool, str]:
        """
        平仓操作
        Args:
            uid: 策略ID
            exchange_client: 交易所客户端
        Returns:
            tuple[bool, str]: (是否成功, 状态消息)
        """
        try:
            grid_data = self.strategy_manager.get_strategy_data(uid)
            if not grid_data:
                raise ValueError("策略数据不存在！")

            # 检查策略是否在运行
            if self.strategy_manager.is_strategy_running(uid):
                raise ValueError("请先停止策略再进行平仓操作！")

            # 调用策略管理器的平仓方法
            success, message = self.strategy_manager.close_positions(uid, exchange_client)
            if success:
                # 保存数据
                self.save_strategies(show_message=False)
            return success, message

        except Exception as e:
            error_msg = f"平仓失败: {str(e)}"
            print(f"[StrategyManagerWrapper] {error_msg}")
            print(f"[StrategyManagerWrapper] 错误详情: {traceback.format_exc()}")
            self.strategy_error.emit(uid, error_msg)
            return False, error_msg

    def get_strategy_data(self, uid: str) -> Optional[GridData]:
        """获取策略数据"""
        return self.strategy_manager.get_strategy_data(uid)

    def get_all_strategy_uids(self) -> List[str]:
        """获取所有策略ID"""
        return list(self.strategy_manager._data.keys())

    def is_strategy_running(self, uid: str) -> bool:
        """检查策略是否在运行"""
        return self.strategy_manager.is_strategy_running(uid)

    def has_running_strategies(self) -> bool:
        """检查是否有运行中的策略"""
        return self.strategy_manager.has_running_strategies()

    def save_strategies(self, show_message: bool = True):
        """保存所有策略数据"""
        def _save():
            try:
                data = {
                    'inst_type': self.inst_type.value,
                    'strategies': {},
                    'running_strategies': []
                }
                
                for uid in list(self.strategy_manager._data.keys()):
                    grid_data = self.strategy_manager.get_strategy_data(uid)
                    if grid_data:
                        data['strategies'][uid] = grid_data.to_dict()
                        if self.strategy_manager.is_strategy_running(uid):
                            data['running_strategies'].append(uid)

                create_file_if_not_exists(self.data_path)
                with open(self.data_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4, ensure_ascii=False, cls=CustomJSONEncoder)
                
                if show_message:
                    self.strategies_saved.emit("策略数据已成功保存！")
                print(f"[StrategyManagerWrapper] 策略数据已保存到 {self.data_path}")

            except Exception as e:
                error_msg = f"保存策略数据失败: {str(e)}"
                print(f"[StrategyManagerWrapper] {error_msg}")
                if show_message:
                    self.save_error.emit(error_msg)
            finally:
                self._save_thread = None

        if self._save_thread and self._save_thread.is_alive():
            print("[StrategyManagerWrapper] 已有保存操作在进行中...")
            return
        self._save_thread = threading.Thread(
            name=f"Strategy-Save-{id(self)}",
            target=_save,
            daemon=True
        )
        self._save_thread.start()

    def load_strategies(self, exchange_client: Optional[BaseClient] = None, show_message: bool = True):
        """加载策略数据并恢复运行状态"""
        def _load():
            try:
                if not os.path.exists(self.data_path):
                    if show_message:
                        self.strategies_loaded.emit("无历史策略数据，已初始化空配置")
                    return

                with open(self.data_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                if not isinstance(data, dict) or 'strategies' not in data:
                    raise ValueError("无效的策略数据格式")

                loaded_count = 0
                running_uids = set(data.get('running_strategies', []))
                
                # 先清除现有数据
                self.strategy_manager.stop_all_strategies()
                for uid in list(self.strategy_manager._data.keys()):
                    self.strategy_manager.delete_strategy(uid)

                for uid, strategy_data in data['strategies'].items():
                    try:
                        symbol_config = SymbolConfig(
                            symbol=strategy_data["symbol_config"]["symbol"],
                            pair=strategy_data["symbol_config"]["pair"],
                            base_coin=strategy_data["symbol_config"]["base_coin"],
                            quote_coin=strategy_data["symbol_config"]["quote_coin"],
                            base_precision=strategy_data["symbol_config"]["base_precision"],
                            quote_precision=strategy_data["symbol_config"]["quote_precision"],
                            price_precision=strategy_data["symbol_config"]["price_precision"],
                            min_base_amount=Decimal(strategy_data["symbol_config"]["min_base_amount"]),
                            min_quote_amount=Decimal(strategy_data["symbol_config"]["min_quote_amount"])
                        )
                        
                        grid_data = self.strategy_manager.create_strategy(
                            uid,
                            symbol_config,
                            strategy_data["exchange"],
                            self.inst_type
                        )

                        if grid_data:
                            grid_data = GridData.from_dict(strategy_data)
                            self.strategy_manager._data[uid] = grid_data
                            trader = self.strategy_manager._strategies.get(uid)
                            if trader:
                                trader.error_occurred.connect(self.strategy_manager._handle_strategy_error)

                            self.strategy_added.emit(uid)
                            loaded_count += 1

                            # 恢复运行状态
                            if uid in running_uids and exchange_client:
                                self.start_strategy(uid, exchange_client)

                    except Exception as e:
                        print(f"[StrategyManagerWrapper] 加载策略 {uid} 失败: {e}")
                        continue

                if show_message and loaded_count > 0:
                    self.strategies_loaded.emit(f"成功加载 {loaded_count} 个策略！")

            except Exception as e:
                error_msg = f"加载策略数据失败: {str(e)}"
                print(f"[StrategyManagerWrapper] {error_msg}")
                if show_message:
                    self.load_error.emit(error_msg)
            finally:
                self._load_thread = None

        if self._load_thread and self._load_thread.is_alive():
            return
        self._load_thread = threading.Thread(
            name=f"GridStrategy-Load-{id(self)}",
            target=_load,
            daemon=True
        )
        self._load_thread.start()