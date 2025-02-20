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

from src.exchange.base_client import ExchangeType, BaseClient
from src.exchange.client_factory import ExchangeClientFactory
from src.strategy.grid.grid_core import GridData, GridDirection
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
    data_saved = Signal(str)  # message
    data_loaded = Signal(str)  # message
    save_error = Signal(str)  # error_message
    load_error = Signal(str)  # error_message

    def __init__(self, inst_type: ExchangeType, client_factory: ExchangeClientFactory):
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
        self.strategy_manager.strategy_started.connect(
            lambda uid: self.strategy_started.emit(uid)
        )
        self.strategy_manager.strategy_stopped.connect(
            lambda uid: self.strategy_stopped.emit(uid)
        )
        self.strategy_manager.strategy_error.connect(
            lambda uid, msg: self.strategy_error.emit(uid, msg)
        )
        self.strategy_manager.strategy_status_changed.connect(
            lambda uid, status: self.strategy_updated.emit(uid)
        )

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

    def create_strategy(self, pair: str, exchange: str, is_long: bool = True, pair_data: dict = None) -> Optional[str]:
        """创建新策略"""
        try:
            # 创建唯一ID
            uid = str(uuid.uuid4())[:8]
            
            print(f"\n[StrategyManagerWrapper] === 创建策略 {uid} ===")
            print(f"交易对: {pair}")
            print(f"交易所: {exchange}")
            print(f"方向: {'做多' if is_long else '做空'}")
            if pair_data:
                print(f"交易对参数: {pair_data}")
            
            # 创建策略
            grid_data = self.strategy_manager.create_strategy(
                uid,
                pair,
                exchange,
                self.inst_type
            )
            
            if not grid_data:
                raise ValueError("创建策略失败")

            # 设置方向 - 统一使用枚举
            grid_data.set_direction(
                is_long=(self.inst_type == ExchangeType.SPOT or is_long)
            )
            
            # 初始化操作状态
            grid_data.row_dict["操作"] = {"开仓": True, "平仓": True}
            
            # 缓存交易对参数
            if pair_data:
                print("\n[StrategyManagerWrapper] === 缓存交易参数 ===")
                if self.inst_type == ExchangeType.SPOT:
                    grid_data.quantity_precision = int(pair_data.get('quantityPrecision', 4))
                    grid_data.price_precision = int(pair_data.get('pricePrecision', 2))
                    grid_data.min_trade_amount = Decimal(str(pair_data.get('minTradeAmount', '0')))
                    grid_data.min_trade_value = Decimal(str(pair_data.get('minTradeUSDT', '5')))
                    print(f"现货参数:")
                    print(f"  数量精度: {grid_data.quantity_precision}")
                    print(f"  价格精度: {grid_data.price_precision}")
                    print(f"  最小数量: {grid_data.min_trade_amount}")
                    print(f"  最小金额: {grid_data.min_trade_value}")
                else:
                    grid_data.quantity_precision = int(pair_data.get('volumePlace', 4))
                    grid_data.price_precision = int(pair_data.get('pricePlace', 2))
                    grid_data.min_trade_amount = Decimal(str(pair_data.get('minTradeNum', '0')))
                    grid_data.min_trade_value = Decimal(str(pair_data.get('minTradeUSDT', '5')))
                    print(f"合约参数:")
                    print(f"  数量精度: {grid_data.quantity_precision}")
                    print(f"  价格精度: {grid_data.price_precision}")
                    print(f"  最小数量: {grid_data.min_trade_amount}")
                    print(f"  最小金额: {grid_data.min_trade_value}")
            else:
                print("[StrategyManagerWrapper] 警告: 未提供交易对参数！")
            
            # 发送信号
            self.strategy_added.emit(uid)
            
            # 保存数据
            self.save_strategies(show_message=False)
            
            return uid
                
        except Exception as e:
            error_msg = f"创建策略失败: {str(e)}"
            print(f"[StrategyManagerWrapper] {error_msg}")
            print(f"[StrategyManagerWrapper] 错误详情: {traceback.format_exc()}")
            self.strategy_error.emit("", error_msg)
            return None

    def _manage_subscription(self, pair: str, uid: str, client: BaseClient, subscribe: bool = True) -> bool:
        """管理订阅状态"""
        try:
            if subscribe:
                # 订阅逻辑 
                if pair not in self._subscriptions:
                    self._subscriptions[pair] = set()
                    success = client.subscribe_pair(pair, ["ticker"], uid)
                    if not success:
                        return False
                self._subscriptions[pair].add(uid)
            else:
                # 取消订阅逻辑
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

    def start_strategy(self, uid: str, exchange_client: BaseClient) -> bool:
        try:
            grid_data = self.strategy_manager.get_strategy_data(uid)
            if not grid_data:
                raise ValueError("策略数据不存在")

            # 使用统一的订阅管理
            if not self._manage_subscription(grid_data.pair, uid, exchange_client, True):
                raise ValueError("行情订阅失败")

            if not self.strategy_manager.start_strategy(uid, exchange_client):
                self._manage_subscription(grid_data.pair, uid, exchange_client, False)
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
        """停止策略"""
        try:
            grid_data = self.strategy_manager.get_strategy_data(uid)
            if not grid_data:
                raise ValueError("策略数据不存在")

            # 停止策略
            if not self.strategy_manager.stop_strategy(uid):
                raise ValueError("停止策略失败")

            # 取消订阅
            self._manage_subscription(grid_data.pair, uid, exchange_client, False)

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
        """删除策略"""
        try:
            grid_data = self.strategy_manager.get_strategy_data(uid)
            if not grid_data:
                raise ValueError("策略数据不存在")

            # 如果策略正在运行,先取消订阅
            if exchange_client and self.strategy_manager.is_strategy_running(uid):
                self._manage_subscription(grid_data.pair, uid, exchange_client, False)

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

    def close_position(self, uid: str, exchange_client: BaseClient) -> bool:
        """
        平仓操作
        
        Args:
            uid: 策略ID
            exchange_client: 交易所客户端
            
        Returns:
            bool: 是否平仓成功
        """
        try:
            grid_data = self.strategy_manager.get_strategy_data(uid)
            if not grid_data:
                raise ValueError("策略数据不存在！")

            # 检查策略是否在运行
            if self.strategy_manager.is_strategy_running(uid):
                raise ValueError("请先停止策略再进行平仓操作！")

            # 调用策略管理器的平仓方法
            success = self.strategy_manager.close_positions(uid, exchange_client)
            if success:
                # 保存数据
                self.save_strategies(show_message=False)
            return success

        except Exception as e:
            error_msg = f"平仓失败: {str(e)}"
            print(f"[StrategyManagerWrapper] {error_msg}")
            print(f"[StrategyManagerWrapper] 错误详情: {traceback.format_exc()}")
            self.strategy_error.emit(uid, error_msg)
            return False

    def save_strategies(self, show_message: bool = True):
        def _save():
            try:
                data = {
                    'inst_type': self.inst_type.value,  # 已经是字符串
                    'strategies': {},
                    'running_strategies': []
                }
                
                for uid in list(self.strategy_manager._data.keys()):
                    grid_data = self.strategy_manager.get_strategy_data(uid)
                    if grid_data:
                        original_status = grid_data.row_dict.get("运行状态", "")
                        grid_data.row_dict["运行状态"] = "已保存"
                        data['strategies'][uid] = grid_data.to_dict()
                        grid_data.row_dict["运行状态"] = original_status
                        if self.strategy_manager.is_strategy_running(uid):
                            data['running_strategies'].append(uid)

                # 使用自定义编码器保存到文件
                create_file_if_not_exists(self.data_path)
                with open(self.data_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4, ensure_ascii=False, cls=CustomJSONEncoder)
                
                if show_message:
                    self.data_saved.emit("数据已成功保存！")

            except Exception as e:
                error_msg = f"保存数据失败: {str(e)}"
                print(f"[StrategyManagerWrapper] {error_msg}")
                print(f"[StrategyManagerWrapper] 错误详情: {traceback.format_exc()}")
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
        """
        加载策略数据
        
        Args:
            exchange_client: 可选的交易所客户端实例，用于恢复运行中的策略
            show_message: 是否显示加载消息
        """
        def _load():
            try:
                if not os.path.exists(self.data_path):
                    if show_message:
                        self.data_loaded.emit("无历史数据，已初始化空配置")
                    return

                # 读取数据文件
                with open(self.data_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    print(f"[StrategyManagerWrapper] 加载文件内容:\n{content}")
                    if not content:  # 空文件
                        if show_message:
                            self.data_loaded.emit("无历史数据，已初始化空配置")
                        return
                    data = json.loads(content)

                if not isinstance(data, dict) or 'strategies' not in data:
                    raise ValueError("无效的数据格式")

                # 恢复所有策略数据
                loaded_count = 0
                for uid, strategy_data in data['strategies'].items():
                    try:
                        print(f"\n[StrategyManagerWrapper] === 加载策略 {uid} ===")

                        # 获取方向
                        direction = strategy_data["direction"].upper()
                        is_long = direction == "LONG"
                        # 创建策略
                        grid_data = self.strategy_manager.create_strategy(
                            uid,
                            strategy_data["pair"],
                            strategy_data["exchange"],
                            strategy_data["inst_type"],
                            is_long  # 传递方向参数
                        )

                        if grid_data:
                            # 设置方向 - 直接使用枚举
                            grid_data.direction = GridDirection[direction]
                            grid_data.row_dict["方向"] = direction
                            
                            # 恢复实现盈亏值
                            original_profit = Decimal(str(strategy_data.get('total_realized_profit', '0')))
                            grid_data.total_realized_profit = original_profit
                            
                            # 恢复网格配置
                            for level_str, config in strategy_data.get("grid_levels", {}).items():
                                level = int(level_str)
                                # 构建配置数据
                                config_data = {
                                    "间隔%": config["间隔%"],
                                    "开仓反弹%": config["开仓反弹%"],
                                    "平仓反弹%": config["平仓反弹%"],
                                    "止盈%": config["止盈%"],
                                    "成交额": config["成交额"]
                                }
                                # 如果有成交信息则添加
                                if config["已开仓"]:
                                    config_data.update({
                                        "filled_amount": config["成交量"],
                                        "filled_price": config["开仓价"],
                                        "filled_time": datetime.fromisoformat(config["开仓时间"]) if config["开仓时间"] else None,
                                        "is_filled": config["已开仓"],
                                        "order_id": config["order_id"]
                                    })
                                grid_data.update_level(level, config_data)
                                
                            # 恢复UI显示数据
                            grid_data.row_dict.update(strategy_data["row_dict"])
                            # 确保实现盈亏正确显示
                            grid_data.row_dict["实现盈亏"] = str(original_profit)
                            
                            # 设置初始状态
                            grid_status = grid_data.get_grid_status()
                            filled_levels = sum(1 for config in grid_data.grid_levels.values() 
                                           if config.is_filled)
                            
                            initial_status = "已添加"  # 默认状态
                            if filled_levels > 0:
                                position_value = grid_data.row_dict.get("持仓价值")
                                if position_value and float(position_value.replace(",", "")) > 0:
                                    initial_status = "已停止"  # 有持仓但策略未运行
                                else:
                                    initial_status = "已平仓"  # 无持仓
                            grid_data.row_dict["运行状态"] = initial_status
                            
                            # 发送策略添加信号
                            self.strategy_added.emit(uid)
                            loaded_count += 1
                            
                    except Exception as e:
                        print(f"[StrategyManagerWrapper] 加载策略 {uid} 失败: {e}")
                        print(f"[StrategyManagerWrapper] 错误详情: {traceback.format_exc()}")
                        continue

                if show_message and loaded_count > 0:
                    self.data_loaded.emit(f"成功加载 {loaded_count} 个策略！")

            except Exception as e:
                error_msg = f"加载数据失败: {str(e)}"
                print(f"[StrategyManagerWrapper] {error_msg}")
                print(f"[StrategyManagerWrapper] 错误详情: {traceback.format_exc()}")
                if show_message:
                    self.load_error.emit(error_msg)
            finally:
                self._load_thread = None

        # 如果已有加载线程在运行，等待其完成
        if self._load_thread and self._load_thread.is_alive():
            return
            
        # 创建新的加载线程
        self._load_thread = threading.Thread(
            name=f"GridStrategy-Load-{id(self)}",
            target=_load,
            daemon=True
        )
        self._load_thread.start()

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