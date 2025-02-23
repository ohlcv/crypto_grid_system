import threading
import time
import traceback
from typing import List, Optional, Dict
from decimal import Decimal
from datetime import datetime
from qtpy.QtCore import QObject, Signal

from src.exchange.base_client import (
    BaseClient, FillResponse, InstType, OrderRequest, OrderResponse, OrderType, OrderSide, PositionSide, TradeSide
)
from src.utils.common.tools import adjust_decimal_places
from src.utils.common.tools import find_value
from .grid_core import GridData
from src.utils.logger.log_helper import grid_logger, trade_logger
from src.utils.error.error_handler import error_handler


class PriceState:
    """价格状态跟踪器"""
    def __init__(self):
        self.trigger_price: Optional[Decimal] = None  # 触发价格
        self.extreme_price: Optional[Decimal] = None  # 极值价格(开仓跟踪最低/最高)
        self.tp_extreme_price: Optional[Decimal] = None  # 止盈极值价格(止盈跟踪最高/最低)
        self.tp_trigger_price: Optional[Decimal] = None  # 止盈触发价格
        self.reset()

    def reset(self):
        """重置状态"""
        self.trigger_price = None
        self.extreme_price = None
        self.tp_extreme_price = None
        self.tp_trigger_price = None

    def update_extreme_price(self, price: Decimal, is_long: bool):
        """更新极值价格"""
        if self.extreme_price is None:
            self.extreme_price = price
        else:
            if is_long:
                self.extreme_price = min(self.extreme_price, price)
            else:
                self.extreme_price = max(self.extreme_price, price)


class OrderState:
    """订单状态管理"""
    def __init__(self):
        self._lock = threading.Lock()
        self.pending_order_id: Optional[str] = None
        self.current_level: Optional[int] = None

    def set_pending_order(self, order_id: str, level: int) -> bool:
        """设置待处理订单"""
        if not self._lock.acquire(timeout=0.5):  # 添加超时
            return False
        try:
            if self.pending_order_id:
                return False
            self.pending_order_id = order_id
            self.current_level = level
            return True
        finally:
            self._lock.release()

    def clear_pending_order(self):
        """清除待处理订单"""
        with self._lock:
            self.pending_order_id = None
            self.current_level = None


class GridTrader(QObject):
    """网格交易策略执行器"""
    
    status_changed = Signal(str, str)  # uid, status
    error_occurred = Signal(str, str)  # uid, error_message

    def __init__(self, grid_data: GridData):
        super().__init__()
        print(f"\n[GridTrader] === 初始化网格交易器 === {grid_data.uid}")
        self.logger = grid_logger
        self.trade_logger = trade_logger

        self.grid_data = grid_data
        self.client = None
        
        self._price_state = PriceState()
        self._order_state = OrderState()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()
        self._lock = threading.Lock()

        print(f"[GridTrader] 交易器初始化完成: {grid_data.uid}")
        print(f"  交易对: {grid_data.symbol_config.pair}")
        print(f"  方向: {grid_data.direction}")
        print(f"  总层数: {len(grid_data.grid_levels)}")

    def set_client(self, client: BaseClient):
        print(f"\n[GridTrader] === 设置交易所客户端 === {self.grid_data.uid}")
        print(f"[GridTrader] 新客户端: {client}")
        
        if self.client:
            try:
                print("[GridTrader] 断开旧client信号连接")
                self.client.order_updated.disconnect(self._on_order_update)
            except TypeError:
                pass

        self.client = client
        
        if client:
            print("[GridTrader] 连接新client的order_updated信号")
            client.order_updated.connect(self._on_order_update)
            print("[GridTrader] 客户端设置完成")

    def stop(self) -> bool:
        print(f"\n[GridTrader] === 停止策略 === {self.grid_data.uid}")
        
        if not self._running:
            print("[GridTrader] 策略未在运行中")
            self._thread = None
            return True

        self._stop_flag.set()
        self._running = False

        if self._thread and threading.current_thread().ident != self._thread.ident:
            print(f"[GridTrader] 等待线程 {self._thread.name} 结束")
            if self._thread.is_alive():
                self._thread.join(timeout=2)
            else:
                print(f"[GridTrader] 线程 {self._thread.name} 已经结束，跳过 join 调用")
        
        self._thread = None
        self.status_changed.emit(self.grid_data.uid, "已停止")
        self.grid_data.status = "已停止"
        self.grid_data.data_updated.emit(self.grid_data.uid)
        print(f"[GridTrader] 策略已停止")
        return True

    def start(self) -> bool:
        print(f"\n[GridTrader] === 启动策略 === {self.grid_data.uid}")
        
        if self._running:
            print(f"[GridTrader] 策略已在运行中")
            return False

        if not self.client:
            error_msg = "未设置交易所客户端，无法获取交易对参数"
            self.logger.error(error_msg)
            self.error_occurred.emit(self.grid_data.uid, error_msg)
            return False

        if not self._cache_trading_params():
            error_msg = "获取交易对参数失败，无法启动策略"
            self.logger.error(error_msg)
            self.error_occurred.emit(self.grid_data.uid, error_msg)
            return False

        if self._thread:
            print(f"[GridTrader] 清理旧线程引用: {self._thread.name}")
            self._thread = None

        thread_name = f"GridTrader-{self.grid_data.symbol_config.pair}-{self.grid_data.uid}"
        print(f"[GridTrader] 创建新线程: {thread_name}")
        self._thread = threading.Thread(
            name=thread_name,
            target=self._run_strategy,
            daemon=True
        )
        
        self._running = True
        self._stop_flag.clear()
        self._thread.start()
        print(f"[GridTrader] 线程已启动, ID: {self._thread.ident}")
        self.status_changed.emit(self.grid_data.uid, "运行中")
        self.grid_data.status = "运行中"
        self.grid_data.data_updated.emit(self.grid_data.uid)
        return True

    def _cache_trading_params(self) -> bool:
        try:
            print(f"\n[GridTrader] === 检查并缓存交易对参数 === {self.grid_data.uid}")
            print(f"交易对: {self.grid_data.symbol_config.pair}")

            if (self.grid_data.symbol_config.base_precision is not None and
                self.grid_data.symbol_config.price_precision is not None and
                self.grid_data.symbol_config.min_base_amount is not None and
                self.grid_data.symbol_config.min_quote_amount is not None):
                print(f"[GridTrader] 已存在缓存参数:")
                print(f"  数量精度: {self.grid_data.symbol_config.base_precision}")
                print(f"  价格精度: {self.grid_data.symbol_config.price_precision}")
                print(f"  最小数量: {self.grid_data.symbol_config.min_base_amount}")
                print(f"  最小金额: {self.grid_data.symbol_config.min_quote_amount}")
                return True

            symbol_normalized = self.grid_data.symbol_config.symbol
            inst_type = self.grid_data.inst_type
            symbol_configs = self.client.rest_api.get_symbol_config(symbol=symbol_normalized, inst_type=inst_type)

            if not symbol_configs:
                error_msg = f"获取交易对 {symbol_normalized} 信息失败"
                print(f"[GridTrader] {error_msg}")
                return False

            pair_config = next((config for config in symbol_configs if config.symbol == symbol_normalized), None)
            if not pair_config:
                print(f"[GridTrader] 未找到交易对 {symbol_normalized} 的配置")
                return False

            self.grid_data.symbol_config = pair_config
            print(f"[GridTrader] 参数已缓存:")
            print(f"  数量精度: {self.grid_data.symbol_config.base_precision}")
            print(f"  价格精度: {self.grid_data.symbol_config.price_precision}")
            print(f"  最小数量: {self.grid_data.symbol_config.min_base_amount}")
            print(f"  最小金额: {self.grid_data.symbol_config.min_quote_amount}")
            return True

        except Exception as e:
            print(f"[GridTrader] 缓存交易参数失败: {e}")
            print(f"[GridTrader] 错误详情: {traceback.format_exc()}")
            return False

    def _run_strategy(self):
        thread_name = threading.current_thread().name
        thread_id = threading.current_thread().ident
        print(f"\n[GridTrader] === 策略线程启动 ===")
        print(f"[GridTrader] 线程名称: {thread_name}")
        print(f"[GridTrader] 线程ID: {thread_id}")
        print(f"[GridTrader] 策略初始状态:")
        print(f"  交易对: {self.grid_data.symbol_config.pair}")
        print(f"  方向: {self.grid_data.direction}")
        print(f"  总层数: {len(self.grid_data.grid_levels)}")
        print(f"  运行标志: {self._running}")
        
        last_process_time = time.time()
        last_price = None
        min_process_interval = 0.1
        
        while self._running and not self._stop_flag.is_set():
            try:
                current_time = time.time()
                
                if current_time - last_process_time < min_process_interval:
                    time.sleep(0.01)
                    continue
                    
                if not self._order_state.pending_order_id:
                    current_price = self.grid_data.ticker_data.lastPr if self.grid_data.ticker_data else None
                    if current_price and current_price != last_price:
                        self._process_price_update(current_price)
                        last_price = current_price
                
                last_process_time = current_time
                
            except Exception as e:
                print(f"[GridTrader] 策略线程 {thread_name} 执行错误: {e}")
                print(f"[GridTrader] 错误详情: {traceback.format_exc()}")
                self.handle_error(f"策略执行错误: {str(e)}")
                break

        print(f"[GridTrader] === 策略线程退出 ===")
        print(f"[GridTrader] 线程名称: {thread_name}")
        print(f"[GridTrader] 线程ID: {thread_id}")
        print(f"[GridTrader] 退出原因: {'停止标志被设置' if self._stop_flag.is_set() else '运行标志为False'}")
        self._running = False
        self.grid_data.status = "已停止"
        self.grid_data.data_updated.emit(self.grid_data.uid)

    def handle_error(self, error_msg: str):
        print(f"[GridTrader] 策略错误: {error_msg}")
        self.error_occurred.emit(self.grid_data.uid, error_msg)
        self.stop()

    @error_handler()
    def _check_first_grid(self, current_price: Decimal) -> bool:
        print(f"\n[GridTrader] === 检查第一层网格开仓条件 ===")
        print(f"[GridTrader] 当前价格: {current_price}")
        return True

    @error_handler()
    def _check_rebound(self, current_price: Decimal, level_config, is_open: bool) -> bool:
        if not self._price_state.extreme_price:
            return False

        rebound = (level_config.open_rebound_percent if is_open else level_config.close_rebound_percent) / Decimal('100')
        is_long = self.grid_data.is_long()

        if is_open:
            if is_long:
                price_diff = current_price - self._price_state.extreme_price
                rebound_ratio = price_diff / self._price_state.extreme_price
                print(f"[GridTrader] 做多开仓反弹检查:")
                print(f"  当前价格: {current_price}")
                print(f"  最低价: {self._price_state.extreme_price}")
                print(f"  反弹比例: {rebound_ratio}")
                print(f"  目标比例: {rebound}")
                return rebound_ratio >= rebound
            else:
                price_diff = self._price_state.extreme_price - current_price
                rebound_ratio = price_diff / self._price_state.extreme_price
                print(f"[GridTrader] 做空开仓回落检查:")
                print(f"  当前价格: {current_price}")
                print(f"  最高价: {self._price_state.extreme_price}")
                print(f"  回落比例: {rebound_ratio}")
                print(f"  目标比例: {rebound}")
                return rebound_ratio >= rebound
        else:
            if is_long:
                price_diff = self._price_state.tp_extreme_price - current_price
                rebound_ratio = price_diff / self._price_state.tp_extreme_price
                print(f"[GridTrader] 做多平仓回落检查:")
                print(f"  当前价格: {current_price}")
                print(f"  最高价: {self._price_state.tp_extreme_price}")
                print(f"  回落比例: {rebound_ratio}")
                print(f"  目标比例: {rebound}")
                return rebound_ratio >= rebound
            else:
                price_diff = current_price - self._price_state.tp_extreme_price
                rebound_ratio = price_diff / self._price_state.tp_extreme_price
                print(f"[GridTrader] 做空平仓反弹检查:")
                print(f"  当前价格: {current_price}")
                print(f"  最低价: {self._price_state.tp_extreme_price}")
                print(f"  反弹比例: {rebound_ratio}")
                print(f"  目标比例: {rebound}")
                return rebound_ratio >= rebound

    def _get_last_take_profit_price(self, level: int) -> Optional[Decimal]:
        try:
            config = self.grid_data.grid_levels.get(level)
            if not config:
                return None
            return getattr(config, 'last_tp_price', None)
        except Exception as e:
            self.logger.error(f"获取止盈价格失败: {e}")
            return None

    @error_handler()
    def _check_open_position(self, current_price: Decimal) -> None:
        if not self.grid_data.operations.get("开仓", False):
            print(f"[GridTrader] 开仓操作被禁用")
            return

        print(f"\n[GridTrader] === 检查开仓条件 === {self.grid_data.symbol_config.pair} {self.grid_data.uid}")
        next_level = self.grid_data.get_next_level()
        total_levels = len(self.grid_data.grid_levels)
        
        if next_level is None or next_level >= total_levels:
            print("[GridTrader] 已达到最大层数或超出范围，不再开仓")
            return

        level_config = self.grid_data.grid_levels[next_level]
        is_long = self.grid_data.is_long()
        print(f"[GridTrader] 开仓百分比: {level_config.interval_percent}%")
        
        if next_level == 0:
            if self._check_first_grid(current_price):
                self._place_order(next_level)
            return

        last_tp_price = self._get_last_take_profit_price(next_level)
        last_level = self.grid_data.get_last_filled_level()
        if last_level is None:
            return
            
        if last_level not in self.grid_data.grid_levels:
            print(f"[GridTrader] 警告: 找不到层级 {last_level} 的网格配置")
            return

        last_level_config = self.grid_data.grid_levels[last_level]
        if not last_level_config.filled_price:
            return

        base_price = last_level_config.filled_price
        interval = level_config.interval_percent / Decimal('100')
        
        if is_long:
            self._price_state.trigger_price = base_price * (Decimal('1') - interval)
        else:
            self._price_state.trigger_price = base_price * (Decimal('1') + interval)

        if last_tp_price:
            print(f"[GridTrader] 检查开仓条件 - 存在平仓历史")
            print(f"上次平仓价格: {last_tp_price}")
            print(f"当前价格: {current_price}")
            
            if current_price > last_tp_price:
                print(f"[GridTrader] 当前价格高于平仓价格，等待回落")
                return
                
            if not self._price_state.extreme_price:
                self._price_state.extreme_price = current_price
            else:
                if is_long:
                    self._price_state.extreme_price = min(self._price_state.extreme_price, current_price)
                else:
                    self._price_state.extreme_price = max(self._price_state.extreme_price, current_price)
            
            if not self._check_rebound(current_price, level_config, is_open=True):
                return
                
            print(f"[GridTrader] 满足反弹条件，准备下单")
            self._place_order(next_level)
            return

        print(f"[GridTrader] 当前市场价格: {current_price}")
        print(f"[GridTrader] 开仓触发价格: {self._price_state.trigger_price}")

        triggered = False
        if is_long:
            triggered = current_price <= self._price_state.trigger_price
        else:
            triggered = current_price >= self._price_state.trigger_price

        self.grid_data.open_trigger_price = self._price_state.trigger_price

        if triggered:
            print(f"[GridTrader] === 价格达到触发条件 ===")
            if not self._price_state.extreme_price:
                self._price_state.extreme_price = current_price
            else:
                if is_long:
                    self._price_state.extreme_price = min(self._price_state.extreme_price, current_price)
                else:
                    self._price_state.extreme_price = max(self._price_state.extreme_price, current_price)
            
            print(f"[GridTrader] 更新极值价格: {self._price_state.extreme_price}")
            
            if self._check_rebound(current_price, level_config, is_open=True):
                print(f"[GridTrader] 反弹条件满足，准备下单")
                self._place_order(next_level)

    @error_handler()
    def _process_price_update(self, current_price: Decimal):
        if not current_price:
            return
        
        try:
            grid_status = self.grid_data.get_grid_status()
            
            if not grid_status["is_configured"]:
                return
            
            position_metrics = self.grid_data.calculate_position_metrics()
            unrealized_pnl = position_metrics['unrealized_pnl']
            
            if grid_status["filled_levels"] > 0 and self.grid_data._check_stop_loss_condition(unrealized_pnl):
                self._close_all_positions("总体止损触发，全部平仓")
                return

            if grid_status["filled_levels"] > 0 and self.grid_data.operations.get("平仓", False):
                if self._check_take_profit(current_price):
                    return
                    
            if not grid_status["is_full"] and self.grid_data.operations.get("开仓", False):
                self._check_open_position(current_price)
                
        except Exception as e:
            error_msg = f"处理价格更新错误: {str(e)}"
            self.logger.error(error_msg)
            self.error_occurred.emit(self.grid_data.uid, error_msg)

    @error_handler()
    def _check_take_profit(self, current_price: Decimal) -> bool:
        if not self.grid_data.operations.get("平仓", False):
            print(f"[GridTrader] 平仓操作被禁用")
            return False

        print(f"\n[GridTrader] === 检查止盈条件 === {self.grid_data.symbol_config.pair} {self.grid_data.uid}")
        last_level = self.grid_data.get_last_filled_level()
        
        if last_level is None:
            print("[GridTrader] 未找到已成交的层级，无法检查止盈条件")
            return False

        level_config = self.grid_data.grid_levels[last_level]
        is_long = self.grid_data.is_long()
        print(f"[GridTrader] 策略方向: {'做多' if is_long else '做空'}")

        profit_percent = level_config.take_profit_percent / Decimal('100')
        if is_long:
            self._price_state.tp_trigger_price = level_config.filled_price * (Decimal('1') + profit_percent)
        else:
            self._price_state.tp_trigger_price = level_config.filled_price * (Decimal('1') - profit_percent)
        self.grid_data.tp_trigger_price = self._price_state.tp_trigger_price

        print(f"[GridTrader] 当前市场价格: {current_price}")
        print(f"[GridTrader] 止盈触发价格: {self._price_state.tp_trigger_price}")
        print(f"[GridTrader] 止盈百分比: {level_config.take_profit_percent}%")

        triggered = False
        if is_long:
            triggered = current_price >= self._price_state.tp_trigger_price
        else:
            triggered = current_price <= self._price_state.tp_trigger_price

        if triggered:
            print(f"[GridTrader] === 达到止盈触发条件 ===")
            if not self._price_state.tp_extreme_price:
                self._price_state.tp_extreme_price = current_price
                print(f"[GridTrader] 初始化止盈极值价格: {self._price_state.tp_extreme_price}")
            else:
                if is_long:
                    self._price_state.tp_extreme_price = max(self._price_state.tp_extreme_price, current_price)
                else:
                    self._price_state.tp_extreme_price = min(self._price_state.tp_extreme_price, current_price)
                print(f"[GridTrader] 更新止盈极值价格: {self._price_state.tp_extreme_price}")
            
            if self._check_rebound(current_price, level_config, is_open=False):
                print(f"[GridTrader] 止盈回调条件满足，准备下止盈单")
                self._place_take_profit_order(last_level)
                print("[GridTrader] 止盈单已下，重置价格状态")
                self._price_state.reset()
                return True
            else:
                print("[GridTrader] 止盈回调条件未满足，继续等待")
        else:
            print("[GridTrader] 未达到止盈触发条件，继续观察")
        return False

    @error_handler()
    def _place_order(self, level: int) -> None:
        try:
            self.logger.info(f"{self.grid_data.inst_type} {self.grid_data.uid} {self.grid_data.symbol_config.pair} 准备开仓-{level}")
            level_config = self.grid_data.grid_levels[level]
            is_long = self.grid_data.is_long()

            request = OrderRequest(
                inst_type=self.grid_data.inst_type,
                pair=self.grid_data.symbol_config.pair,
                symbol=self.grid_data.symbol_config.symbol,
                position_side=PositionSide.LONG if is_long else PositionSide.SHORT,
                side=OrderSide.BUY if is_long else OrderSide.SELL,
                trade_side=TradeSide.OPEN,
                order_type=OrderType.MARKET,
                quote_size=Decimal(str(level_config.invest_amount)),
                price=self.grid_data.ticker_data.lastPr if self.grid_data.ticker_data else None,
                client_order_id=f"grid_{self.grid_data.uid}_{level}_{int(time.time()*1000)}"
            )

            response = self.client.rest_api.place_order(request)
            
            if response.success:
                self._order_state.set_pending_order(response.order_id, level)
                print(f"[GridTrader] 开仓订单已提交: {response.order_id}")
                print(f"[GridTrader] 调用函数: {response.function_name}")
                if response.data:
                    print(f"[GridTrader] 成交数量: {response.data.filled_base_amount}")
                    print(f"[GridTrader] 成交价格: {response.data.filled_price}")
                    print(f"[GridTrader] 成交金额: {response.data.filled_quote_value}")
                    print(f"[GridTrader] 手续费: {response.data.fee}")
                    print(f"[GridTrader] 手续费币种: {response.data.fee_currency}")
                    # 直接传递 FillResponse 对象给 update_order_fill
                    self.grid_data.update_order_fill(level, response.data, TradeSide.OPEN)
            else:
                error_msg = f"下单失败: {response.error_message}"
                self.handle_error(error_msg)

        except Exception as e:
            error_msg = f"下单错误: {str(e)}"
            self.trade_logger.error(f"下单错误 - {self.grid_data.uid}", exc_info=e)
            self.handle_error(error_msg)

    @error_handler()
    def _place_take_profit_order(self, level: int) -> None:
        try:
            level_config = self.grid_data.grid_levels[level]
            is_long = self.grid_data.is_long()
            
            request = OrderRequest(
                inst_type=self.grid_data.inst_type,
                pair=self.grid_data.symbol_config.pair,
                symbol=self.grid_data.symbol_config.symbol,
                position_side=PositionSide.LONG if is_long else PositionSide.SHORT,
                side=OrderSide.SELL if is_long else OrderSide.BUY,
                trade_side=TradeSide.CLOSE,
                order_type=OrderType.MARKET,
                base_size=level_config.filled_amount,
                price=self.grid_data.ticker_data.lastPr if self.grid_data.ticker_data else None,
                client_order_id=f"grid_{self.grid_data.uid}_{level}_{int(time.time()*1000)}_tp"
            )

            response = self.client.rest_api.place_order(request)
            
            if response.success:
                self._order_state.set_pending_order(response.order_id, level)
                print(f"[GridTrader] 止盈订单已提交: {response.order_id}")
                print(f"[GridTrader] 调用函数: {response.function_name}")
                if response.data:
                    print(f"[GridTrader] 成交数量: {response.data.filled_base_amount}")
                    print(f"[GridTrader] 成交价格: {response.data.filled_price}")
                    print(f"[GridTrader] 成交金额: {response.data.filled_quote_value}")
                    print(f"[GridTrader] 手续费: {response.data.fee}")
                    print(f"[GridTrader] 手续费币种: {response.data.fee_currency}")
                    # 更新止盈成交信息
                    self.grid_data.update_order_fill(level, response.data, TradeSide.CLOSE)
            else:
                error_msg = f"止盈下单失败: {response.error_message}"
                self.error_occurred.emit(self.grid_data.uid, error_msg)

        except Exception as e:
            error_msg = f"止盈下单错误: {str(e)}"
            self.logger.error(f"[GridTrader] {error_msg}")
            self.logger.error(f"[GridTrader] 错误详情: {traceback.format_exc()}")
            self.handle_error(error_msg)

    @error_handler()
    def _on_order_update(self, order_id: str, order_data: dict):
        if order_id != self._order_state.pending_order_id:
            return
        try:
            if order_data["status"] == "filled":
                level = self._order_state.current_level
                # 构造 FillResponse 对象
                fill_response = FillResponse(
                    symbol=self.grid_data.symbol_config.symbol,
                    trade_time=int(order_data.get('cTime', time.time() * 1000)),
                    position_side=self.grid_data.direction,
                    trade_side=TradeSide.OPEN,  # 默认假设为开仓，后续可根据逻辑调整
                    filled_price=Decimal(order_data.get('priceAvg', '0')),  # 需要从 order_data 中获取
                    filled_base_amount=Decimal(order_data.get('size', '0')),  # 需要从 order_data 中获取
                    filled_quote_value=Decimal(order_data.get('amount', '0')),  # 需要从 order_data 中获取
                    trade_id=order_data.get('tradeId'),
                    order_id=order_id,
                    client_order_id=order_data.get('clientOid'),
                    fee=Decimal(order_data.get('fee', '0')) if order_data.get('fee') else None,
                    fee_currency=order_data.get('feeCoin'),
                    trade_scope=order_data.get('tradeScope')
                )
                self.grid_data.update_order_fill(level, fill_response, TradeSide.OPEN)
                self._order_state.clear_pending_order()
                print(f"[GridTrader] Order filled: {order_id} for level {level}")
                    
        except Exception as e:
            print(f"[GridTrader] Error processing order update: {e}")
            self.error_occurred.emit(self.grid_data.uid, f"订单更新处理失败: {str(e)}")

    @error_handler()
    def _close_all_positions(self, reason: str) -> tuple[bool, str]:
        try:
            self.logger.info(f"{self.grid_data.inst_type} {self.grid_data.uid} {self.grid_data.symbol_config.pair} 准备全平...")
            self.logger.info(f"  原因: {reason}")
            
            request = OrderRequest(
                inst_type=self.grid_data.inst_type,
                pair=self.grid_data.symbol_config.pair,
                symbol=self.grid_data.symbol_config.symbol,
                position_side=PositionSide.LONG if self.grid_data.is_long() else PositionSide.SHORT
            )
            
            response = self.client.rest_api.closeAllPositionsMarket(request)
            
            if response.success:
                print(f"[GridTrader] 全平订单提交成功: {response.order_id}")
                print(f"[GridTrader] 调用函数: {response.function_name}")
                if response.data:
                    print(f"[GridTrader] 成交数量: {response.data.filled_base_amount}")
                    print(f"[GridTrader] 成交价格: {response.data.filled_price}")
                self.grid_data.reset_to_initial()
                self.grid_data.status = f"已平仓({reason})"
                self.grid_data.data_updated.emit(self.grid_data.uid)
                return True, "平仓成功"
            else:
                error_msg = f"平仓失败: {response.error_message}"
                self.error_occurred.emit(self.grid_data.uid, error_msg)
                return False, error_msg
                    
        except Exception as e:
            error_msg = f"平仓出错: {str(e)}"
            self.logger.error(f"[GridTrader] {error_msg}")
            self.logger.error(f"[GridTrader] 错误详情: {traceback.format_exc()}")
            return False, error_msg