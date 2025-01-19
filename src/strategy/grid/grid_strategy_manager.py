# src/strategy/grid/grid_strategy_manager.py

import traceback
from typing import Dict, Optional
from decimal import Decimal
import threading
from datetime import datetime
from qtpy.QtCore import QObject, Signal

from src.exchange.base_client import BaseClient
from src.utils.common.tools import find_value
from .grid_core import GridData, GridDirection
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

    def create_strategy(self, uid: str, pair: str, exchange: str, inst_type: str) -> Optional[GridData]:
        """创建新策略"""
        print(f"\n[GridStrategyManager] === 创建新策略 === {uid}")
        print(f"[GridStrategyManager] 交易对: {pair}")
        # print(f"[GridStrategyManager] 当前线程状态:")
        # for t in threading.enumerate():
        #     print(f"  - {t.name} (ID: {t.ident})")
        
        with self._lock:
            if uid in self._data:
                print(f"[GridStrategyManager] 策略 {uid} 已存在")
                return None

        try:
            # 创建策略数据
            print(f"[GridStrategyManager] 初始化策略数据...")
            grid_data = GridData(uid, pair, exchange, inst_type)
            self._data[uid] = grid_data
            
            # 创建策略实例（只传入grid_data）
            print(f"[GridStrategyManager] 创建策略实例...")
            trader = GridTrader(grid_data)  
            self._strategies[uid] = trader
            print(f"[GridStrategyManager] 策略实例创建成功: {uid}")
            
            # 打印当前线程状态
            # print("\n[GridStrategyManager] 策略创建后线程状态:")
            # for t in threading.enumerate():
            #     print(f"  - {t.name} (ID: {t.ident}, 活跃: {t.is_alive()})")
                
            return grid_data
            
        except Exception as e:
            print(f"[GridStrategyManager] 创建策略失败: {e}")
            print(f"[GridStrategyManager] 错误详情: {traceback.format_exc()}")
            
            # 清理失败的策略数据
            if uid in self._data:
                del self._data[uid]
                print(f"[GridStrategyManager] 已清理失败的策略数据: {uid}")
            
            return None

    def stop_strategy(self, uid: str) -> bool:
        """暂停策略运行"""
        print(f"\n[GridStrategyManager] === 暂停策略运行 === {uid}")
        
        try:
            trader = self._strategies.get(uid)
            if not trader:
                print(f"[GridStrategyManager] 未找到策略实例: {uid}")
                return False
                
            # 停止策略运行
            success = trader.stop()
            if success:
                self.strategy_stopped.emit(uid)
                print(f"[GridStrategyManager] 策略已暂停运行")
            
            return success
            
        except Exception as e:
            print(f"[GridStrategyManager] 暂停策略失败: {e}")
            print(f"[GridStrategyManager] 错误详情: {traceback.format_exc()}")
            return False

    def delete_strategy(self, uid: str) -> bool:
        """删除策略"""
        print(f"\n[GridStrategyManager] === 删除策略 === {uid}")
        print(f"[GridStrategyManager] 当前线程状态:")
        for t in threading.enumerate():
            print(f"  - {t.name} (ID: {t.ident}, 活跃: {t.is_alive()})")
        
        try:
            # 如果策略正在运行，先停止它
            if self.is_strategy_running(uid):
                print(f"[GridStrategyManager] 策略 {uid} 正在运行，先停止它")
                if not self.stop_strategy(uid):
                    print(f"[GridStrategyManager] 停止策略失败")
                    return False
                    
            with self._lock:
                # 清理策略实例
                if uid in self._strategies:
                    trader = self._strategies[uid]
                    print(f"[GridStrategyManager] 清理策略实例: {uid}")
                    
                    # 检查是否有活动线程
                    if trader._thread and trader._thread.is_alive():
                        print(f"[GridStrategyManager] 发现活动线程:")
                        print(f"  线程名称: {trader._thread.name}")
                        print(f"  线程ID: {trader._thread.ident}")
                        
                        # 确保线程停止
                        trader._stop_flag.set()
                        trader._running = False
                        trader._thread.join(timeout=2)
                        print(f"[GridStrategyManager] 线程已终止")
                        
                    # 清理client
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
                if uid in self._data:
                    grid_data = self._data[uid]
                    # 断开数据更新信号
                    try:
                        grid_data.data_updated.disconnect()
                    except TypeError:
                        pass
                    del self._data[uid]
                    print(f"[GridStrategyManager] 策略数据已删除")
                
                # 打印更新后的线程状态
                # print("\n[GridStrategyManager] 策略删除后线程状态:")
                # print(f"  总线程数: {len(threading.enumerate())}")
                # for t in threading.enumerate():
                #     print(f"  - {t.name} (ID: {t.ident}, 活跃: {t.is_alive()})")
                
                return True
            
        except Exception as e:
            print(f"[GridStrategyManager] 删除策略失败: {e}")
            print(f"[GridStrategyManager] 错误详情: {traceback.format_exc()}")
            return False

    def start_strategy(self, uid: str, exchange_client: BaseClient) -> bool:
        """启动策略运行"""
        print(f"\n[GridStrategyManager] === 启动策略运行 === {uid}")
        print(f"[GridStrategyManager] 当前线程状态:")
        for t in threading.enumerate():
            print(f"  - {t.name} (ID: {t.ident}, 活跃: {t.is_alive()})")
        
        try:
            # 获取grid_data
            grid_data = self._data.get(uid)
            if not grid_data:
                print(f"[GridStrategyManager] 未找到策略数据: {uid}")
                return False
                
            # 获取或创建trader
            trader = self._strategies.get(uid)
            if trader and trader._running:
                print(f"[GridStrategyManager] 策略已在运行中")
                if trader._thread:
                    print(f"  线程名称: {trader._thread.name}")
                    print(f"  线程ID: {trader._thread.ident}")
                return False

            # 如果不存在trader或trader已停止，创建新的trader
            if not trader:
                trader = GridTrader(grid_data)
                self._strategies[uid] = trader

            # 获取并缓存交易对参数
            if not self._cache_trading_params(trader.grid_data, exchange_client):
                error_msg = "获取交易对参数失败"
                self.strategy_error.emit(uid, error_msg)
                return False
                
            # 设置exchange_client
            print(f"[GridStrategyManager] 设置交易所客户端...")
            trader.set_client(exchange_client)
            
            # 确保实现盈亏值正确设置
            original_profit = grid_data.total_realized_profit
            print(f"[GridStrategyManager] 保持原有实现盈亏: {original_profit}")
            
            # 启动策略
            if trader.start():
                self.strategy_started.emit(uid)
                # 确保运行状态更新但不影响实现盈亏
                grid_data.total_realized_profit = original_profit
                grid_data.row_dict["实现盈亏"] = str(original_profit)
                grid_data.row_dict["运行状态"] = "运行中"
                grid_data.data_updated.emit(uid)
                
                # 打印更新后的线程状态
                print("\n[GridStrategyManager] 策略启动后线程状态:")
                for t in threading.enumerate():
                    print(f"  - {t.name} (ID: {t.ident}, 活跃: {t.is_alive()})")
                return True
                
            return False
                
        except Exception as e:
            print(f"[GridStrategyManager] 启动策略失败: {e}")
            print(f"[GridStrategyManager] 错误详情: {traceback.format_exc()}")
            self.strategy_error.emit(uid, str(e))
            return False

    def _cache_trading_params(self, grid_data: GridData, exchange_client: BaseClient) -> bool:
        """获取并缓存交易对参数
        
        Args:
            grid_data: 网格策略数据
            exchange_client: 交易所客户端
            
        Returns:
            bool: 是否成功获取并缓存参数
        """
        try:
            print(f"\n[GridStrategyManager] === 获取交易对参数 ===")
            print(f"交易对: {grid_data.pair}")
            
            # 获取交易对信息
            symbol_normalized = grid_data.pair.replace('/', '')
            is_spot = grid_data.inst_type == "SPOT"
            pair_info = exchange_client.rest_api.get_pairs(symbol=symbol_normalized)
            
            if pair_info.get('code') != '00000':
                error_msg = f"获取交易对信息失败: {pair_info.get('msg')}"
                print(f"[GridStrategyManager] {error_msg}")
                return False
                
            # 缓存交易参数
            pair_data = pair_info['data'][0]
            print(f"[GridStrategyManager] 原始数据: {pair_data}")
            
            if is_spot:
                # 现货参数
                grid_data.quantity_precision = int(pair_data.get('quantityPrecision', 4))
                grid_data.price_precision = int(pair_data.get('pricePrecision', 2))
                grid_data.min_trade_amount = Decimal(str(pair_data.get('minTradeAmount', '0')))
                grid_data.min_trade_value = Decimal(str(pair_data.get('minTradeUSDT', '5')))
                print(f"[GridStrategyManager] 现货参数已缓存:")
                print(f"  数量精度: {grid_data.quantity_precision}")
                print(f"  价格精度: {grid_data.price_precision}")
                print(f"  最小数量: {grid_data.min_trade_amount}")
                print(f"  最小金额: {grid_data.min_trade_value}")
            else:
                # 合约参数
                grid_data.quantity_precision = int(pair_data.get('volumePlace', 4))
                grid_data.price_precision = int(pair_data.get('pricePlace', 2))
                grid_data.min_trade_amount = Decimal(str(pair_data.get('minTradeNum', '0')))
                grid_data.min_trade_value = Decimal(str(pair_data.get('minTradeUSDT', '5')))
                print(f"[GridStrategyManager] 合约参数已缓存:")
                print(f"  数量精度: {grid_data.quantity_precision}")
                print(f"  价格精度: {grid_data.price_precision}")
                print(f"  最小数量: {grid_data.min_trade_amount}")
                print(f"  最小金额: {grid_data.min_trade_value}")

            return True

        except Exception as e:
            print(f"[GridStrategyManager] 缓存交易参数失败: {e}")
            print(f"[GridStrategyManager] 错误详情: {traceback.format_exc()}")
            return False

    def process_market_data(self, pair: str, data: dict):
        """处理市场数据"""
        try:
            # 确保数据格式正确
            if not isinstance(data, dict):
                print(f"[GridStrategyManager] 无效的市场数据格式: {data}")
                return

            normalized_pair = pair.replace('/', '')
            # print(f"\n[GridStrategyManager] === 处理市场数据 === {normalized_pair}")
            # print(f"[GridStrategyManager] 原始数据: {data}")

            # 获取所有运行中的策略ID
            running_strategies = set(self._strategies.keys())
            if not running_strategies:
                return  # 没有运行中的策略，直接返回

            # 找到相关策略
            affected_strategies = []
            for uid, grid_data in self._data.items():
                # 只处理运行中的策略
                if uid not in running_strategies:
                    continue

                grid_pair = grid_data.pair.replace('/', '')
                if grid_pair == normalized_pair:
                    affected_strategies.append(uid)

            # 只有匹配的交易对且策略在运行时才处理
            # print(f"[GridStrategyManager] 行情交易对: {normalized_pair} 找到相关策略: {affected_strategies}")
            for uid in affected_strategies:
                try:
                    grid_data = self._data[uid]
                    if not grid_data:
                        continue

                    # 检查是否运行中
                    trader = self._strategies.get(uid)
                    if not trader or not trader._running:
                        continue

                    # 检查操作状态
                    operation_status = grid_data.row_dict.get("操作", {})
                    if not operation_status.get("开仓", True) and not operation_status.get("平仓", True):
                        continue  # 如果开平仓都被禁用，跳过更新

                    # 检查数据完整性 - 修正这里的逻辑
                    price_str = find_value(data, "lastPr")
                    timestamp = find_value(data, "ts")
                    if not price_str or not timestamp:  # 改为检查是否为空
                        print(f"[GridStrategyManager] 数据不完整: price={price_str}, timestamp={timestamp}")
                        continue

                    # 更新策略数据
                    grid_data.update_market_data(data)

                except Exception as e:
                    print(f"[GridStrategyManager] 更新策略 {uid} 失败: {e}")
                    print(f"[GridStrategyManager] 错误详情: {traceback.format_exc()}")
                    
                    # 尝试停止出错的策略
                    try:
                        if uid in self._strategies:
                            trader = self._strategies[uid]
                            trader.stop()
                            del self._strategies[uid]
                            self.strategy_error.emit(uid, f"策略数据更新错误: {str(e)}")
                    except Exception as stop_error:
                        print(f"[GridStrategyManager] 停止策略失败: {stop_error}")

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

    def close_positions(self, uid: str, exchange_client: BaseClient) -> bool:
        """
        平掉指定策略的所有持仓
        Args:
            uid: 策略ID
            exchange_client: 交易所客户端
        Returns:
            bool: 是否成功平仓
        """
        print(f"\n[GridStrategyManager] === 平仓操作 === {uid}")
        try:
            # 获取策略数据
            grid_data = self._data.get(uid)
            if not grid_data:
                print(f"[GridStrategyManager] 错误: 策略数据不存在 - {uid}")
                return False

            # 检查是否有持仓
            # metrics = grid_data.calculate_position_metrics()
            # if metrics['total_value'] <= 0:
            #     print(f"[GridStrategyManager] 策略 {uid} 无持仓，无需平仓")
            #     return True
                
            # print(f"[GridStrategyManager] 当前持仓信息:")
            # print(f"  持仓价值: {metrics['total_value']}")
            # print(f"  持仓均价: {metrics['avg_price']}")
            # print(f"  未实现盈亏: {metrics['unrealized_pnl']}")
                    
            # 创建临时的GridTrader实例来执行平仓
            print(f"[GridStrategyManager] 创建临时交易器执行平仓...")
            temp_trader = GridTrader(grid_data)
            temp_trader.set_client(exchange_client)
            
            # 连接错误信号以便转发
            temp_trader.error_occurred.connect(self._handle_strategy_error)
            
            # 执行平仓
            print(f"[GridStrategyManager] 开始执行平仓...")
            success = temp_trader._close_all_positions("手动平仓")
            
            if success:
                print(f"[GridStrategyManager] 平仓成功")
                # 如果策略正在运行，需要停止它
                if self.is_strategy_running(uid):
                    print(f"[GridStrategyManager] 停止正在运行的策略...")
                    self.stop_strategy(uid)
            else:
                print(f"[GridStrategyManager] 平仓失败")
                
            return success
                
        except Exception as e:
            error_msg = f"平仓失败: {str(e)}"
            print(f"[GridStrategyManager] {error_msg}")
            print(f"[GridStrategyManager] 错误详情: {traceback.format_exc()}")
            self.strategy_error.emit(uid, error_msg)
            return False