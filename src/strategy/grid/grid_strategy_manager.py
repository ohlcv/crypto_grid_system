# src/strategy/grid/grid_strategy_manager.py

import traceback
from typing import Dict, Optional
from decimal import Decimal
import threading
from datetime import datetime
from qtpy.QtCore import QObject, Signal

from src.exchange.base_client import BaseClient
from .grid_core import GridData
from .grid_trader import GridTrader

class GridStrategyManager(QObject):
    """网格策略管理器"""
    
    # 信号定义
    strategy_started = Signal(str)  # uid
    strategy_stopped = Signal(str)  # uid
    strategy_error = Signal(str, str)  # uid, error_message
    strategy_status_changed = Signal(str, str)  # uid, status

    def __init__(self):
        super().__init__()
        self._strategies: Dict[str, GridTrader] = {}  # uid -> GridTrader
        self._data: Dict[str, GridData] = {}  # uid -> GridData
        self._lock = threading.Lock()

    def create_strategy(self, uid: str, pair: str, exchange: str, inst_type: str) -> GridData:
        """创建新策略"""
        with self._lock:
            if uid in self._data:
                raise ValueError(f"Strategy {uid} already exists")

        print(f"[GridStrategyManager] Creating strategy: {uid} - {pair}")
        grid_data = GridData(uid, pair, exchange, inst_type)
        self._data[uid] = grid_data
        return grid_data

    def start_strategy(self, uid: str, exchange_client: BaseClient) -> bool:
        """启动策略"""
        # with self._lock:
        print(f"\n[GridStrategyManager] === 开始启动策略 === {uid}")
        print(f"[GridStrategyManager] 当前运行策略数: {len(self._strategies)}")
        print(f"[GridStrategyManager] 当前策略数据数: {len(self._data)}")
        # 检查策略数据是否存在
        grid_data = self._data.get(uid)
        if not grid_data:
            print(f"[GridStrategyManager] 策略 {uid} 数据不存在")
            return False
        # 检查策略是否已经在运行
        existing_trader = self._strategies.get(uid)
        if existing_trader:
            if existing_trader._running:
                print(f"[GridStrategyManager] 策略 {uid} 已在运行中")
                return False
            else:
                # 如果策略存在但没在运行，先清理掉
                print(f"[GridStrategyManager] 清理未运行的策略实例")
                del self._strategies[uid]
        try:
            print(f"[GridStrategyManager] 创建策略执行器...")
            trader = GridTrader(grid_data, exchange_client)
            print(f"[GridStrategyManager] 连接信号...")
            trader.status_changed.connect(self._handle_status_changed)
            trader.error_occurred.connect(self._handle_error)
            print(f"[GridStrategyManager] 启动执行器...")
            if not trader.start():
                print(f"[GridStrategyManager] 执行器启动失败")
                return False
            # 保存到运行列表
            self._strategies[uid] = trader
            # 发送启动信号
            self.strategy_started.emit(uid)
            print(f"[GridStrategyManager] 策略启动成功: {uid}")
            return True
        except Exception as e:
            error_msg = f"启动策略失败: {str(e)}"
            print(f"[GridStrategyManager] 错误: {error_msg}")
            print(f"[GridStrategyManager] 详细信息: {traceback.format_exc()}")
            self.strategy_error.emit(uid, error_msg)
            # 确保清理失败的策略实例
            if uid in self._strategies:
                del self._strategies[uid]
            return False

    def process_market_data(self, pair: str, data: dict):
        """处理市场数据"""
        try:
            normalized_pair = pair.replace('/', '')
            # print(f"\n[GridStrategyManager] === 处理市场数据 === {normalized_pair}")
            # print(f"[GridStrategyManager] 原始数据: {data}")
            
            # 找到相关策略
            affected_strategies = []
            for uid, grid_data in self._data.items():
                grid_pair = grid_data.pair.replace('/', '')
                # print(f"[GridStrategyManager] 检查策略 {uid}: {grid_pair}")
                # print(f"  策略交易对: {grid_pair}")
                # print(f"  行情交易对: {normalized_pair}")
                if grid_pair == normalized_pair:
                    affected_strategies.append(uid)
            
            # print(f"[GridStrategyManager] 行情交易对: {normalized_pair} 找到相关策略: {affected_strategies}")
            for uid in affected_strategies:
                try:
                    grid_data = self._data[uid]
                    # print(f"  交易对: {normalized_pair} {uid}")
                    # print(f"  最新价格: {data.get('lastPr')}")
                    # print(f"  时间戳: {data.get('ts')}")
                    
                    grid_data.update_market_data(data)
                except Exception as e:
                    print(f"[GridStrategyManager] 更新策略 {uid} 失败: {e}")
                    print(f"[GridStrategyManager] 错误详情: {traceback.format_exc()}")
                    
        except Exception as e:
            print(f"[GridStrategyManager] 处理市场数据错误: {e}")
            print(f"[GridStrategyManager] 错误详情: {traceback.format_exc()}")

    def print_running_strategies(self):
        """打印所有运行中的策略信息"""
        print("\n[GridStrategyManager] === 运行中的策略 ===")
        for uid, trader in self._strategies.items():
            print(f"策略ID: {uid}")
            print(f"  交易对: {trader.grid_data.pair}")
            print(f"  方向: {trader.grid_data.direction}")
            print(f"  线程状态: {'运行中' if trader._thread and trader._thread.is_alive() else '已停止'}")
            if trader._thread:
                print(f"  线程ID: {trader._thread.ident}")
                print(f"  线程名称: {trader._thread.name}")
            print(f"  运行标志: {trader._running}")
        print("=== 策略信息结束 ===\n")

    def delete_strategy(self, uid: str) -> bool:
        """删除策略"""
        print(f"\n[GridStrategyManager] === 删除策略 === {uid}")
        self.print_running_strategies()  # 删除前打印

        if self.is_strategy_running(uid):
            print(f"[GridStrategyManager] 策略 {uid} 正在运行，先停止它")
            if not self.stop_strategy(uid):
                print(f"[GridStrategyManager] 停止策略失败")
                return False
        with self._lock:
            # 确保策略已经停止运行
            if uid in self._strategies:
                trader = self._strategies[uid]
                if trader._thread and trader._thread.is_alive():
                    print(f"[GridStrategyManager] 等待策略线程结束")
                    trader._thread.join(timeout=5)  # 等待线程结束，最多等5秒
                del self._strategies[uid]
            # 删除策略数据
            if uid in self._data:
                del self._data[uid]
                print(f"[GridStrategyManager] 策略 {uid} 已删除")
                self.print_running_strategies()  # 删除后打印
                return True
            return False

    def stop_strategy(self, uid: str) -> bool:
        """暂停策略运行"""
        print(f"\n[GridStrategyManager] === 暂停策略运行 === {uid}")
        with self._lock:
            if uid not in self._strategies:
                print(f"[GridStrategyManager] 策略 {uid} 不在运行中")
                return True  # 如果策略本来就没运行，认为停止成功
            try:
                trader = self._strategies[uid]
                success = trader.stop()
                if success:
                    del self._strategies[uid]  # 从运行列表中移除
                    if uid in self._data:
                        self._data[uid].row_dict["运行状态"] = "已暂停"
                    self.strategy_stopped.emit(uid)
                    print(f"[GridStrategyManager] 策略 {uid} 已暂停")
                return success

            except Exception as e:
                print(f"[GridStrategyManager] 暂停策略失败: {e}")
                return False
        
    def _handle_strategy_error(self, uid: str, error_msg: str):
        """处理策略错误"""
        print(f"\n[GridStrategyManager] === 处理策略错误 === {uid}")
        print(f"[GridStrategyManager] 错误信息: {error_msg}")
        with self._lock:
            # 更新状态并暂停策略
            if uid in self._data:
                self._data[uid].row_dict["运行状态"] = "错误停止"
            
            # 如果策略还在运行，停止它
            if uid in self._strategies:
                trader = self._strategies[uid]
                trader.stop()
                del self._strategies[uid]
            self.strategy_error.emit(uid, error_msg)

    def stop_all_strategies(self):
        """停止所有策略"""
        # with self._lock:
        print("[GridStrategyManager] 停止所有策略")
        for uid in list(self._strategies.keys()):
            try:
                print(f"[GridStrategyManager] 停止策略: {uid}")
                # 设置较短的超时时间
                if not self.stop_strategy(uid):
                    print(f"[GridStrategyManager] 策略 {uid} 停止失败")
            except Exception as e:
                print(f"[GridStrategyManager] 停止策略 {uid} 时出错: {e}")
                continue

    def get_strategy_data(self, uid: str) -> Optional[GridData]:
        """获取策略数据"""
        return self._data.get(uid)

    def update_grid_config(self, uid: str, level: int, config: dict) -> bool:
        """更新网格配置"""
        # with self._lock:
        if uid not in self._data:
            return False

        print(f"[GridStrategyManager] Updating grid config: {uid} - Level {level}")
        try:
            grid_data = self._data[uid]
            grid_data.update_level(level, config)
            return True
        except Exception as e:
            print(f"[GridStrategyManager] Failed to update grid config: {e}")
            return False

    def is_strategy_running(self, uid: str) -> bool:
        """检查策略是否正在运行"""
        # with self._lock:
        if uid in self._strategies:
            trader = self._strategies[uid]
            return trader._running
        return False

    def has_running_strategies(self) -> bool:
        """检查是否有运行中的策略"""
        return bool(self._strategies)

    def get_all_running_pairs(self) -> list:
        """获取所有运行中策略的交易对"""
        return [
            self._data[uid].pair 
            for uid in self._strategies.keys()
        ]

    def get_running_statistics(self) -> dict:
        """获取运行中策略的统计数据"""
        # with self._lock:
        stats = {
            "total_running": len(self._strategies),
            "pairs": self.get_all_running_pairs(),
            "total_investment": Decimal('0'),
            "total_profit": Decimal('0'),
            "last_update": datetime.now().isoformat()
        }
        
        for uid, trader in self._strategies.items():
            grid_data = self._data[uid]
            # 计算投资金额和盈亏
            for level_config in grid_data.grid_levels.values():
                if level_config.is_filled:
                    stats["total_investment"] += level_config.invest_amount
                    if grid_data.last_price and level_config.filled_price:
                        profit = (grid_data.last_price - level_config.filled_price) * level_config.filled_amount
                        if not grid_data.is_long():
                            profit = -profit
                        stats["total_profit"] += profit
        return stats

    def _handle_status_changed(self, uid: str, status: str):
        """处理策略状态变化"""
        self.strategy_status_changed.emit(uid, status)

    def _handle_error(self, uid: str, error_msg: str):
        """处理策略错误"""
        print(f"[GridStrategyManager] Strategy error - {uid}: {error_msg}")
        self.strategy_error.emit(uid, error_msg)