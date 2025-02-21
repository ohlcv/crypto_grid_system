# src/strategy/grid/grid_core.py

import threading
import time
import traceback
from typing import Any, Dict, Optional, List
from decimal import Decimal
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from qtpy.QtCore import QObject, Signal
from src.exchange.base_client import InstType, OrderResponse
from src.utils.common.tools import find_value
from src.utils.logger.log_helper import grid_logger
from decimal import Decimal
from typing import Optional


class AvgPriceTakeProfitConfig:
    """均价止盈配置"""
    def __init__(self):
        self.enabled: bool = False  # 是否启用
        self.profit_percent: Optional[Decimal] = None  # 止盈百分比

    def enable(self, profit_percent: Decimal) -> None:
        """启用均价止盈"""
        self.enabled = True
        self.profit_percent = profit_percent

    def disable(self) -> None:
        """禁用均价止盈"""
        self.enabled = False
        self.profit_percent = None

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'enabled': self.enabled,
            'profit_percent': float(self.profit_percent) if self.profit_percent else None
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'AvgPriceTakeProfitConfig':
        """从字典创建实例"""
        instance = cls()
        instance.enabled = data.get('enabled', False)
        profit_percent = data.get('profit_percent')
        instance.profit_percent = Decimal(str(profit_percent)) if profit_percent is not None else None
        return instance

class AvgPriceStopLossConfig:
    """均价止损配置"""
    def __init__(self):
        self.enabled: bool = False  # 是否启用
        self.loss_percent: Optional[Decimal] = None  # 止损百分比

    def enable(self, loss_percent: Decimal) -> None:
        """启用均价止损"""
        self.enabled = True
        self.loss_percent = abs(loss_percent)  # 确保为正数

    def disable(self) -> None:
        """禁用均价止损"""
        self.enabled = False
        self.loss_percent = None

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'enabled': self.enabled,
            'loss_percent': float(self.loss_percent) if self.loss_percent else None
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'AvgPriceStopLossConfig':
        """从字典创建实例"""
        instance = cls()
        instance.enabled = data.get('enabled', False)
        loss_percent = data.get('loss_percent')
        instance.loss_percent = Decimal(str(loss_percent)) if loss_percent is not None else None
        return instance

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

    def __init__(self, uid: str, pair: str, exchange: str, inst_type: InstType):
        super().__init__()  # 调用 QObject 的初始化方法
        self._lock = threading.Lock()
        self.uid = uid
        self.pair = pair
        self.exchange = exchange
        self.inst_type = inst_type
        self.direction = GridDirection.LONG  # 默认做多
        self.grid_levels: Dict[int, LevelConfig] = {}  # 层号 -> 配置
        self.take_profit_config = TakeProfitConfig()
        self.stop_loss_config = StopLossConfig()
        self.avg_price_take_profit_config = AvgPriceTakeProfitConfig()
        self.avg_price_stop_loss_config = AvgPriceStopLossConfig()
        self.last_price: Optional[Decimal] = None  # 最新价格
        self.last_update_time: Optional[datetime] = None  # 最后更新时间
        self.total_realized_profit = Decimal('0')  # 添加累计已实现盈利字段

        # 添加交易参数缓存
        self.quantity_precision: Optional[int] = None  # 数量精度
        self.price_precision: Optional[int] = None    # 价格精度
        self.min_trade_amount: Optional[Decimal] = None  # 最小交易数量
        self.min_trade_value: Optional[Decimal] = None   # 最小交易额

        self._row_dict = {
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
            "均价止盈": None,
            "均价止损": None,
            "总体止盈": None,   # 新增
            "总体止损": None,   # 新增
            "最后时间": None,
            "时间戳": None,
            "标识符": uid
        }

        self.logger = grid_logger
        # self.logger.info(f"创建网格数据: {pair} ({uid})")

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

    @property  
    def row_dict(self) -> dict:
        """获取 row_dict"""
        return self._row_dict
        
    @row_dict.setter
    def row_dict(self, value: dict):
        """设置整个 row_dict"""
        self._row_dict = value
        self.data_updated.emit(self.uid)

    def update_row_dict(self, updates: dict):
        """更新表格显示数据"""
        # print(f"\n[GridData] === 更新表格数据 === {self.uid}")
        # print(f"[GridData] 更新前的数据: {self._row_dict}")
        # print(f"[GridData] 待更新数据: {updates}")

        # 更新数据
        self._row_dict.update(updates)
        # print(f"[GridData] 更新后的数据: {self._row_dict}")
        # print(f"[GridData] 发送数据更新信号...")
        # 发送更新信号
        self.data_updated.emit(self.uid)
        # print(f"[GridData] 数据更新信号已发送")

    def set_row_value(self, key: str, value: Any):
        """设置 row_dict 的单个值"""
        self._row_dict[key] = value 
        self.data_updated.emit(self.uid)

    def set_direction(self, is_long: bool):
        """设置交易方向"""
        self.direction = GridDirection.LONG if is_long else GridDirection.SHORT
        self.row_dict["方向"] = self.direction.value  # 直接使用枚举值
        self.logger.info(f"设置交易方向 - {self.uid} - {self.direction.value}")

    def is_long(self) -> bool:
        """是否做多"""
        return self.direction == GridDirection.LONG

    def update_operation_status(self, operation: dict):
        """更新操作状态"""
        self.logger.info(f"更新操作状态 - {self.uid} - {operation}")
        self.set_row_value("操作", operation)

    def is_empty(self) -> bool:
        """检查是否为空配置（无任何网格层）"""
        return len(self.grid_levels) == 0

    def has_filled_levels(self) -> bool:
        """检查是否有已开仓的层级"""
        return any(config.is_filled for config in self.grid_levels.values())

    def reset_to_initial(self):
        """重置到初始状态"""
        with self._lock:  # 添加锁保护
            # 清空网格配置
            self.grid_levels.clear()
            
            # 重置价格和时间
            self.last_price = None
            self.last_update_time = None
            
            # 重置累计盈利
            self.total_realized_profit = Decimal('0')
            
            # 重置止盈止损配置
            self.take_profit_config.disable()
            self.stop_loss_config.disable()
            
            # 重置表格显示数据
            self.update_row_dict({
                "交易所": self.exchange,
                "交易对": self.pair,
                "方向": self.direction.value,
                "操作": {"开仓": True, "平仓": True},
                "运行状态": "已重置",
                "当前层数": "0/0",  # 修改为更明确的显示
                "持仓价值": "0",   # 使用具体值替代None
                "持仓盈亏": "0",
                "持仓均价": "0",
                "最后价格": "0",
                "尾单价格": "0",
                "开仓触发价": "0",
                "止盈触发价": "0", 
                "实现盈亏": "0",
                "总体止盈": "0",
                "总体止损": "0",
                "最后时间": "",
                "时间戳": "",
                "标识符": self.uid
            })

    def _calculate_profit(self, level: int, fill_data: OrderResponse) -> Decimal:
        """计算止盈订单的收益"""
        try:
            config = self.grid_levels.get(level)
            if not config or not config.is_filled:
                print(f"[GridData] 错误: 层级 {level} 未开仓，无法计算收益")
                return Decimal('0')

            # 获取开仓价格和成交数量
            open_price = config.filled_price
            filled_amount = config.filled_amount
            close_price = fill_data.filled_price

            if not (open_price and filled_amount and close_price):
                print(f"[GridData] 错误: 缺失必要数据 - 开仓价: {open_price}, 数量: {filled_amount}, 平仓价: {close_price}")
                return Decimal('0')

            # 根据方向计算收益
            if self.is_long():
                # 做多：(平仓价 - 开仓价) * 数量
                profit = (close_price - open_price) * filled_amount
            else:
                # 做空：(开仓价 - 平仓价) * 数量
                profit = (open_price - close_price) * filled_amount

            print(f"[GridData] 计算收益:")
            print(f"  开仓价: {open_price}")
            print(f"  平仓价: {close_price}")
            print(f"  数量: {filled_amount}")
            print(f"  粗算收益: {profit}")

            return profit.quantize(Decimal('0.0000'))

        except Exception as e:
            print(f"[GridData] 计算收益错误: {e}")
            print(f"[GridData] 错误详情: {traceback.format_exc()}")
            return Decimal('0')

    def handle_take_profit(self, level: int, fill_data: OrderResponse) -> None:
        """处理止盈成交"""
        with self._lock:
            print(f"\n[GridData] === 处理止盈成交 === Level {level}")
            if level not in self.grid_levels:
                print(f"[GridData] 错误: 层级 {level} 不存在")
                return
            
            config = self.grid_levels[level]
            try:
                # 优先尝试从 fill_data 获取收益
                realized_profit = fill_data.profit or Decimal('0')

                # 如果 profit 未提供或为 0，则通过计算获取
                if not realized_profit:
                    realized_profit = self._calculate_profit(level, fill_data)

                print(f"[GridData] 盈亏计算:")
                print(f"  收益: {realized_profit}")
                print(f"  手续费: {fill_data.fee}")
                print(f"  净盈亏: {realized_profit - fill_data.fee}")

                # 记录上次止盈价格（用于下次开仓判断）
                setattr(config, 'last_tp_price', fill_data.filled_price)

                # 更新累计盈亏（减去手续费）
                net_profit = realized_profit - fill_data.fee
                self.total_realized_profit += realized_profit
                self.row_dict["实现盈亏"] = str(self.total_realized_profit)

                print(f"[GridData] 累计已实现盈亏: {self.total_realized_profit}")
                
                # 重置该层状态
                if self.reset_level(level):
                    print(f"[GridData] 层级 {level} 重置成功")
                    self.data_updated.emit(self.uid)
                    print(f"[GridData] 数据更新信号已发送")
                else:
                    print(f"[GridData] 错误: 层级 {level} 重置失败")
                    
            except Exception as e:
                print(f"[GridData] 处理止盈错误: {e}")
                print(f"[GridData] 错误详情: {traceback.format_exc()}")

    def update_order_fill(self, level: int, fill_response: OrderResponse, trade_type: str = "open") -> None:
        """
        更新订单成交信息
        Args:
            level: 网格层级
            fill_response: 成交响应
            trade_type: 交易类型 ('open'/'close')
        """
        try:
            level_config = self.grid_levels.get(level)
            if not level_config:
                raise ValueError(f"未找到网格层级: {level}")

            if trade_type == 'open':
                # 更新开仓信息
                level_config.filled_amount = fill_response.filled_amount
                level_config.filled_price = fill_response.filled_price
                level_config.filled_time = datetime.fromtimestamp(fill_response.open_time/1000) if fill_response.open_time else datetime.now()
                level_config.is_filled = True
                level_config.order_id = fill_response.order_id

                # 更新网格状态显示
                grid_status = self.get_grid_status()
                current_level = (f"{grid_status['filled_levels']}/{grid_status['total_levels']}" 
                            if grid_status["total_levels"] > 0 else "未设置")
                
                position_value = fill_response.filled_value
                trigger_price = None
                take_profit_price = None
                
                # 计算下一层开仓触发价
                if level + 1 in self.grid_levels:
                    next_config = self.grid_levels[level + 1]
                    interval = next_config.interval_percent / Decimal('100')
                    if self.is_long():
                        trigger_price = fill_response.filled_price * (Decimal('1') - interval)
                    else:
                        trigger_price = fill_response.filled_price * (Decimal('1') + interval)

                # 计算止盈触发价
                if level_config.take_profit_percent:
                    profit_rate = level_config.take_profit_percent / Decimal('100')
                    if self.is_long():
                        take_profit_price = fill_response.filled_price * (Decimal('1') + profit_rate)
                    else:
                        take_profit_price = fill_response.filled_price * (Decimal('1') - profit_rate)

                # 更新表格显示
                self.row_dict.update({
                    "当前层数": current_level,
                    "持仓均价": str(fill_response.filled_price),
                    "持仓价值": str(position_value),
                    "尾单价格": str(fill_response.filled_price),
                    "开仓触发价": str(trigger_price) if trigger_price else "未定义",
                    "止盈触发价": str(take_profit_price) if take_profit_price else "未定义",
                    "持仓盈亏": str(fill_response.fee)
                })
                
            else:  # 平仓更新
                level_config.last_tp_price = fill_response.filled_price  # 记录止盈价格
                self.total_realized_profit += fill_response.profit or Decimal('0')
                self.row_dict["实现盈亏"] = str(self.total_realized_profit)
                
                # 重置该层配置
                self.reset_level(level)

            # 发送数据更新信号
            self.data_updated.emit(self.uid)

        except Exception as e:
            print(f"[GridData] 更新订单成交信息失败: {e}")
            print(f"[GridData] 错误详情: {traceback.format_exc()}")
            raise

    def update_level(self, level: int, config: dict) -> None:
        """更新网格层配置"""
        # print(f"\n[GridData] === 更新网格层 {level} ===")
        # print(f"[GridData] 配置数据: {config}")
        
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
            # print(f"[GridData] 层级 {level} 初始化完成")

        try:
            # 检查是否有成交信息
            has_filled_data = all(key in config for key in ['filled_amount', 'filled_price', 'filled_time', 'is_filled'])
            # print(f"[GridData] 是否包含成交信息: {has_filled_data}")
            
            if has_filled_data:
                # 更新成交信息
                filled_data = {
                    'filled_amount': Decimal(str(config['filled_amount'])) if config['filled_amount'] else None,
                    'filled_price': Decimal(str(config['filled_price'])) if config['filled_price'] else None,
                    'filled_time': config['filled_time'],
                    'is_filled': config['is_filled'],
                    'order_id': config.get('order_id')
                }
                # print(f"[GridData] 更新成交信息: {filled_data}")
                
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

            # print(f"[GridData] 层级 {level} 更新后的配置:")
            # print(f"  间隔%: {level_config.interval_percent}")
            # print(f"  开仓反弹%: {level_config.open_rebound_percent}")
            # print(f"  平仓反弹%: {level_config.close_rebound_percent}")
            # print(f"  止盈%: {level_config.take_profit_percent}")
            # print(f"  成交额: {level_config.invest_amount}")
            # print(f"  是否已成交: {level_config.is_filled}")
            # if level_config.is_filled:
            #     print(f"  成交数量: {level_config.filled_amount}")
            #     print(f"  成交价格: {level_config.filled_price}")
            #     print(f"  成交时间: {level_config.filled_time}")
            #     print(f"  订单ID: {level_config.order_id}")

        except Exception as e:
            print(f"[GridData] 更新层级配置错误: {e}")
            print(f"[GridData] 错误详情: {traceback.format_exc()}")

    def calculate_position_metrics(self) -> dict:
        """计算持仓相关指标"""
        try:
            # print(f"\n[GridData] === 计算持仓指标 ===")
            # print(f"当前价格: {self.last_price}")
            
            # 确保 last_price 是 Decimal 类型
            try:
                current_price = Decimal(str(self.last_price)) if self.last_price else None
            except (TypeError, ValueError):
                current_price = None
                
            if not current_price:
                # print("[GridData] 当前无有效价格")
                return {
                    'total_value': Decimal('0'),
                    'avg_price': Decimal('0'),
                    'unrealized_pnl': Decimal('0'),
                    'total_size': Decimal('0')
                }

            # print(f"网格配置数: {len(self.grid_levels)}")
            
            total_size = Decimal('0')
            total_cost = Decimal('0')

            # 检查每个网格的状态
            for level, config in self.grid_levels.items():
                # print(f"\n检查网格 {level}:")
                # print(f"  已开仓: {config.is_filled}")
                # print(f"  开仓量: {config.filled_amount}")
                # print(f"  开仓价: {config.filled_price}")
                
                if not config.is_filled:
                    # print("  未开仓,跳过")
                    continue
                    
                try:
                    # 确保数据类型转换正确
                    size = Decimal(str(config.filled_amount)) if config.filled_amount else None
                    entry_price = Decimal(str(config.filled_price)) if config.filled_price else None
                    
                    if not (size and entry_price):
                        # print("  无效的开仓数据,跳过")
                        continue
                    
                    # 累加并打印
                    total_size += size
                    total_cost += size * entry_price
                    # print(f"  累计持仓量: {total_size}")
                    # print(f"  累计成本: {total_cost}")
                    
                except (TypeError, ValueError) as e:
                    # print(f"  数据转换错误: {e}")
                    continue

            # 计算结果
            if total_size > 0:
                avg_price = (total_cost / total_size).quantize(Decimal('0.0000'))
                if self.is_spot():
                    total_value = (total_size * current_price).quantize(Decimal('0.00'))
                else:
                    total_value = (total_size * avg_price).quantize(Decimal('0.00'))
                unrealized_pnl = (
                    (current_price - avg_price) * total_size if self.is_long()
                    else (avg_price - current_price) * total_size
                ).quantize(Decimal('0.0000'))
            else:
                avg_price = Decimal('0')
                total_value = Decimal('0')
                unrealized_pnl = Decimal('0')
                
            result = {
                'total_size': total_size,
                'total_value': total_value,
                'avg_price': avg_price,
                'unrealized_pnl': unrealized_pnl,
            }
            
            # print("\n计算结果:")
            # print(f"  总持仓量: {total_size}")
            # print(f"  持仓均价: {result['avg_price']}")
            # print(f"  持仓价值: {result['total_value']}")
            # print(f"  未实现盈亏: {result['unrealized_pnl']}")
            
            return result

        except Exception as e:
            print(f"[GridData] 计算持仓指标错误: {e}")
            print(f"[GridData] 错误详情: {traceback.format_exc()}")
            return {
                'total_value': Decimal('0'),
                'avg_price': Decimal('0'),
                'unrealized_pnl': Decimal('0'),
                'total_size': Decimal('0')
            }

    def calculate_avg_price_tp_sl_prices(self) -> dict:
        """计算均价止盈止损触发价格"""
        result = {
            'avg_tp_price': None,
            'avg_sl_price': None
        }
        
        # 获取持仓均价
        position_metrics = self.calculate_position_metrics()
        avg_price = position_metrics.get('avg_price')
        
        if not avg_price or avg_price == Decimal('0'):
            return result
            
        # 计算均价止盈触发价
        if (self.avg_price_take_profit_config.enabled and 
            self.avg_price_take_profit_config.profit_percent):
            profit_rate = self.avg_price_take_profit_config.profit_percent / Decimal('100')
            if self.is_long():
                result['avg_tp_price'] = avg_price * (Decimal('1') + profit_rate)
            else:
                result['avg_tp_price'] = avg_price * (Decimal('1') - profit_rate)
                
        # 计算均价止损触发价
        if (self.avg_price_stop_loss_config.enabled and 
            self.avg_price_stop_loss_config.loss_percent):
            loss_rate = self.avg_price_stop_loss_config.loss_percent / Decimal('100')
            if self.is_long():
                result['avg_sl_price'] = avg_price * (Decimal('1') - loss_rate)
            else:
                result['avg_sl_price'] = avg_price * (Decimal('1') + loss_rate)
                
        return result

    def update_market_data(self, data) -> None:
        """更新市场数据"""
        try:
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
            # 计算均价止盈止损触发价
            tp_sl_prices = self.calculate_avg_price_tp_sl_prices()
            
            # 更新表格数据
            self.update_row_dict({
                "最后价格": str(self.last_price),
                "最后时间": self.last_update_time.strftime("%H:%M:%S"), 
                "时间戳": timestamp,
                "持仓价值": str(position_metrics['total_value']),
                "持仓均价": str(position_metrics['avg_price']),
                "持仓盈亏": str(position_metrics['unrealized_pnl']),
                "实现盈亏": str(self.total_realized_profit),
                "均价止盈触发价": str(tp_sl_prices['avg_tp_price']) if tp_sl_prices['avg_tp_price'] else "-",
                "均价止损触发价": str(tp_sl_prices['avg_sl_price']) if tp_sl_prices['avg_sl_price'] else "-"
            })
        
        except Exception as e:
            print(f"更新市场数据错误: {e}")
            print(traceback.format_exc())

    def add_realized_profit(self, profit: Decimal):
        """添加已实现盈利"""
        self.total_realized_profit += profit
        # 更新显示
        self.row_dict["实现盈亏"] = str(self.total_realized_profit)
        self.logger.info(f"[GridData] 更新累计已实现盈利: {self.total_realized_profit}")
        
        # 发送更新信号
        self.data_updated.emit(self.uid)
        
        # 检查是否达到总体止盈条件
        position_metrics = self.calculate_position_metrics()
        unrealized_pnl = position_metrics['unrealized_pnl']
        if self._check_take_profit_condition(unrealized_pnl):
            self.logger.info(f"[GridData] 达到总体止盈条件：{self.total_realized_profit} >= {self.take_profit_config.profit_amount}")
            return True
        return False

    def _check_take_profit_condition(self, unrealized_pnl: Decimal) -> bool:
        """检查是否达到总体止盈条件（使用累计已实现盈利）"""
        if not self.take_profit_config.enabled or self.take_profit_config.profit_amount is None:
            return False
        return self.total_realized_profit - unrealized_pnl >= self.take_profit_config.profit_amount
        
    def _check_stop_loss_condition(self, unrealized_pnl: Decimal) -> bool:
        """检查是否达到总体止损条件（使用总浮动亏损）"""
        if not self.stop_loss_config.enabled or self.stop_loss_config.loss_amount is None:
            return False
        return unrealized_pnl <= -self.stop_loss_config.loss_amount

    def _check_avg_price_take_profit_stop_loss(self, current_price: Decimal) -> bool:
        """检查均价止盈止损条件"""
        if not self.has_filled_levels():
            return False
            
        # 获取当前持仓均价
        position_metrics = self.calculate_position_metrics()
        avg_price = position_metrics.get('avg_price')
        if not avg_price:
            return False
            
        # 计算当前价格相对于均价的百分比变化
        price_change_percent = ((current_price - avg_price) / avg_price) * Decimal('100')
        
        # 检查均价止盈条件
        if self.avg_price_take_profit_config.enabled and self.avg_price_take_profit_config.profit_percent:
            if price_change_percent >= self.avg_price_take_profit_config.profit_percent:
                self._close_all_positions("触发均价止盈")
                return True
                
        # 检查均价止损条件
        if self.avg_price_stop_loss_config.enabled and self.avg_price_stop_loss_config.loss_percent:
            if price_change_percent <= -self.avg_price_stop_loss_config.loss_percent:
                self._close_all_positions("触发均价止损")
                return True
                
        return False

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

    def is_spot(self) -> bool:
        return self.inst_type == InstType.SPOT

    def to_dict(self) -> dict:
        """转换为字典格式"""
        data = {
            "uid": self.uid,
            "pair": self.pair,
            "exchange": self.exchange,
            "inst_type": self.inst_type.value,
            "direction": self.direction.value,
            "take_profit_config": self.take_profit_config.to_dict(),
            "stop_loss_config": self.stop_loss_config.to_dict(),
            "total_realized_profit": float(self.total_realized_profit),  # 确保包含实现盈亏
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
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'GridData':
        """从字典创建实例"""
        print(f"[GridData] === 反序列化数据 === {data['uid']}")
        inst_type = InstType(data["inst_type"])
        instance = cls(data["uid"], data["pair"], data["exchange"], inst_type)
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
        
        # 恢复实现盈亏
        instance.total_realized_profit = Decimal(str(data.get('total_realized_profit', '0')))
        instance.row_dict["实现盈亏"] = str(instance.total_realized_profit)
        
        print(f"[GridData] 反序列化完成: {len(instance.grid_levels)} 层配置")
        print(f"[GridData] 恢复实现盈亏: {instance.total_realized_profit}")
        
        return instance
