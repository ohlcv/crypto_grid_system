# src/strategy/grid/grid_core.py

import threading
import traceback
from typing import Dict, Optional, List
from decimal import Decimal
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from qtpy.QtCore import QObject, Signal
from src.utils.common.tools import find_value
from src.utils.logger.log_helper import grid_logger
from decimal import Decimal
from typing import Optional


class TakeProfitConfig:
    """总体止盈配置"""
    def __init__(self):
        self.enabled: bool = False  # 是否启用
        self.profit_amount: Optional[Decimal] = None  # 止盈金额
        self._original_config = {}  # 保存原始配置，用于恢复

    def enable(self, profit_amount: Decimal) -> None:
        """启用止盈"""
        self.enabled = True
        self.profit_amount = profit_amount

    def disable(self) -> None:
        """禁用止盈"""
        self.enabled = False
        self.profit_amount = None

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'enabled': self.enabled,
            'profit_amount': float(self.profit_amount) if self.profit_amount else None
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'TakeProfitConfig':
        """从字典创建实例"""
        instance = cls()
        instance.enabled = data.get('enabled', False)
        profit_amount = data.get('profit_amount')
        instance.profit_amount = Decimal(str(profit_amount)) if profit_amount is not None else None
        return instance

class StopLossConfig:
    """总体止损配置"""
    def __init__(self):
        self.enabled: bool = False  # 是否启用
        self.loss_amount: Optional[Decimal] = None  # 止损金额
        self._original_config = {}  # 保存原始配置，用于恢复

    def enable(self, loss_amount: Decimal) -> None:
        """启用止损"""
        self.enabled = True
        self.loss_amount = abs(loss_amount)  # 确保为正数

    def disable(self) -> None:
        """禁用止损"""
        self.enabled = False
        self.loss_amount = None

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'enabled': self.enabled,
            'loss_amount': float(self.loss_amount) if self.loss_amount else None
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'StopLossConfig':
        """从字典创建实例"""
        instance = cls()
        instance.enabled = data.get('enabled', False)
        loss_amount = data.get('loss_amount')
        instance.loss_amount = Decimal(str(loss_amount)) if loss_amount is not None else None
        return instance
    
class GridDirection(Enum):
    """网格方向"""
    LONG = "long"   # 做多
    SHORT = "short" # 做空

@dataclass
class LevelConfig:
    """网格层配置"""
    interval_percent: Decimal  # 间隔百分比
    open_rebound_percent: Decimal  # 开仓反弹百分比
    close_rebound_percent: Decimal  # 平仓反弹百分比
    take_profit_percent: Decimal  # 止盈百分比
    invest_amount: Decimal  # 投资金额
    filled_amount: Optional[Decimal] = None  # 成交数量
    filled_price: Optional[Decimal] = None  # 成交价格
    filled_time: Optional[datetime] = None  # 成交时间
    is_filled: bool = False  # 是否已成交
    order_id: Optional[str] = None  # 订单ID

class GridData(QObject):
    """单个网格策略的数据容器"""
    data_updated = Signal(str)

    def __init__(self, uid: str, pair: str, exchange: str, inst_type: str):
        super().__init__()  # 调用 QObject 的初始化方法
        self.uid = uid
        self.pair = pair
        self.exchange = exchange
        self.inst_type = inst_type
        self.direction = GridDirection.LONG  # 默认做多
        self.take_profit_config = TakeProfitConfig()
        self.stop_loss_config = StopLossConfig()
        self.grid_levels: Dict[int, LevelConfig] = {}  # 层号 -> 配置
        self.last_price: Optional[Decimal] = None  # 最新价格
        self.last_update_time: Optional[datetime] = None  # 最后更新时间
        self.total_realized_profit = Decimal('0')  # 添加累计已实现盈利字段

        # 添加交易参数缓存
        self.quantity_precision: Optional[int] = None  # 数量精度
        self.price_precision: Optional[int] = None    # 价格精度
        self.min_trade_amount: Optional[Decimal] = None  # 最小交易数量
        self.min_trade_value: Optional[Decimal] = None   # 最小交易额

        self.row_dict = {
            "交易所": exchange,
            "交易对": pair,
            "方向": "做多",  # 默认做多
            "操作": {"开仓": True, "平仓": True},
            "运行状态": "已添加",
            "当前层数": None,
            "持仓价值": None,
            "持仓盈亏": None,
            "持仓均价": None,
            "最后价格": None,
            "尾单价格": None,
            "开仓触发价": None,
            "止盈触发价": None,
            "实现盈亏": None,    # 新增
            "总体止盈": None,   # 新增
            "总体止损": None,   # 新增
            "最后时间": None,
            "时间戳": None,
            "标识符": uid
        }

        self.logger = grid_logger
        self.logger.info(f"创建网格数据: {pair} ({uid})")

        self._lock = threading.Lock()

    def set_direction(self, is_long: bool):
        """设置交易方向"""
        self.logger.info(f"设置交易方向 - {self.uid} - {'做多' if is_long else '做空'}")
        self.direction = GridDirection.LONG if is_long else GridDirection.SHORT
        self.row_dict["方向"] = self.direction.value 
        self.data_updated.emit(self.uid)

    def update_operation_status(self, operation: dict):
        """更新操作状态"""
        self.logger.info(f"更新操作状态 - {self.uid} - {operation}")
        self.row_dict["操作"] = operation
        self.data_updated.emit(self.uid)

    def reset_level(self, level: int) -> bool:
        """
        重置网格层状态
        返回: 重置是否成功
        """
        # print(f"\n[GridData] === 重置网格层 {level} ===")
        # print(f"[GridData] 当前状态:")
        # print(f"  总层数: {len(self.grid_levels)}")
        
        if level not in self.grid_levels:
            # print(f"[GridData] 错误: 层级 {level} 不存在")
            return False
            
        config = self.grid_levels[level]
        # print(f"[GridData] 重置前配置:")
        # print(f"  {config}")
        
        # 保存原有的网格参数
        saved_params = {
            "interval_percent": config.interval_percent,
            "open_rebound_percent": config.open_rebound_percent,
            "close_rebound_percent": config.close_rebound_percent,
            "take_profit_percent": config.take_profit_percent,
            "invest_amount": config.invest_amount
        }
        self.data_updated.emit(self.uid)
        # print(f"[GridData] 保存的参数: {saved_params}")
        
        # 重新初始化该层配置
        self.grid_levels[level] = LevelConfig(
            interval_percent=saved_params["interval_percent"],
            open_rebound_percent=saved_params["open_rebound_percent"],
            close_rebound_percent=saved_params["close_rebound_percent"],
            take_profit_percent=saved_params["take_profit_percent"],
            invest_amount=saved_params["invest_amount"],
            filled_amount=None,
            filled_price=None,
            filled_time=None,
            is_filled=False,
            order_id=None
        )
        
        # print(f"[GridData] 重置后配置:")
        # print(f"  {self.grid_levels[level]}")
        
        return True

    def is_empty(self) -> bool:
        """检查是否为空配置（无任何网格层）"""
        return len(self.grid_levels) == 0

    def has_filled_levels(self) -> bool:
        """检查是否有已开仓的层级"""
        return any(config.is_filled for config in self.grid_levels.values())

    def reset_to_initial(self):
        """重置到初始状态"""
        self.grid_levels.clear()
        self.row_dict = {
            "交易所": self.exchange,
            "交易对": self.pair,
            "方向": self.direction.value,
            "操作": {"开仓": True, "平仓": True},
            "运行状态": "已添加",
            "当前层数": None,
            "持仓价值": None,
            "持仓盈亏": None,
            "持仓均价": None,
            "最后价格": None,
            "尾单价格": None,
            "开仓触发价": None,
            "止盈触发价": None,
            "实现盈亏": None,    # 新增
            "总体止盈": None,   # 新增
            "总体止损": None,   # 新增
            "最后时间": None,
            "时间戳": None,
            "标识符": self.uid
        }
        self.total_realized_profit = Decimal('0')  # 重置累计盈利
        self.data_updated.emit(self.uid)

    def handle_take_profit(self, level: int, fill_data: dict) -> None:
        """处理止盈成交"""
        with self._lock:
            print(f"\n[GridData] === 处理止盈成交 === Level {level}")
            if level not in self.grid_levels:
                print(f"[GridData] 错误: 层级 {level} 不存在")
                return
            
            config = self.grid_levels[level]
            try:
                # 直接使用收益数据
                realized_profit = Decimal(str(fill_data.get('profit', '0'))) - Decimal(str(fill_data['fee']))

                print(f"[GridData] 盈亏计算:")
                print(f"  收益: {fill_data.get('profit', '0')}")
                print(f"  手续费: {fill_data['fee']}")
                print(f"  净盈亏: {realized_profit}")

                # 记录上次止盈价格（用于下次开仓判断）
                setattr(config, 'last_tp_price', Decimal(str(fill_data['filled_price'])))

                # 更新累计盈亏
                self.total_realized_profit += realized_profit
                self.row_dict["实现盈亏"] = str(self.total_realized_profit)

                print(f"[GridData] 累计已实现盈亏: {self.total_realized_profit}")
                
                # 重置该层状态
                if self.reset_level(level):
                    print(f"[GridData] 层级 {level} 重置成功")
                    # 发送更新信号 - 仅在成功重置后发送
                    self.data_updated.emit(self.uid)
                    print(f"[GridData] 数据更新信号已发送")
                else:
                    print(f"[GridData] 错误: 层级 {level} 重置失败")
                    
            except Exception as e:
                print(f"[GridData] 处理止盈错误: {e}")
                print(f"[GridData] 错误详情: {traceback.format_exc()}")

    def update_order_fill(self, level: int, order_data: dict, trade_side: str = "open") -> None:
        """
        更新订单成交信息
        Args:
            level: 网格层级
            order_data: 订单数据
            trade_side: 交易方向 ('open' 或 'close')
        """
        with self._lock:
            print(f"\n[GridData] === 更新订单成交信息 === Level {level}")
            print(f"[GridData] 交易方向: {trade_side}")
            print(f"[GridData] 订单数据: {order_data}")
            # 校验订单数据
            required_keys = {'filled_amount', 'filled_price', 'orderId'}
            if not required_keys.issubset(order_data):
                print(f"[GridData] 订单数据缺少必要字段: {order_data}")
                return
            if level not in self.grid_levels:
                print(f"[GridData] 层级 {level} 不存在")
                return
            level_config = self.grid_levels[level]
            if trade_side == 'open':  # 开仓更新
                print(f"[GridData] 处理开仓更新")
                # 更新网格层配置
                level_config.filled_amount = order_data['filled_amount']
                level_config.filled_price = order_data['filled_price']
                level_config.filled_time = datetime.now()
                level_config.is_filled = True
                level_config.order_id = order_data['orderId']
                print(f"[GridData] 更新网格配置:")
                print(f"  成交数量: {level_config.filled_amount}")
                print(f"  成交价格: {level_config.filled_price}")
                print(f"  成交时间: {level_config.filled_time}")
                print(f"  订单ID: {level_config.order_id}")
                # 计算止盈价格
                take_profit_price = None
                if level_config.take_profit_percent:
                    if self.is_long():
                        take_profit_price = level_config.filled_price * (Decimal('1') + level_config.take_profit_percent / Decimal('100'))
                    else:
                        take_profit_price = level_config.filled_price * (Decimal('1') - level_config.take_profit_percent / Decimal('100'))
                    print(f"[GridData] 止盈触发价格: {take_profit_price}")
                else:
                    print(f"[GridData] 止盈百分比未配置，无法计算止盈价格")
                # 计算下一层开仓触发价
                trigger_price = None
                if level + 1 in self.grid_levels:
                    next_level_config = self.grid_levels[level + 1]
                    if next_level_config.interval_percent:
                        interval = next_level_config.interval_percent / Decimal('100')
                        if self.is_long():
                            trigger_price = level_config.filled_price * (Decimal('1') - interval)
                        else:
                            trigger_price = level_config.filled_price * (Decimal('1') + interval)
                        print(f"[GridData] 下一层触发价: {trigger_price}")
                    else:
                        print(f"[GridData] 层级 {level + 1} 的间隔百分比未配置，无法计算触发价格")
                else:
                    print("[GridData] 当前已是最后一层，无需计算下一层触发价")
                # 更新策略表格显示
                grid_status = self.get_grid_status()
                if grid_status["is_configured"]:
                    if grid_status["is_full"]:
                        current_level = f"{grid_status['total_levels']}/{grid_status['total_levels']}"
                    else:
                        current_level = f"{grid_status['filled_levels']}/{grid_status['total_levels']}"
                else:
                    current_level = "未设置"
                position_value = level_config.filled_amount * level_config.filled_price
                self.row_dict.update({
                    "当前层数": current_level,
                    "持仓均价": str(level_config.filled_price),
                    "持仓价值": str(position_value),
                    "尾单价格": str(level_config.filled_price),
                    "开仓触发价": str(trigger_price) if trigger_price else "未定义",
                    "止盈触发价": str(take_profit_price) if take_profit_price else "未定义",
                    "持仓盈亏": str(order_data.get('fee', '0')),  # 初始时显示手续费为盈亏
                })
            elif trade_side == 'close':  # 平仓更新
                # print(f"[GridData] 处理平仓更新")
                # 计算平仓盈亏
                profit = (Decimal(str(order_data['filled_price'])) - level_config.filled_price) * Decimal(str(order_data['filled_amount']))
                if not self.is_long():
                    profit = -profit
                fee = Decimal(str(order_data.get('fee', '0')))
                total_profit = profit - fee
            # 发出更新信号
            self.data_updated.emit(self.uid)
            print(f"[GridData] 数据更新完成，已发送更新信号")

    def update_level(self, level: int, config: dict) -> None:
        """更新网格层配置"""
        print(f"\n[GridData] === 更新网格层 {level} ===")
        print(f"[GridData] 配置数据: {config}")
        
        # 获取层级配置
        level_config = self.grid_levels.get(level)
        if not level_config:
            # 如果层级不存在，初始化一个空的 LevelConfig
            self.grid_levels[level] = LevelConfig(
                interval_percent=Decimal('0'),
                open_rebound_percent=Decimal('0'),
                close_rebound_percent=Decimal('0'),
                take_profit_percent=Decimal('0'),
                invest_amount=Decimal('0'),
            )
            level_config = self.grid_levels[level]
            print(f"[GridData] 层级 {level} 初始化完成")

        try:
            # 检查是否有成交信息
            has_filled_data = all(key in config for key in ['filled_amount', 'filled_price', 'filled_time', 'is_filled'])
            print(f"[GridData] 是否包含成交信息: {has_filled_data}")
            
            if has_filled_data:
                # 更新成交信息
                filled_data = {
                    'filled_amount': Decimal(str(config['filled_amount'])) if config['filled_amount'] else None,
                    'filled_price': Decimal(str(config['filled_price'])) if config['filled_price'] else None,
                    'filled_time': config['filled_time'],
                    'is_filled': config['is_filled'],
                    'order_id': config.get('order_id')
                }
                print(f"[GridData] 更新成交信息: {filled_data}")
                
                # 使用object.__setattr__来更新成交信息
                for key, value in filled_data.items():
                    object.__setattr__(level_config, key, value)

            # 更新其他配置参数
            if "间隔%" in config:
                level_config.interval_percent = Decimal(str(config["间隔%"]))
            if "开仓反弹%" in config:
                level_config.open_rebound_percent = Decimal(str(config["开仓反弹%"]))
            if "平仓反弹%" in config:
                level_config.close_rebound_percent = Decimal(str(config["平仓反弹%"]))
            if "止盈%" in config:
                level_config.take_profit_percent = Decimal(str(config["止盈%"]))
            if "成交额" in config:
                level_config.invest_amount = Decimal(str(config["成交额"]))

            print(f"[GridData] 层级 {level} 更新后的配置:")
            print(f"  间隔%: {level_config.interval_percent}")
            print(f"  开仓反弹%: {level_config.open_rebound_percent}")
            print(f"  平仓反弹%: {level_config.close_rebound_percent}")
            print(f"  止盈%: {level_config.take_profit_percent}")
            print(f"  成交额: {level_config.invest_amount}")
            print(f"  是否已成交: {level_config.is_filled}")
            if level_config.is_filled:
                print(f"  成交数量: {level_config.filled_amount}")
                print(f"  成交价格: {level_config.filled_price}")
                print(f"  成交时间: {level_config.filled_time}")
                print(f"  订单ID: {level_config.order_id}")

        except Exception as e:
            print(f"[GridData] 更新层级配置错误: {e}")
            print(f"[GridData] 错误详情: {traceback.format_exc()}")

    def calculate_position_metrics(self) -> dict:
        """
        计算持仓相关指标
        Returns:
            dict: {
                'total_value': 持仓总价值,
                'avg_price': 持仓均价,
                'unrealized_pnl': 未实现盈亏
            }
        """
        try:
            if not self.last_price:
                return {
                    'total_value': Decimal('0'),
                    'avg_price': Decimal('0'),
                    'unrealized_pnl': Decimal('0')
                }

            total_size = Decimal('0')
            total_value = Decimal('0')
            total_cost = Decimal('0')
            current_price = self.last_price

            # 遍历所有已开仓的网格
            for level, config in self.grid_levels.items():
                if config.is_filled and config.filled_amount and config.filled_price:
                    size = config.filled_amount
                    entry_price = config.filled_price
                    
                    # 累加持仓数量和成本
                    total_size += size
                    total_cost += size * entry_price

            # 计算持仓均价
            avg_price = total_cost / total_size if total_size > 0 else Decimal('0')
            
            # 计算当前持仓价值
            total_value = total_size * current_price if total_size > 0 else Decimal('0')
            
            # 计算未实现盈亏
            if total_size > 0:
                if self.is_long():
                    unrealized_pnl = (current_price - avg_price) * total_size
                else:
                    unrealized_pnl = (avg_price - current_price) * total_size
            else:
                unrealized_pnl = Decimal('0')

            return {
                'total_value': total_value.quantize(Decimal('0.00')),
                'avg_price': avg_price.quantize(Decimal('0.0000')),
                'unrealized_pnl': unrealized_pnl.quantize(Decimal('0.0000'))
            }
        except Exception as e:
            self.logger.error(f"计算持仓指标错误: {e}")
            return {
                'total_value': Decimal('0'),
                'avg_price': Decimal('0'),
                'unrealized_pnl': Decimal('0')
            }

    def add_realized_profit(self, profit: Decimal):
        """添加已实现盈利"""
        self.total_realized_profit += profit
        # 更新显示
        self.row_dict["实现盈亏"] = str(self.total_realized_profit)
        self.logger.info(f"[GridData] 更新累计已实现盈利: {self.total_realized_profit}")
        
        # 发送更新信号
        self.data_updated.emit(self.uid)
        
        # 检查是否达到总体止盈条件
        if self.check_take_profit_condition():
            self.logger.info(f"[GridData] 达到总体止盈条件：{self.total_realized_profit} >= {self.take_profit_config.profit_amount}")
            return True
        return False

    def check_take_profit_condition(self) -> bool:
        """检查是否达到总体止盈条件（使用累计已实现盈利）"""
        if not self.take_profit_config.enabled or self.take_profit_config.profit_amount is None:
            return False
        return self.total_realized_profit >= self.take_profit_config.profit_amount
        
    def check_stop_loss_condition(self, unrealized_pnl: Decimal) -> bool:
        """检查是否达到总体止损条件（使用总浮动亏损）"""
        if not self.stop_loss_config.enabled or self.stop_loss_config.loss_amount is None:
            return False
        return unrealized_pnl <= -self.stop_loss_config.loss_amount

    def get_last_filled_level(self) -> Optional[int]:
        """获取最后一个已成交的层级"""
        # with self._lock:
        filled_levels = [
            level for level, config in self.grid_levels.items()
            if config.is_filled
        ]
        # print(f"[GridData] 当前所有已成交层级: {filled_levels}")
        if filled_levels:
            last_level = max(filled_levels)
            # print(f"[GridData] 最后已成交的层级: {last_level}")
            return last_level
        else:
            print("[GridData] 没有找到任何已成交层级")
            return None

    def get_grid_status(self) -> dict:
        """获取网格状态信息"""
        # with self._lock:
        total_levels = len(self.grid_levels)
        if total_levels == 0:
            return {
                "is_configured": False,
                "total_levels": 0,
                "filled_levels": 0,
                "next_level": None,
                "is_full": False
            }
        # 计算已开仓的层数
        filled_levels = sum(1 for config in self.grid_levels.values() if config.is_filled)
        last_filled = max((level for level, config in self.grid_levels.items() 
                        if config.is_filled), default=None)
        next_level = self.get_next_level()
        status = {
            "is_configured": True,
            "total_levels": total_levels,
            "filled_levels": filled_levels,
            "last_filled_level": last_filled,
            "next_level": next_level,
            "is_full": filled_levels == total_levels
        }
        # print(f"[GridData] {self.uid} - 网格状态:")
        # print(f"  总层数: {status['total_levels']}")
        # print(f"  已开仓层数: {status['filled_levels']}")
        # print(f"  最后开仓层: {status['last_filled_level']}")
        # print(f"  下一开仓层: {status['next_level']}")
        # print(f"  是否已满: {status['is_full']}")
        return status

    def get_next_level(self) -> Optional[int]:
        """获取下一个未成交的层级"""
        # with self._lock:
        if not self.grid_levels:  # 未设置网格
            return None
        for level in sorted(self.grid_levels.keys()):
            if not self.grid_levels[level].is_filled:
                return level
        return None  # 已开满仓

    def is_long(self) -> bool:
        """是否做多"""
        return self.direction == GridDirection.LONG

    def is_spot(self) -> bool:
        """是否现货"""
        return self.inst_type == "SPOT"

    def update_market_data(self, data) -> None:
        """更新市场数据"""
        try:
            # 查找价格
            # print(type(data), data)
            price_str = find_value(data, "lastPr")
            if not price_str:
                return   
            new_price = Decimal(str(price_str))
            self.last_price = new_price
            
            # 查找时间戳
            timestamp = find_value(data, "ts")
            if timestamp:
                timestamp = int(timestamp)
                self.last_update_time = datetime.fromtimestamp(timestamp / 1000)

            # 计算持仓指标
            position_metrics = self.calculate_position_metrics()
            
            # 更新表格数据
            self.row_dict.update({
                "最后价格": str(self.last_price),
                "最后时间": self.last_update_time.strftime("%H:%M:%S"),
                "时间戳": timestamp,
                "持仓价值": str(position_metrics['total_value']),
                "持仓均价": str(position_metrics['avg_price']),
                "持仓盈亏": str(position_metrics['unrealized_pnl']),
                "实现盈亏": str(self.total_realized_profit),
            })
            
            # 发送更新信号
            self.data_updated.emit(self.uid)
        
        except Exception as e:
            print(f"更新市场数据错误: {e}")
            print(traceback.format_exc())

    def to_dict(self) -> dict:
        """转换为字典格式"""
        # print(f"[GridData] === 序列化数据 === {self.uid}")
        data = {
            "uid": self.uid,
            "pair": self.pair,
            "exchange": self.exchange,
            "inst_type": self.inst_type,
            "direction": self.direction.value,
            'take_profit_config': self.take_profit_config.to_dict(),
            'stop_loss_config': self.stop_loss_config.to_dict(),
            'total_realized_profit': float(self.total_realized_profit),  # 添加已实现盈利
            "grid_levels": {
                level: {
                    "间隔%": float(config.interval_percent),
                    "开仓反弹%": float(config.open_rebound_percent),
                    "平仓反弹%": float(config.close_rebound_percent),
                    "止盈%": float(config.take_profit_percent),
                    "成交额": float(config.invest_amount),
                    "成交量": float(config.filled_amount) if config.filled_amount else None,
                    "开仓价": float(config.filled_price) if config.filled_price else None,
                    "开仓时间": config.filled_time.isoformat() if config.filled_time else None,
                    "已开仓": config.is_filled,
                    "order_id": config.order_id
                }
                for level, config in self.grid_levels.items()
            },
            "row_dict": self.row_dict
        }
        # print(f"[GridData] 序列化完成: {len(data['grid_levels'])} 层配置")
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'GridData':
        """从字典创建实例"""
        # print(f"[GridData] === 反序列化数据 === {data['uid']}")
        instance = cls(data["uid"], data["pair"], data["exchange"], data["inst_type"])
        instance.direction = GridDirection(data["direction"])
        
        # 恢复网格配置
        for level, config in data["grid_levels"].items():
            level_config = LevelConfig(
                interval_percent=Decimal(str(config["间隔%"])),
                open_rebound_percent=Decimal(str(config["开仓反弹%"])),
                close_rebound_percent=Decimal(str(config["平仓反弹%"])),
                take_profit_percent=Decimal(str(config["止盈%"])),
                invest_amount=Decimal(str(config["成交额"])),
                filled_amount=Decimal(str(config["成交量"])) if config["成交量"] else None,
                filled_price=Decimal(str(config["开仓价"])) if config["开仓价"] else None,
                filled_time=datetime.fromisoformat(config["开仓时间"]) if config["开仓时间"] else None,
                is_filled=config["已开仓"],
                order_id=config["order_id"]
            )
            instance.grid_levels[int(level)] = level_config
        
        # 恢复表格数据
        instance.row_dict = data["row_dict"]
        instance.take_profit_config = TakeProfitConfig.from_dict(data.get('take_profit_config', {}))
        instance.stop_loss_config = StopLossConfig.from_dict(data.get('stop_loss_config', {}))
        instance.total_realized_profit = Decimal(str(data.get('total_realized_profit', '0')))
        # print(f"[GridData] 反序列化完成: {len(instance.grid_levels)} 层配置")
        return instance