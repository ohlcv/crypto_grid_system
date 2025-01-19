# src/strategy/grid/grid_trader.py

import threading
import time
import traceback
from typing import Optional, Dict
from decimal import ROUND_HALF_UP, Decimal
from datetime import datetime
from qtpy.QtCore import QObject, Signal

from src.exchange.base_client import (
    BaseClient, OrderRequest, OrderType, OrderSide, TradeSide
)
from src.utils.common.common import adjust_decimal_places
from src.utils.common.tools import find_value
from .grid_core import GridData, GridDirection
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
    
    # 信号定义
    status_changed = Signal(str, str)  # uid, status
    error_occurred = Signal(str, str)  # uid, error_message

    def __init__(self, grid_data: GridData):
        """初始化交易器
        Args:
            grid_data: 网格策略数据
        """
        super().__init__()
        print(f"\n[GridTrader] === 初始化网格交易器 === {grid_data.uid}")
        self.logger = grid_logger
        self.trade_logger = trade_logger
        self.logger.info(f"创建网格交易器 - {grid_data.pair} ({grid_data.uid})")

        self.grid_data = grid_data
        self.client = None  # 初始化时不设置client
        
        self._price_state = PriceState()
        self._order_state = OrderState()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()
        self._lock = threading.Lock()

        print(f"[GridTrader] 交易器初始化完成: {grid_data.uid}")
        print(f"  交易对: {grid_data.pair}")
        print(f"  方向: {grid_data.direction}")
        print(f"  总层数: {len(grid_data.grid_levels)}")

    def set_client(self, client: BaseClient):
        """设置交易所客户端并连接信号"""
        print(f"\n[GridTrader] === 设置交易所客户端 === {self.grid_data.uid}")
        print(f"[GridTrader] 新客户端: {client}")
        
        # 如果已有client，先断开旧的信号连接
        if self.client:
            try:
                print("[GridTrader] 断开旧client信号连接")
                self.client.order_updated.disconnect(self._on_order_update)
            except TypeError:
                pass

        self.client = client
        
        # 连接新的信号
        if client:
            print("[GridTrader] 连接新client的order_updated信号")
            client.order_updated.connect(self._on_order_update)
            print("[GridTrader] 客户端设置完成")

    def start(self) -> bool:
        """启动策略"""
        print(f"\n[GridTrader] === 启动策略 === {self.grid_data.uid}")
        
        if self._running:
            print(f"[GridTrader] 策略已在运行中")
            return False

        # 如果有旧线程引用，先清理
        if self._thread:
            print(f"[GridTrader] 清理旧线程引用: {self._thread.name}")
            self._thread = None

        # 创建新线程
        thread_name = f"GridTrader-{self.grid_data.pair}-{self.grid_data.uid}"
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
        return True

    def stop(self) -> bool:
        """停止策略"""
        print(f"\n[GridTrader] === 停止策略 === {self.grid_data.uid}")
        
        if not self._running:
            print("[GridTrader] 策略未在运行中")
            # 清理可能存在的旧线程引用
            self._thread = None
            return True

        # 设置停止标志
        self._stop_flag.set()
        self._running = False

        # 等待线程结束
        if self._thread:
            print(f"[GridTrader] 等待线程 {self._thread.name} 结束")
            if self._thread.is_alive():
                self._thread.join(timeout=2)  # 只在线程活跃时调用 join
            else:
                print(f"[GridTrader] 线程 {self._thread.name} 已经结束，跳过 join 调用")
            
            # 强制清理线程引用
            self._thread = None

        print("[GridTrader] 策略已停止")
        return True

    def _run_strategy(self):
        """策略主循环"""
        thread_name = threading.current_thread().name
        thread_id = threading.current_thread().ident
        print(f"\n[GridTrader] === 策略线程启动 ===")
        print(f"[GridTrader] 线程名称: {thread_name}")
        print(f"[GridTrader] 线程ID: {thread_id}")
        print(f"[GridTrader] 策略初始状态:")
        print(f"  交易对: {self.grid_data.pair}")
        print(f"  方向: {self.grid_data.direction}")
        print(f"  总层数: {len(self.grid_data.grid_levels)}")
        print(f"  运行标志: {self._running}")
        
        last_process_time = time.time()
        min_process_interval = 0.1  # 最小处理间隔（秒）
        
        while self._running and not self._stop_flag.is_set():
            try:
                current_time = time.time()
                
                # 控制处理频率
                if current_time - last_process_time < min_process_interval:
                    time.sleep(0.01)  # 短暂休眠
                    continue
                    
                if not self._order_state.pending_order_id:
                    current_price = self.grid_data.last_price
                    if current_price:
                        self._process_price_update()
                
                last_process_time = current_time
                
            except Exception as e:
                print(f"[GridTrader] 策略线程 {thread_name} 执行错误: {e}")
                print(f"[GridTrader] 错误详情: {traceback.format_exc()}")
                break
                
        print(f"[GridTrader] === 策略线程退出 ===")
        print(f"[GridTrader] 线程名称: {thread_name}")
        print(f"[GridTrader] 线程ID: {thread_id}")
        print(f"[GridTrader] 退出原因: {'停止标志被设置' if self._stop_flag.is_set() else '运行标志为False'}")

    def handle_error(self, error_msg: str):
        """处理错误并暂停策略"""
        print(f"[GridTrader] 策略错误: {error_msg}")
        self.error_occurred.emit(self.grid_data.uid, error_msg)
        self.stop()  # 暂停策略运行

    @error_handler()
    def _on_order_update(self, order_id: str, order_data: dict):
        """处理订单更新"""
        if order_id != self._order_state.pending_order_id:
            return
        try:
            if order_data["status"] == "filled":
                level = self._order_state.current_level
                self.grid_data.update_order_fill(level, order_data)
                self._order_state.clear_pending_order()
                print(f"[GridTrader] Order filled: {order_id} for level {level}")
                
        except Exception as e:
            print(f"[GridTrader] Error processing order update: {e}")
            self.error_occurred.emit(self.grid_data.uid, f"订单更新处理失败: {str(e)}")

    @error_handler()
    def _check_first_grid(self, current_price: Decimal) -> bool:
        """
        检查第一层网格开仓条件
        目前直接返回True，后续可以根据需求完善逻辑
        """
        print(f"\n[GridTrader] === 检查第一层网格开仓条件 ===")
        print(f"[GridTrader] 当前价格: {current_price}")
        return True

    @error_handler()
    def _check_rebound(self, current_price: Decimal, level_config, is_open: bool) -> bool:
        """
        检查反弹条件
        Args:
            current_price: 当前价格
            level_config: 层级配置
            is_open: True表示开仓检查，False表示平仓检查
        """
        if not self._price_state.extreme_price:
            return False

        # 根据开平仓选择不同的反弹百分比
        rebound = (level_config.open_rebound_percent if is_open else level_config.close_rebound_percent) / Decimal('100')
        is_long = self.grid_data.is_long()

        if is_open:  # 开仓反弹检查
            if is_long:
                # 做多时，计算从最低点反弹的百分比
                price_diff = current_price - self._price_state.extreme_price
                rebound_ratio = price_diff / self._price_state.extreme_price
                print(f"[GridTrader] 做多开仓反弹检查:")
                print(f"  当前价格: {current_price}")
                print(f"  最低价: {self._price_state.extreme_price}")
                print(f"  反弹比例: {rebound_ratio}")
                print(f"  目标比例: {rebound}")
                return rebound_ratio >= rebound
            else:
                # 做空时，计算从最高点回落的百分比
                price_diff = self._price_state.extreme_price - current_price
                rebound_ratio = price_diff / self._price_state.extreme_price
                print(f"[GridTrader] 做空开仓回落检查:")
                print(f"  当前价格: {current_price}")
                print(f"  最高价: {self._price_state.extreme_price}")
                print(f"  回落比例: {rebound_ratio}")
                print(f"  目标比例: {rebound}")
                return rebound_ratio >= rebound
        else:  # 平仓反弹检查
            if is_long:
                # 做多时，计算从最高点回落的百分比
                price_diff = self._price_state.tp_extreme_price - current_price
                rebound_ratio = price_diff / self._price_state.tp_extreme_price
                print(f"[GridTrader] 做多平仓回落检查:")
                print(f"  当前价格: {current_price}")
                print(f"  最高价: {self._price_state.tp_extreme_price}")
                print(f"  回落比例: {rebound_ratio}")
                print(f"  目标比例: {rebound}")
                return rebound_ratio >= rebound
            else:
                # 做空时，计算从最低点反弹的百分比
                price_diff = current_price - self._price_state.tp_extreme_price
                rebound_ratio = price_diff / self._price_state.tp_extreme_price
                print(f"[GridTrader] 做空平仓反弹检查:")
                print(f"  当前价格: {current_price}")
                print(f"  最低价: {self._price_state.tp_extreme_price}")
                print(f"  反弹比例: {rebound_ratio}")
                print(f"  目标比例: {rebound}")
                return rebound_ratio >= rebound

    def _get_last_take_profit_price(self, level: int) -> Optional[Decimal]:
        """获取某层最近一次的止盈价格"""
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
        """检查开仓条件"""
        operation_status = self.grid_data.row_dict.get("操作", {})
        can_open = operation_status.get("开仓", False)
        if not can_open:
            print(f"[GridTrader] 开仓操作被禁用")
            return

        print(f"\n[GridTrader] === 检查开仓条件 === {self.grid_data.pair} {self.grid_data.uid}")
        next_level = self.grid_data.get_next_level()
        total_levels = len(self.grid_data.grid_levels)
        
        # 检查是否已满层
        if next_level is None or next_level >= total_levels:
            print("[GridTrader] 已达到最大层数或超出范围，不再开仓")
            return

        level_config = self.grid_data.grid_levels[next_level]
        is_long = self.grid_data.is_long()
        
        # 第一层网格特殊处理
        if next_level == 0:
            if self._check_first_grid(current_price):
                self._place_order(next_level)
            return

        # 获取上一次止盈价格
        last_tp_price = self._get_last_take_profit_price(next_level)
        
        # 计算触发价格（如果尚未设置）
        if not self._price_state.trigger_price:
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

        # 如果有平仓历史
        if last_tp_price:
            print(f"[GridTrader] 检查开仓条件 - 存在平仓历史")
            print(f"上次平仓价格: {last_tp_price}")
            print(f"当前价格: {current_price}")
            
            # 如果当前价格高于平仓价格
            if current_price > last_tp_price:
                print(f"[GridTrader] 当前价格高于平仓价格，等待回落")
                return
                
            # 价格低于平仓价格，开始寻找底部
            if not self._price_state.extreme_price:
                self._price_state.extreme_price = current_price
            else:
                if is_long:
                    self._price_state.extreme_price = min(self._price_state.extreme_price, current_price)
                else:
                    self._price_state.extreme_price = max(self._price_state.extreme_price, current_price)
            
            # 检查反弹条件
            if not self._check_rebound(current_price, level_config, is_open=True):
                return
                
            # 满足反弹条件，下单
            print(f"[GridTrader] 满足反弹条件，准备下单")
            self._place_order(next_level)
            return

        # 如果没有平仓历史，使用原有逻辑
        print(f"[GridTrader] 当前市场价格: {current_price}")
        print(f"[GridTrader] 开仓触发价格: {self._price_state.trigger_price}")

        triggered = False
        if is_long:
            triggered = current_price <= self._price_state.trigger_price
        else:
            triggered = current_price >= self._price_state.trigger_price

        self.grid_data.row_dict["开仓触发价"] = str(self._price_state.trigger_price)

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
    def _process_price_update(self):
        """处理价格更新"""
        if not self.grid_data.last_price:
            return
        
        try:
            current_price = self.grid_data.last_price
            grid_status = self.grid_data.get_grid_status()
            
            if not grid_status["is_configured"]:
                return
            
            # 计算当前浮动盈亏
            position_metrics = self.grid_data.calculate_position_metrics()
            unrealized_pnl = position_metrics['unrealized_pnl']
            
            # 检查总体止损条件（使用浮动盈亏判断）
            if grid_status["filled_levels"] > 0 and self.grid_data.check_stop_loss_condition(unrealized_pnl):
                self._close_all_positions("总体止损触发，全部平仓")
                return

            # 继续原有的网格交易逻辑
            if grid_status["filled_levels"] > 0 and self.grid_data.row_dict["操作"]["平仓"]:
                if self._check_take_profit(current_price):
                    return
                    
            if not grid_status["is_full"] and self.grid_data.row_dict["操作"]["开仓"]:
                self._check_open_position(current_price)
                
        except Exception as e:
            error_msg = f"处理价格更新错误: {str(e)}"
            self.logger.error(error_msg)
            self.error_occurred.emit(self.grid_data.uid, error_msg)

    @error_handler()
    def _handle_order_update(self, order_id: str, order_data: dict):
        """处理订单状态更新"""
        print(f"\n[GridTrader] === 订单状态更新 ===")
        print(f"[GridTrader] 订单ID: {order_id}")
        print(f"[GridTrader] 订单数据: {order_data}")
        
        if not self._order_state.pending_order_id == order_id:
            print(f"[GridTrader] 非当前待处理订单，忽略")
            return
            
        try:
            status = order_data.get('status')
            if status == 'filled':
                print(f"[GridTrader] 订单已成交，开始处理成交明细")
                current_level = self._order_state.current_level
                is_spot = self.grid_data.inst_type == "SPOT"

                # 查询成交明细
                fills = self.client.rest_api.get_fills(
                    symbol=self.grid_data.pair.replace('/', ''),
                    order_id=order_id
                )
                print(f"[GridTrader] 成交明细响应: {fills}")

                if isinstance(fills, dict) and fills.get('code') == '00000':
                    # 获取成交列表
                    if is_spot:
                        fill_list = fills.get('data', [])
                    else:
                        fill_list = fills.get('data', {}).get('fillList', [])

                    # 处理成交数据
                    fill_data = self._process_fills(fill_list, is_spot)
                    if fill_data:
                        # 添加订单ID和状态
                        fill_data['orderId'] = order_id
                        fill_data['status'] = status
                        
                        print(f"[GridTrader] 成交数据汇总:")
                        print(f"  成交均价: {fill_data['filled_price']}")
                        print(f"  成交数量: {fill_data['filled_amount']}")
                        print(f"  成交金额: {fill_data['filled_value']}")
                        print(f"  手续费: {fill_data['fee']}")

                        # 如果是平仓订单（网格止盈或总体止损），计算实现盈亏
                        trade_side = order_data.get('trade_side')
                        print(f"[GridTrader] 交易方向: {trade_side}")
                        if trade_side == 'close':
                            level_config = self.grid_data.grid_levels.get(current_level)
                            if level_config and level_config.filled_price:
                                # 计算本次实现盈亏
                                entry_price = level_config.filled_price
                                exit_price = Decimal(str(fill_data['filled_price']))
                                filled_amount = Decimal(str(fill_data['filled_amount']))
                                fee = Decimal(str(fill_data['fee']))

                                # 根据方向计算盈亏
                                if self.grid_data.is_long():
                                    realized_profit = (exit_price - entry_price) * filled_amount
                                else:
                                    realized_profit = (entry_price - exit_price) * filled_amount

                                # 扣除手续费
                                realized_profit -= fee

                                print(f"[GridTrader] 盈亏计算:")
                                print(f"  开仓价: {entry_price}")
                                print(f"  平仓价: {exit_price}")
                                print(f"  数量: {filled_amount}")
                                print(f"  手续费: {fee}")
                                print(f"  实现盈亏: {realized_profit}")
                                
                                # 添加到累计已实现盈利并检查止盈条件
                                if self.grid_data.add_realized_profit(realized_profit):
                                    print(f"[GridTrader] 达到总体止盈条件，准备全部平仓")
                                    self._close_all_positions("达到总体止盈目标，全部平仓")
                                    return

                        # 更新网格数据
                        self.grid_data.update_order_fill(current_level, fill_data)
                        self._order_state.clear_pending_order()
                        
                        print(f"[GridTrader] 成交数据更新完成")
                else:
                    self.logger.error(f"[GridTrader] 获取成交明细失败: {fills}")
            else:
                print(f"[GridTrader] 订单状态: {status}，等待成交")            
        except Exception as e:
            error_msg = f"处理订单更新失败: {str(e)}"
            print(f"[GridTrader] {error_msg}")
            self.logger.error(f"[GridTrader] 错误详情: {traceback.format_exc()}")
            self.error_occurred.emit(self.grid_data.uid, error_msg)

    @error_handler()
    def _check_take_profit(self, current_price: Decimal) -> bool:
        """检查止盈条件"""
        operation_status = self.grid_data.row_dict.get("操作", {})
        can_close = operation_status.get("平仓", False)
        # print(f"[GridTrader] 检查平仓状态: {can_close}")
        if not can_close:
            print(f"[GridTrader] 平仓操作被禁用")
            return False
        last_level = self.grid_data.get_last_filled_level() 
        level_config = self.grid_data.grid_levels[last_level]   # 获取最后层的配置
        # print(f"[GridTrader] 最后层配置: {level_config}")
        print(f"\n[GridTrader] === 检查止盈条件 === {self.grid_data.pair} {self.grid_data.uid}")
        ts = self.grid_data.row_dict["时间戳"]
        print(f"[GridTrader] 当前时间戳 {ts}")
        # 获取最后已成交层级
        if last_level is None:
            print("[GridTrader] 未找到已成交的层级，无法检查止盈条件")
            return False
        # print(f"[GridTrader] 最后已成交层级: {last_level}")
        # print(f"  成交价格: {level_config.filled_price}")
        # print(f"  止盈百分比: {level_config.take_profit_percent}%")
        is_long = self.grid_data.is_long()
        print(f"[GridTrader] 策略方向: {'做多' if is_long else '做空'}")

        # 计算止盈触发价（如果尚未设置）
        if not self._price_state.tp_trigger_price:
            profit_percent = level_config.take_profit_percent / Decimal('100')
            if is_long:
                self._price_state.tp_trigger_price = level_config.filled_price * (Decimal('1') + profit_percent)
            else:
                self._price_state.tp_trigger_price = level_config.filled_price * (Decimal('1') - profit_percent)

            print(f"[GridTrader] 计算止盈触发价: {self._price_state.tp_trigger_price}")
            self.grid_data.row_dict["止盈触发价"] = str(self._price_state.tp_trigger_price)
            print(f"[GridTrader] 止盈百分比: {level_config.take_profit_percent}%")

        # 打印当前触发价格和市场价格
        print(f"[GridTrader] 当前市场价格: {current_price}")
        print(f"[GridTrader] 止盈触发价格: {self._price_state.tp_trigger_price}")
        print(f"[GridTrader] 止盈百分比: {level_config.take_profit_percent}%")
        # 检查是否达到触发价
        triggered = False
        if is_long:
            triggered = current_price >= self._price_state.tp_trigger_price
        else:
            triggered = current_price <= self._price_state.tp_trigger_price
        if triggered:
            print(f"[GridTrader] === 达到止盈触发条件 ===")
            # 更新止盈极值价格
            if not self._price_state.tp_extreme_price:
                self._price_state.tp_extreme_price = current_price
                print(f"[GridTrader] 初始化止盈极值价格: {self._price_state.tp_extreme_price}")
            else:
                if is_long:
                    self._price_state.tp_extreme_price = max(self._price_state.tp_extreme_price, current_price)
                else:
                    self._price_state.tp_extreme_price = min(self._price_state.tp_extreme_price, current_price)
                print(f"[GridTrader] 更新止盈极值价格: {self._price_state.tp_extreme_price}")
            # 检查回调条件
            if self._check_profit_rebound(current_price, level_config):
                print(f"[GridTrader] 止盈回调条件满足，准备下止盈单")
                self._place_take_profit_order(last_level)
                print("[GridTrader] 止盈单已下，重置价格状态")
                self._price_state.reset()  # 重置状态，准备下一次开仓
                return True
            else:
                print("[GridTrader] 止盈回调条件未满足，继续等待")
        else:
            print("[GridTrader] 未达到止盈触发条件，继续观察")
        return False

    @error_handler()
    def _check_profit_rebound(self, current_price: Decimal, level_config) -> bool:
        """检查止盈回调条件"""
        if not self._price_state.tp_extreme_price:
            return False

        rebound = level_config.close_rebound_percent / Decimal('100')
        is_long = self.grid_data.is_long()

        if is_long:
            # 做多时，计算从最高点回落的百分比
            price_diff = self._price_state.tp_extreme_price - current_price
            rebound_ratio = price_diff / self._price_state.tp_extreme_price
            return rebound_ratio >= rebound
        else:
            # 做空时，计算从最低点反弹的百分比
            price_diff = current_price - self._price_state.tp_extreme_price
            rebound_ratio = price_diff / self._price_state.tp_extreme_price
            return rebound_ratio >= rebound

    @error_handler()
    def _process_fills(self, fills_data: list, is_spot: bool) -> dict:
        """处理成交数据"""
        self.logger.info(f"{self.grid_data.inst_type} {self.grid_data.uid} {self.grid_data.pair} 处理成交数据...")
        total_price = Decimal('0')
        total_size = Decimal('0')
        total_amount = Decimal('0')
        total_fee = Decimal('0')
        total_profit = Decimal('0')  # 添加收益累计

        reference_price = self.grid_data.last_price

        if not fills_data:
            self.logger.info("not fills_data")
            return None
                
        self.logger.info(f"fills_data: {fills_data}")
        
        for fill in fills_data:
            try:
                if is_spot:
                    # 现货格式处理
                    price = adjust_decimal_places(
                        fill.get('priceAvg', '0'), 
                        reference_price
                    )
                    size = adjust_decimal_places(
                        fill.get('size', '0'),
                        reference_price
                    )
                    amount = Decimal(str(fill.get('amount', '0')))
                    fee_detail = fill.get('feeDetail', {})
                    if fee_detail:
                        fee = Decimal(str(fee_detail.get('totalFee', '0')))
                        total_fee += abs(fee)
                    # 获取现货收益
                    profit_str = find_value(fill, 'profit')
                    if profit_str:
                        profit = Decimal(str(profit_str))
                        total_profit += profit
                else:
                    # 合约格式处理
                    price = adjust_decimal_places(
                        fill.get('price', '0'), 
                        reference_price
                    )
                    size = adjust_decimal_places(
                        fill.get('baseVolume', '0'),
                        reference_price
                    )
                    amount = Decimal(str(fill.get('quoteVolume', '0')))
                    fee_details = fill.get('feeDetail', [])
                    if fee_details:
                        fee = Decimal(str(fee_details[0].get('totalFee', '0')))
                        total_fee += abs(fee)
                    # 获取合约收益
                    profit_str = find_value(fill, 'profit')
                    if profit_str:
                        profit = Decimal(str(profit_str))
                        total_profit += profit

                if not is_spot:
                    total_price += price * size
                total_size += size
                total_amount += amount

            except Exception as e:
                self.logger.error(f"[GridTrader] 处理成交记录错误: {e}")
                print(f"[GridTrader] 成交记录: {fill}")
                continue

        # 计算均价
        avg_price = (total_price / total_size) if not is_spot and total_size > 0 else price

        result = {
            'filled_price': avg_price,
            'filled_amount': total_size,
            'filled_value': total_amount,
            'fee': total_fee,
            'profit': total_profit  # 统一返回收益
        }

        print(f"[GridTrader] 成交数据处理结果:")
        print(f"  均价: {result['filled_price']}")
        print(f"  数量: {result['filled_amount']}")
        print(f"  金额: {result['filled_value']}")
        print(f"  手续费: {result['fee']}")
        print(f"  收益: {result['profit']}")

        return result

    @error_handler()
    def _place_order(self, level: int) -> None:
        """下开仓单"""
        try:
            self.logger.info(f"{self.grid_data.inst_type} {self.grid_data.uid} {self.grid_data.pair} 准备开仓-{level}")
            level_config = self.grid_data.grid_levels[level]
            is_long = self.grid_data.is_long()
            is_spot = self.grid_data.inst_type == "SPOT"

            # 首先验证投资金额是否满足最小要求
            # invest_amount = level_config.invest_amount
            # min_value = self.grid_data.min_trade_value or Decimal('5')
            # if invest_amount < min_value:
            #     raise ValueError(f"投资金额 {invest_amount} USDT 小于最小交易额 {min_value} USDT")

            # 计算下单数量
            if is_spot:
                order_size = float(level_config.invest_amount)
            else:
                order_size = float(level_config.invest_amount / self.grid_data.last_price)

            # 使用缓存的精度进行处理
            precision = self.grid_data.quantity_precision or 4  # 默认精度为4
            order_size = float(Decimal(str(order_size)).quantize(
                Decimal('0.' + '0' * precision),
                rounding=ROUND_HALF_UP
            ))

            # 检查最小交易量/额
            # min_amount = self.grid_data.min_trade_amount or Decimal('0')
            # min_value = self.grid_data.min_trade_value or Decimal('5')

            # if Decimal(str(order_size)) < min_amount:
            #     raise ValueError(f"下单数量 {order_size} 小于最小交易量 {min_amount}")

            # order_value = Decimal(str(order_size)) * Decimal(str(self.grid_data.last_price))
            # if order_value < min_value:
            #     raise ValueError(f"下单金额 {order_value} 小于最小交易额 {min_value}")
            
            self.logger.debug(f"[GridTrader] 订单详情:")
            self.logger.debug(f"  网格层级: {level}")
            self.logger.debug(f"  方向: {'做多' if is_long else '做空'}")
            self.logger.debug(f"  是否现货: {is_spot}")
            self.logger.debug(f"  投资金额: {level_config.invest_amount}")
            self.logger.debug(f"  下单size: {order_size}")
            self.logger.debug(f"  当前价格: {self.grid_data.last_price}")

            # 生成客户端订单ID
            client_order_id = f"grid_{self.grid_data.uid}_{level}_{int(time.time()*1000)}"
            
            # 发送订单
            response = self.client.rest_api.place_order(
                symbol=self.grid_data.pair.replace('/', ''),
                size=str(order_size),
                trade_side="open",
                side="buy" if is_long else "sell",
                client_oid=client_order_id
            )
            self.trade_logger.info(f"[GridTrader] 下单结果 - {self.grid_data.uid} - {response}")

            # 处理下单响应
            if isinstance(response, dict) and response.get('code') == '00000':
                order_id = response['data']['orderId']
                self._order_state.set_pending_order(order_id, level)
                
                time.sleep(0.5)  # 短暂延迟确保成交明细可查

                # 查询成交明细
                fills = self.client.rest_api.get_fills(
                    symbol=self.grid_data.pair.replace('/', ''),
                    order_id=order_id
                )
                self.logger.info(f"[GridTrader] 成交明细响应: {fills}")

                if isinstance(fills, dict) and fills.get('code') == '00000':
                    # 获取成交列表
                    if is_spot:
                        fill_list = fills.get('data', [])
                    else:
                        fill_list = fills.get('data', {}).get('fillList', [])

                    # 处理成交数据
                    fill_data = self._process_fills(fill_list, is_spot)
                    if fill_data:
                        # 添加订单ID和状态
                        fill_data['orderId'] = order_id
                        fill_data['status'] = 'filled'
                        
                        self.logger.debug(f"[GridTrader] 汇总数据:")
                        self.logger.debug(f"  成交均价: {fill_data['filled_price']}")
                        self.logger.debug(f"  成交数量: {fill_data['filled_amount']}")
                        self.logger.debug(f"  成交金额: {fill_data['filled_value']}")
                        self.logger.debug(f"  手续费: {fill_data['fee']}")

                        # 更新网格数据
                        self.grid_data.update_order_fill(level, fill_data, "open")
                        self._order_state.clear_pending_order()
                        self._price_state.reset()
                    else:
                        error_msg = "无效的成交数据"
                        self.error_occurred.emit(self.grid_data.uid, error_msg)
                        self.stop()

                else:
                    error_msg = f"获取成交明细失败: {fills}"
                    self.logger.error(f"[GridTrader] {error_msg}")
                    self.error_occurred.emit(self.grid_data.uid, error_msg)
                    self.stop()
            else:
                error_msg = f"下单失败: {response}"
                self.logger.error(f"[GridTrader] {error_msg}")
                self.error_occurred.emit(self.grid_data.uid, error_msg)
                self.stop()

        except Exception as e:
            error_msg = f"下单错误: {str(e)}"
            self.trade_logger.error(f"下单错误 - {self.grid_data.uid}", exc_info=e)
            self.handle_error(error_msg)

    @error_handler()
    def _place_take_profit_order(self, level: int) -> None:
        """下止盈单"""
        try:
            level_config = self.grid_data.grid_levels[level]
            is_long = self.grid_data.is_long()
            is_spot = self.grid_data.inst_type == "SPOT"
            self.logger.info(f"{self.grid_data.inst_type} {self.grid_data.uid} {self.grid_data.pair} 准备止盈-{level}")

            # 计算下单数量
            if not is_spot:
                # 合约使用持仓数量直接平仓
                order_size = float(level_config.filled_amount)
            else:
                # 现货需要根据当前价格计算数量，并考虑手续费
                order_size = float(level_config.invest_amount / self.grid_data.last_price) * 0.998
                    
            # 使用缓存的精度进行处理
            precision = self.grid_data.quantity_precision or 4  # 默认精度为4
            order_size = float(Decimal(str(order_size)).quantize(
                Decimal('0.' + '0' * precision),
                rounding=ROUND_HALF_UP
            ))
                
            self.logger.debug(f"[GridTrader] 止盈订单详情:")
            self.logger.debug(f"  网格层级: {level}")
            self.logger.debug(f"  方向: {'卖出' if is_long else '买入'}")
            self.logger.debug(f"  是否现货: {is_spot}")
            self.logger.debug(f"  开仓价格: {level_config.filled_price}")
            self.logger.debug(f"  持仓数量: {order_size}")
            self.logger.debug(f"  当前价格: {self.grid_data.last_price}")

            # 生成客户端订单ID
            client_order_id = f"grid_{self.grid_data.uid}_{level}_{int(time.time()*1000)}_tp"

            # 发送止盈订单
            if is_spot:
                response = self.client.rest_api.place_order(
                    symbol=self.grid_data.pair.replace('/', ''),
                    size=str(order_size),  
                    trade_side="close",  # 现货API会根据trade_side自动设置买卖方向
                    client_oid=client_order_id
                )
            else:
                # 合约止盈订单
                response = self.client.rest_api.place_order(
                    symbol=self.grid_data.pair.replace('/', ''),
                    size=str(order_size),
                    trade_side="close",
                    side="sell" if not is_long else "buy",  # 做空时平仓需要买入
                    client_oid=client_order_id
                )
            self.logger.info(f"[GridTrader] 止盈订单响应: {response}")

            # 处理下单响应
            if isinstance(response, dict) and response.get('code') == '00000':
                order_id = response['data']['orderId']
                self._order_state.set_pending_order(order_id, level)
                    
                time.sleep(0.5)  # 短暂延迟确保成交明细可查

                # 查询成交明细
                fills = self.client.rest_api.get_fills(
                    symbol=self.grid_data.pair.replace('/', ''),
                    order_id=order_id
                )
                self.logger.info(f"[GridTrader] 止盈成交明细: {fills}")

                if isinstance(fills, dict) and fills.get('code') == '00000':
                    # 获取成交列表
                    if is_spot:
                        fill_list = fills.get('data', [])
                    else:
                        fill_list = fills.get('data', {}).get('fillList', [])

                    # 处理成交数据
                    fill_data = self._process_fills(fill_list, is_spot)
                    if fill_data:
                        self.logger.debug(f"[GridTrader] 止盈成交汇总:")
                        self.logger.debug(f"  开仓价格: {level_config.filled_price}")
                        self.logger.debug(f"  平仓均价: {fill_data['filled_price']}")
                        self.logger.debug(f"  平仓数量: {fill_data['filled_amount']}")
                        self.logger.debug(f"  成交金额: {fill_data['filled_value']}")
                        self.logger.debug(f"  手续费: {fill_data['fee']}")

                        # 计算预期盈亏
                        entry_price = level_config.filled_price if level_config.filled_price else Decimal('0')
                        exit_price = Decimal(str(fill_data['filled_price']))
                        amount = Decimal(str(fill_data['filled_amount']))
                        fee = Decimal(str(fill_data['fee']))
                        
                        if is_long:
                            expected_profit = (exit_price - entry_price) * amount
                        else:
                            expected_profit = (entry_price - exit_price) * amount
                        expected_profit -= fee
                        
                        self.logger.debug(f"  预期盈亏: {expected_profit}")

                        # 更新止盈信息
                        self.grid_data.handle_take_profit(level, fill_data)
                        self._order_state.clear_pending_order()
                        self._price_state.reset()
                        self.logger.debug(f"[GridTrader] 止盈完成，网格已重置")

                        # 检查是否达到总体止盈条件
                        if self.grid_data.check_take_profit_condition():
                            self._close_all_positions("达到总体止盈目标，全部平仓")
                        else:
                            # 立即检查是否可以重新开仓
                            self._check_open_position(self.grid_data.last_price)
                    else:
                        error_msg = "无效的成交数据"
                        self.error_occurred.emit(self.grid_data.uid, error_msg)
                else:
                    error_msg = f"获取成交明细失败: {fills}"
                    self.logger.error(f"[GridTrader] {error_msg}")
                    self.error_occurred.emit(self.grid_data.uid, error_msg)
            else:
                error_msg = f"止盈下单失败: {response}"
                self.logger.error(f"[GridTrader] {error_msg}")
                self.error_occurred.emit(self.grid_data.uid, error_msg)

        except Exception as e:
            error_msg = f"止盈下单错误: {str(e)}"
            self.logger.error(f"[GridTrader] {error_msg}")
            self.logger.error(f"[GridTrader] 错误详情: {traceback.format_exc()}")
            self.handle_error(error_msg)

    def _close_all_positions(self, reason: str) -> bool:
        """
        平掉所有持仓并返回是否成功
        Args:
            reason: 平仓原因
        Returns:
            bool: 是否成功平仓
        """
        try:
            # 记录日志
            self.logger.info(f"{self.grid_data.inst_type} {self.grid_data.uid} {self.grid_data.pair} 准备全平...")
            self.logger.info(f"  原因: {reason}")
            
            # 获取当前持仓信息
            # metrics = self.grid_data.calculate_position_metrics()
            # self.logger.debug(f"  当前持仓: {metrics}")
            
            # if metrics['total_value'] <= 0:
            #     self.logger.info("  无持仓，无需平仓")
            #     return True

            # 准备平仓参数
            symbol = self.grid_data.pair.replace('/', '')
            is_spot = self.grid_data.inst_type == "SPOT"
            is_long = self.grid_data.is_long()
            
            # 合约平仓
            if not is_spot:
                self.logger.debug("  执行合约全部平仓...")
                response = self.client.rest_api.all_close_positions(
                    symbol=symbol,
                    hold_side='long' if is_long else 'short'
                )
                self.logger.info(f"  平仓响应: {response}")
                
                if response.get('code') != '00000':
                    error_msg = f"合约平仓失败: {response.get('msg', '未知错误')}"
                    self.logger.error(f"  {error_msg}")
                    raise ValueError(error_msg)
                    
                # 检查成交明细
                success_list = response.get('data', {}).get('successList', [])
                failure_list = response.get('data', {}).get('failureList', [])
                
                if failure_list:
                    error_msg = f"部分订单失败: {failure_list}"
                    self.logger.error(f"  {error_msg}")
                    raise ValueError(error_msg)
            
            # 现货平仓
            else:
                self.logger.debug("  执行现货全部平仓...")
                failed_levels = []
                
                # 遍历所有已开仓的网格层
                for level, config in self.grid_data.grid_levels.items():
                    if not config.is_filled or not config.filled_amount:
                        continue
                        
                    try:
                        # 计算平仓数量（考虑手续费）
                        close_amount = config.filled_amount * Decimal('0.998')
                        
                        # 使用精度处理
                        precision = self.grid_data.quantity_precision or 4
                        close_amount = float(close_amount.quantize(
                            Decimal('0.' + '0' * precision),
                            rounding=ROUND_HALF_UP
                        ))
                        
                        # 下平仓单
                        response = self.client.rest_api.place_order(
                            symbol=symbol,
                            size=str(close_amount),
                            trade_side="close",
                            side="sell" if is_long else "buy"
                        )
                        
                        if response.get('code') != '00000':
                            failed_levels.append(level)
                            continue
                            
                        # 等待订单成交
                        time.sleep(0.5)
                        
                        # 获取成交明细
                        fills = self.client.rest_api.get_fills(
                            symbol=symbol,
                            order_id=response['data']['orderId']
                        )
                        
                        if fills.get('code') == '00000':
                            fill_data = self._process_fills(fills.get('data', []), True)
                            if fill_data:
                                # 处理该层平仓
                                self.grid_data.handle_take_profit(level, fill_data)
                        else:
                            failed_levels.append(level)
                            
                    except Exception as e:
                        self.logger.error(f"  平仓层级 {level} 失败: {e}")
                        failed_levels.append(level)
                        
                if failed_levels:
                    error_msg = f"以下层级平仓失败: {failed_levels}"
                    self.logger.error(f"  {error_msg}")
                    raise ValueError(error_msg)
            
            # 重置网格配置
            self.grid_data.reset_to_initial()
            
            # 更新UI显示
            self.grid_data.row_dict["运行状态"] = f"已平仓({reason})"
            self.grid_data.data_updated.emit(self.grid_data.uid)
            
            self.logger.info(f"[GridTrader] 平仓完成 - {self.grid_data.uid}")
            return True
            
        except Exception as e:
            error_msg = f"平仓出错: {str(e)}"
            self.logger.error(f"[GridTrader] {error_msg}")
            self.logger.error(f"[GridTrader] 错误详情: {traceback.format_exc()}")
            self.error_occurred.emit(self.grid_data.uid, error_msg)
            return False