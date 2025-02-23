# src/strategy/grid/grid_strategy_manager.py

import traceback
from typing import Dict, Optional
from decimal import Decimal
import threading
from datetime import datetime
from qtpy.QtCore import QObject, Signal

from src.exchange.base_client import BaseClient, InstType, PositionSide, SymbolConfig, TickerData
from src.utils.common.tools import find_value
from .grid_core import GridData
from .strategy_interface import StrategyManagerInterface

class Signals(QObject):
    """单独的信号类，用于发射信号"""
    strategy_started = Signal(str)
    strategy_stopped = Signal(str)
    strategy_error = Signal(str, str)
    strategy_status_changed = Signal(str, str)
    save_requested = Signal(str)

class GridStrategyManager(StrategyManagerInterface):
    """网格策略管理器"""

    def __init__(self):
        super().__init__()
        self._strategies: Dict[str, 'GridTrader'] = {}  # 类型提示，避免直接导入
        self._data: Dict[str, GridData] = {}  # uid -> GridData
        self._lock = threading.Lock()
        self.signals = Signals()  # 组合一个信号对象

    def _handle_save_request(self, uid: str):
        print(f"[GridStrategyManager] 收到保存请求: {uid}")
        self.signals.save_requested.emit(uid)

    def create_strategy(self, uid: str, symbol_config: SymbolConfig, exchange: str, inst_type: InstType, is_long: bool = True) -> Optional[GridData]:
        print(f"\n[GridStrategyManager] {inst_type} === 创建新策略 === {uid}")
        print(f"[GridStrategyManager] 交易对: {symbol_config.pair}")
        
        with self._lock:
            if uid in self._data:
                # error_msg = f"策略 {uid} 已存在"
                # print(f"[GridStrategyManager] {error_msg}")
                # self.signals.strategy_error.emit(uid, error_msg)
                return None

            try:
                print(f"[GridStrategyManager] 初始化策略数据...")
                grid_data = GridData(uid, symbol_config, exchange, inst_type)
                
                print(f"[GridStrategyManager] 设置交易方向...")
                grid_data.set_direction(is_long=(inst_type == InstType.SPOT or is_long))
                
                print(f"[GridStrategyManager] 创建策略实例...")
                from .grid_trader import GridTrader  # 动态导入
                trader = GridTrader(self, uid)
                trader.save_requested.connect(self._handle_save_request)
                trader.error_occurred.connect(self._handle_strategy_error)
                self._data[uid] = grid_data
                self._strategies[uid] = trader
                
                print(f"[GridStrategyManager] 策略实例创建成功: {uid}")
                return grid_data
                
            except Exception as e:
                error_msg = f"创建策略失败: {str(e)}"
                print(f"[GridStrategyManager] {error_msg}")
                print(f"[GridStrategyManager] 错误详情: {traceback.format_exc()}")
                self.signals.strategy_error.emit(uid, error_msg)
                if uid in self._data:
                    del self._data[uid]
                return None

    def start_strategy(self, uid: str, exchange_client: BaseClient) -> bool:
        print(f"\n[GridStrategyManager] === 启动策略运行 === {uid}")
        try:
            grid_data = self._data.get(uid)
            if not grid_data:
                error_msg = "未找到策略数据"
                print(f"[GridStrategyManager] {error_msg}")
                self.signals.strategy_error.emit(uid, error_msg)
                return False
                
            trader = self._strategies.get(uid)
            if trader and trader._running:
                error_msg = "策略已在运行中"
                print(f"[GridStrategyManager] {error_msg}")
                self.signals.strategy_error.emit(uid, error_msg)
                return False

            if not trader:
                print(f"[GridStrategyManager] 创建新的trader实例...")
                from .grid_trader import GridTrader  # 动态导入
                trader = GridTrader(self, uid)
                trader.error_occurred.connect(self._handle_strategy_error)
                self._strategies[uid] = trader
            
            print(f"[GridStrategyManager] 设置交易所客户端...")
            trader.set_client(exchange_client)
            
            original_profit = grid_data.total_realized_profit
            print(f"[GridStrategyManager] 保持原有实现盈亏: {original_profit}")
            
            if trader.start():
                self.signals.strategy_started.emit(uid)
                grid_data.total_realized_profit = original_profit
                grid_data.status = "运行中"
                grid_data.data_updated.emit(uid)
                print(f"[GridStrategyManager] 策略启动完成: {uid}")
                return True
                
            error_msg = "策略启动失败（GridTrader.start 返回 False）"
            print(f"[GridStrategyManager] {error_msg}")
            self.signals.strategy_error.emit(uid, error_msg)
            return False
                
        except Exception as e:
            error_msg = f"启动策略失败: {str(e)}"
            print(f"[GridStrategyManager] {error_msg}")
            print(f"[GridStrategyManager] 错误详情: {traceback.format_exc()}")
            self.signals.strategy_error.emit(uid, error_msg)
            return False

    def stop_strategy(self, uid: str) -> bool:
        print(f"\n[GridStrategyManager] === 暂停策略运行 === {uid}")
        try:
            trader = self._strategies.get(uid)
            if not trader:
                error_msg = "未找到策略实例"
                print(f"[GridStrategyManager] {error_msg}")
                self.signals.strategy_error.emit(uid, error_msg)
                return False
                
            if not trader.stop():
                error_msg = "停止策略失败（GridTrader.stop 返回 False）"
                print(f"[GridStrategyManager] {error_msg}")
                self.signals.strategy_error.emit(uid, error_msg)
                return False
                
            self.signals.strategy_stopped.emit(uid)
            print(f"[GridStrategyManager] 策略已暂停运行")
            return True
            
        except Exception as e:
            error_msg = f"停止策略失败: {str(e)}"
            print(f"[GridStrategyManager] {error_msg}")
            print(f"[GridStrategyManager] 错误详情: {traceback.format_exc()}")
            self.signals.strategy_error.emit(uid, error_msg)
            return False

    def delete_strategy(self, uid: str) -> bool:
        print(f"\n[GridStrategyManager] === 删除策略 === {uid}")
        try:
            with self._lock:
                trader = self._strategies.get(uid)
                grid_data = self._data.get(uid)
                
                if not trader and not grid_data:
                    error_msg = "未找到策略实例或数据"
                    print(f"[GridStrategyManager] {error_msg}")
                    self.signals.strategy_error.emit(uid, error_msg)
                    return False

                # 如果策略正在运行，先停止
                if trader and trader._running:
                    print(f"[GridStrategyManager] 策略 {uid} 正在运行，先停止它")
                    if not self.stop_strategy(uid):
                        error_msg = "停止策略失败，无法删除"
                        print(f"[GridStrategyManager] {error_msg}")
                        self.signals.strategy_error.emit(uid, error_msg)
                        return False

                # 清理策略实例
                if trader:
                    print(f"[GridStrategyManager] 清理策略实例: {uid}")
                    if trader._thread and trader._thread.is_alive():
                        print(f"[GridStrategyManager] 发现活动线程: {trader._thread.name} (ID: {trader._thread.ident})")
                        trader._stop_flag.set()
                        trader._running = False
                        trader._thread.join(timeout=2)
                        if trader._thread.is_alive():
                            error_msg = "线程未能及时终止"
                            print(f"[GridStrategyManager] {error_msg}")
                            self.signals.strategy_error.emit(uid, error_msg)
                            return False
                        print(f"[GridStrategyManager] 线程已终止")

                    if trader.client:
                        print(f"[GridStrategyManager] 清理客户端连接...")
                        try:
                            trader.client.order_updated.disconnect(trader._on_order_update)
                        except TypeError:
                            pass
                        trader.client = None
                        
                    del self._strategies[uid]
                    print(f"[GridStrategyManager] 策略实例已删除")

                # 清理策略数据
                if grid_data:
                    print(f"[GridStrategyManager] 清理策略数据: {uid}")
                    try:
                        grid_data.data_updated.disconnect()
                    except TypeError:
                        pass
                    del self._data[uid]
                    print(f"[GridStrategyManager] 策略数据已删除")
                
                return True
            
        except Exception as e:
            error_msg = f"删除策略失败: {str(e)}"
            print(f"[GridStrategyManager] {error_msg}")
            print(f"[GridStrategyManager] 错误详情: {traceback.format_exc()}")
            self.signals.strategy_error.emit(uid, error_msg)
            return False

    def process_market_data(self, pair: str, data: dict):
        try:
            # print(f"[GridStrategyManager] 处理市场数据 - pair: {pair}, data: {data}")
            if not isinstance(data, dict):
                error_msg = f"无效的市场数据格式: {data}"
                print(f"[GridStrategyManager] {error_msg}")
                self.signals.strategy_error.emit("", error_msg)
                return

            normalized_pair = pair.replace('/', '')
            running_strategies = set(self._strategies.keys())
            if not running_strategies:
                return

            affected_strategies = []
            for uid, grid_data in self._data.items():
                if uid not in running_strategies:
                    continue
                grid_pair = grid_data.symbol_config.pair.replace('/', '')
                if grid_pair == normalized_pair:
                    affected_strategies.append(uid)

            if affected_strategies:
                ticker = TickerData(
                    instId=normalized_pair,
                    lastPr=Decimal(str(find_value(data, "lastPr") or '0')),
                    ts=int(find_value(data, "ts") or 0)
                )
                for uid in affected_strategies:
                    grid_data = self._data[uid]
                    trader = self._strategies.get(uid)
                    if not grid_data or not trader or not trader._running:
                        continue
                    if not grid_data.operations.get("开仓", True) and not grid_data.operations.get("平仓", True):
                        continue
                    grid_data.update_market_data(ticker)
                    # print(f"[GridStrategyManager] 更新 {uid} 的 ticker_data: {ticker.lastPr}")
        except Exception as e:
            error_msg = f"处理市场数据失败: {str(e)}"
            print(f"[GridStrategyManager] {error_msg}")
            self.signals.strategy_error.emit("", error_msg)

    def print_running_strategies(self):
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
        
    def _handle_strategy_error(self, uid: str, error_msg: str):
        print(f"\n[GridStrategyManager] === 处理策略错误 === {uid}")
        print(f"[GridStrategyManager] 错误信息: {error_msg}")
        with self._lock:
            if uid in self._data:
                self._data[uid].status = "错误停止"
            if uid in self._strategies:
                trader = self._strategies[uid]
                trader.stop()
                del self._strategies[uid]
            self.signals.strategy_error.emit(uid, error_msg)

    def stop_all_strategies(self):
        print("[GridStrategyManager] 停止所有策略")
        try:
            for uid in list(self._strategies.keys()):
                print(f"[GridStrategyManager] 停止策略: {uid}")
                if not self.stop_strategy(uid):
                    print(f"[GridStrategyManager] 策略 {uid} 停止失败")
        except Exception as e:
            error_msg = f"停止所有策略失败: {str(e)}"
            print(f"[GridStrategyManager] {error_msg}")
            print(f"[GridStrategyManager] 错误详情: {traceback.format_exc()}")
            self.signals.strategy_error.emit("", error_msg)

    def get_strategy_data(self, uid: str) -> Optional[GridData]:
        return self._data.get(uid)

    def update_grid_config(self, uid: str, level: int, config: dict) -> bool:
        if uid not in self._data:
            error_msg = f"未找到策略 {uid}"
            print(f"[GridStrategyManager] {error_msg}")
            self.signals.strategy_error.emit(uid, error_msg)
            return False

        print(f"[GridStrategyManager] Updating grid config: {uid} - Level {level}")
        try:
            grid_data = self._data[uid]
            grid_data.update_level(level, config)
            return True
        except Exception as e:
            error_msg = f"更新网格配置失败: {str(e)}"
            print(f"[GridStrategyManager] {error_msg}")
            self.signals.strategy_error.emit(uid, error_msg)
            return False

    def is_strategy_running(self, uid: str) -> bool:
        trader = self._strategies.get(uid)
        return trader._running if trader else False

    def has_running_strategies(self) -> bool:
        return any(trader._running for trader in self._strategies.values())

    def get_all_running_pairs(self) -> list:
        return [self._data[uid].pair for uid, trader in self._strategies.items() if trader._running]

    def get_running_statistics(self) -> dict:
        stats = {
            "total_running": 0,
            "pairs": [],
            "total_investment": Decimal('0'),
            "total_profit": Decimal('0'),
            "last_update": datetime.now().isoformat()
        }
        
        try:
            stats["total_running"] = sum(1 for trader in self._strategies.values() if trader._running)
            stats["pairs"] = self.get_all_running_pairs()
            
            for uid, trader in self._strategies.items():
                if not trader._running:
                    continue
                grid_data = self._data[uid]
                for level_config in grid_data.grid_levels.values():
                    if level_config.is_filled:
                        stats["total_investment"] += level_config.invest_amount
                        if grid_data.ticker_data and grid_data.ticker_data.lastPr and level_config.filled_price:
                            profit = (grid_data.ticker_data.lastPr - level_config.filled_price) * level_config.filled_amount
                            if not grid_data.is_long():
                                profit = -profit
                            stats["total_profit"] += profit
            return stats
            
        except Exception as e:
            error_msg = f"获取运行统计失败: {str(e)}"
            print(f"[GridStrategyManager] {error_msg}")
            print(f"[GridStrategyManager] 错误详情: {traceback.format_exc()}")
            self.signals.strategy_error.emit("", error_msg)
            return stats

    def _handle_status_changed(self, uid: str, status: str):
        if status not in ["运行中", "已停止"]:
            self.signals.strategy_status_changed.emit(uid, status)

    # from .grid_trader import GridTrader
    def close_positions(self, uid: str, exchange_client: BaseClient) -> tuple[bool, str]:
        """平仓处理"""
        try:
            print(f"\n[GridStrategyManager] === 平仓操作 === {uid}")
            grid_data = self.get_strategy_data(uid)
            if not grid_data:
                error_msg = "策略数据不存在"
                print(f"[GridStrategyManager] {error_msg}")
                return False, error_msg

            print(f"[GridStrategyManager] 创建临时交易器执行平仓...")
            # 直接将 grid_data 作为参数传入
            from .grid_trader import GridTrader
            temp_trader = GridTrader(self, uid)  
            temp_trader.set_client(exchange_client)
            
            print(f"[GridStrategyManager] 开始执行平仓...")
            success, message = temp_trader._close_all_positions("手动平仓")
            
            if success:
                print(f"[GridStrategyManager] 平仓操作完成: {message}")
            else:
                print(f"[GridStrategyManager] 平仓失败: {message}")
            
            return success, message
            
        except Exception as e:
            error_msg = f"平仓失败: {str(e)}"
            print(f"[GridStrategyManager] {error_msg}")
            print(f"[GridStrategyManager] 错误详情: {traceback.format_exc()}")
            return False, error_msg