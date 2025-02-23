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
from src.exchange.base_client import FillResponse, InstType, OrderResponse, PositionSide, TradeSide, SymbolConfig, TickerData
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
    """单个网格策略的数据容器，使用base_client.py中的数据结构"""
    data_updated = Signal(str)  # uid参数

    def __init__(self, uid: str, symbol_config: SymbolConfig, exchange: str, inst_type: InstType):
        super().__init__()
        self._lock = threading.Lock()
        self.uid = uid
        self.symbol_config = symbol_config
        self.exchange_str = exchange
        self.inst_type = inst_type
        self.direction = PositionSide.LONG
        self.grid_levels: Dict[int, LevelConfig] = {}
        self.ticker_data: Optional[TickerData] = None
        self.total_realized_profit = Decimal('0')
        self.status = "已添加"
        self.operations = {"开仓": True, "平仓": True}
        # 添加触发价格属性
        self.open_trigger_price = None
        self.tp_trigger_price = None
        # 添加止盈止损配置
        self.take_profit_config = TakeProfitConfig()
        self.stop_loss_config = StopLossConfig()
        self.avg_price_take_profit_config = AvgPriceTakeProfitConfig()
        self.avg_price_stop_loss_config = AvgPriceStopLossConfig()

    def update_market_data(self, ticker: TickerData) -> None:
        """更新市场数据，使用TickerData"""
        with self._lock:
            self.ticker_data = ticker
            self.data_updated.emit(self.uid)

    def reset_level(self, level: int) -> bool:
        """重置网格层状态"""
        with self._lock:
            if level not in self.grid_levels:
                return False
                
            config = self.grid_levels[level]
            saved_params = {
                "interval_percent": config.interval_percent,
                "open_rebound_percent": config.open_rebound_percent,
                "close_rebound_percent": config.close_rebound_percent,
                "take_profit_percent": config.take_profit_percent,
                "invest_amount": config.invest_amount
            }
            
            self.grid_levels[level] = LevelConfig(
                interval_percent=saved_params["interval_percent"],
                open_rebound_percent=saved_params["open_rebound_percent"],
                close_rebound_percent=saved_params["close_rebound_percent"],
                take_profit_percent=saved_params["take_profit_percent"],
                invest_amount=saved_params["invest_amount"]
            )
            self.data_updated.emit(self.uid)
            return True

    def set_direction(self, is_long: bool):
        """设置交易方向使用PositionSide"""
        self.direction = PositionSide.LONG if is_long else PositionSide.SHORT
        self.data_updated.emit(self.uid)

    def update_operation_status(self, operation: dict):
        """更新操作状态"""
        self.operations = operation.copy()
        self.data_updated.emit(self.uid)

    def reset_to_initial(self):
        """重置到初始状态"""
        with self._lock:
            self.grid_levels.clear()
            self.ticker_data = None
            self.total_realized_profit = Decimal('0')
            self.status = "已重置"
            self.operations = {"开仓": True, "平仓": True}
            self.data_updated.emit(self.uid)

    def update_level(self, level: int, config: dict) -> None:
        """更新网格层配置"""
        with self._lock:
            level_config = self.grid_levels.get(level)
            if not level_config:
                self.grid_levels[level] = LevelConfig(
                    interval_percent=Decimal('0'),
                    open_rebound_percent=Decimal('0'),
                    close_rebound_percent=Decimal('0'),
                    take_profit_percent=Decimal('0'),
                    invest_amount=Decimal('0'),
                )
                level_config = self.grid_levels[level]

            # 处理成交信息
            if 'filled_amount' in config:
                level_config.filled_amount = Decimal(str(config['filled_amount'])) if config['filled_amount'] else None
                level_config.filled_price = Decimal(str(config['filled_price'])) if config['filled_price'] else None
                level_config.filled_time = config['filled_time']
                level_config.is_filled = config['is_filled']
                level_config.order_id = config.get('order_id')
            
            # 处理网格配置 - 使用英文key
            if 'interval_percent' in config:
                level_config.interval_percent = Decimal(str(config['interval_percent']))
            if 'open_rebound_percent' in config:
                level_config.open_rebound_percent = Decimal(str(config['open_rebound_percent']))
            if 'close_rebound_percent' in config:    
                level_config.close_rebound_percent = Decimal(str(config['close_rebound_percent']))
            if 'take_profit_percent' in config:
                level_config.take_profit_percent = Decimal(str(config['take_profit_percent'])) 
            if 'invest_amount' in config:
                level_config.invest_amount = Decimal(str(config['invest_amount']))

    def calculate_position_metrics(self) -> dict:
        """计算持仓相关指标"""
        current_price = self.ticker_data.lastPr if self.ticker_data else Decimal('0')
        total_size = Decimal('0')
        total_cost = Decimal('0')

        for config in self.grid_levels.values():
            if config.is_filled and config.filled_amount and config.filled_price:
                total_size += config.filled_amount
                total_cost += config.filled_amount * config.filled_price

        if total_size > 0:
            avg_price = total_cost / total_size
            total_value = total_size * (current_price if self.is_spot() else avg_price)
            unrealized_pnl = (current_price - avg_price) * total_size if self.is_long() else (avg_price - current_price) * total_size
        else:
            avg_price = total_value = unrealized_pnl = Decimal('0')

        return {
            'total_size': total_size,
            'total_value': total_value.quantize(Decimal('0.00')),
            'avg_price': avg_price.quantize(Decimal('0.0000')),
            'unrealized_pnl': unrealized_pnl.quantize(Decimal('0.0000'))
        }

    def get_grid_status(self) -> dict:
        """获取网格状态信息"""
        total_levels = len(self.grid_levels)
        if total_levels == 0:
            return {
                "is_configured": False,
                "total_levels": 0,
                "filled_levels": 0,
                "next_level": None,
                "is_full": False
            }
            
        filled_levels = sum(1 for config in self.grid_levels.values() if config.is_filled)
        next_level = min([level for level, config in self.grid_levels.items() if not config.is_filled], default=None)
        
        return {
            "is_configured": True,
            "total_levels": total_levels,
            "filled_levels": filled_levels,
            "next_level": next_level,
            "is_full": filled_levels == total_levels
        }

    def to_dict(self) -> dict:
        return {
            "uid": self.uid,
            "symbol_config": {
                "symbol": self.symbol_config.symbol,
                "pair": self.symbol_config.pair,
                "base_coin": self.symbol_config.base_coin,
                "quote_coin": self.symbol_config.quote_coin,
                "base_precision": self.symbol_config.base_precision,
                "quote_precision": self.symbol_config.quote_precision,
                "price_precision": self.symbol_config.price_precision,
                "min_base_amount": str(self.symbol_config.min_base_amount),
                "min_quote_amount": str(self.symbol_config.min_quote_amount)
            },
            "exchange": self.exchange_str,
            "inst_type": self.inst_type.value,
            "direction": self.direction.value,
            "ticker_data": {
                "instId": self.ticker_data.instId,
                "lastPr": str(self.ticker_data.lastPr),
                "ts": self.ticker_data.ts
            } if self.ticker_data else None,
            "total_realized_profit": str(self.total_realized_profit),
            "status": self.status,  # 确保状态被正确保存
            "operations": self.operations.copy(),  # 使用深拷贝
            "grid_levels": {
                str(level): {
                    "interval_percent": str(config.interval_percent),
                    "open_rebound_percent": str(config.open_rebound_percent),
                    "close_rebound_percent": str(config.close_rebound_percent),
                    "take_profit_percent": str(config.take_profit_percent),
                    "invest_amount": str(config.invest_amount),
                    "filled_amount": str(config.filled_amount) if config.filled_amount else None,
                    "filled_price": str(config.filled_price) if config.filled_price else None,
                    "filled_time": config.filled_time.isoformat() if config.filled_time else None,
                    "is_filled": config.is_filled,
                    "order_id": config.order_id
                } for level, config in self.grid_levels.items()
            },
            "open_trigger_price": str(self.open_trigger_price) if self.open_trigger_price else None,
            "tp_trigger_price": str(self.tp_trigger_price) if self.tp_trigger_price else None,
            "take_profit_config": self.take_profit_config.to_dict(),
            "stop_loss_config": self.stop_loss_config.to_dict(),
            "avg_price_take_profit_config": self.avg_price_take_profit_config.to_dict(),
            "avg_price_stop_loss_config": self.avg_price_stop_loss_config.to_dict()
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'GridData':
        symbol_config = SymbolConfig(
            symbol=data["symbol_config"]["symbol"],
            pair=data["symbol_config"]["pair"],
            base_coin=data["symbol_config"]["base_coin"],
            quote_coin=data["symbol_config"]["quote_coin"],
            base_precision=data["symbol_config"]["base_precision"],
            quote_precision=data["symbol_config"]["quote_precision"],
            price_precision=data["symbol_config"]["price_precision"],
            min_base_amount=Decimal(data["symbol_config"]["min_base_amount"]),
            min_quote_amount=Decimal(data["symbol_config"]["min_quote_amount"])
        )
        
        instance = cls(data["uid"], symbol_config, data["exchange"], InstType(data["inst_type"]))
        instance.direction = PositionSide(data["direction"])
        instance.status = data["status"]
        instance.operations = data["operations"]
        instance.total_realized_profit = Decimal(data["total_realized_profit"])

        if data.get("ticker_data"):
            instance.ticker_data = TickerData(
                instId=data["ticker_data"]["instId"],
                lastPr=Decimal(data["ticker_data"]["lastPr"]),
                ts=data["ticker_data"]["ts"]
            )

        for level_str, grid_config in data["grid_levels"].items():
            level = int(level_str)
            instance.grid_levels[level] = LevelConfig(
                interval_percent=Decimal(grid_config["interval_percent"]),
                open_rebound_percent=Decimal(grid_config["open_rebound_percent"]),
                close_rebound_percent=Decimal(grid_config["close_rebound_percent"]),
                take_profit_percent=Decimal(grid_config["take_profit_percent"]),
                invest_amount=Decimal(grid_config["invest_amount"]),
                filled_amount=Decimal(grid_config["filled_amount"]) if grid_config["filled_amount"] else None,
                filled_price=Decimal(grid_config["filled_price"]) if grid_config["filled_price"] else None,
                filled_time=datetime.fromisoformat(grid_config["filled_time"]) if grid_config["filled_time"] else None,
                is_filled=grid_config["is_filled"],
                order_id=grid_config["order_id"]
            )
        
        instance.open_trigger_price = Decimal(data["open_trigger_price"]) if data.get("open_trigger_price") else None
        instance.tp_trigger_price = Decimal(data["tp_trigger_price"]) if data.get("tp_trigger_price") else None
        instance.take_profit_config = TakeProfitConfig.from_dict(data.get("take_profit_config", {}))
        instance.stop_loss_config = StopLossConfig.from_dict(data.get("stop_loss_config", {}))
        instance.avg_price_take_profit_config = AvgPriceTakeProfitConfig.from_dict(data.get("avg_price_take_profit_config", {}))
        instance.avg_price_stop_loss_config = AvgPriceStopLossConfig.from_dict(data.get("avg_price_stop_loss_config", {}))
        
        return instance

    def is_spot(self) -> bool:
        return self.inst_type == InstType.SPOT

    def is_long(self) -> bool:
        """是否做多"""
        return self.direction == PositionSide.LONG

    def is_empty(self) -> bool:
        """检查是否为空配置（无任何网格层）"""
        return len(self.grid_levels) == 0

    def has_filled_levels(self) -> bool:
        """检查是否有已开仓的层级"""
        return any(config.is_filled for config in self.grid_levels.values())

    def update_order_fill(self, level: int, fill_response: 'FillResponse', trade_type: TradeSide = TradeSide.OPEN) -> None:
        try:
            level_config = self.grid_levels.get(level)
            if not level_config:
                raise ValueError(f"未找到网格层级: {level}")

            if trade_type == TradeSide.OPEN:
                level_config.filled_amount = fill_response.filled_base_amount
                level_config.filled_price = fill_response.filled_price
                level_config.filled_time = datetime.fromtimestamp(fill_response.trade_time / 1000) if fill_response.trade_time else datetime.now()
                level_config.is_filled = True
                level_config.order_id = fill_response.order_id

                if level + 1 in self.grid_levels:
                    next_config = self.grid_levels[level + 1]
                    interval = next_config.interval_percent / Decimal('100')
                    if self.is_long():
                        self.open_trigger_price = fill_response.filled_price * (Decimal('1') - interval)
                    else:
                        self.open_trigger_price = fill_response.filled_price * (Decimal('1') + interval)

                if level_config.take_profit_percent:
                    profit_rate = level_config.take_profit_percent / Decimal('100')
                    if self.is_long():
                        self.tp_trigger_price = fill_response.filled_price * (Decimal('1') + profit_rate)
                    else:
                        self.tp_trigger_price = fill_response.filled_price * (Decimal('1') - profit_rate)
            else:  # 平仓更新
                level_config.last_tp_price = fill_response.filled_price
                self.total_realized_profit += fill_response.profit or Decimal('0')
                self.reset_level(level)

            self.data_updated.emit(self.uid)

        except Exception as e:
            print(f"[GridData] 更新订单成交信息失败: {e}")
            raise

    def _calculate_profit(self, level: int, fill_data: 'FillResponse') -> Decimal:
        try:
            config = self.grid_levels.get(level)
            if not config or not config.is_filled:
                print(f"[GridData] 错误: 层级 {level} 未开仓，无法计算收益")
                return Decimal('0')

            open_price = config.filled_price
            filled_amount = config.filled_amount
            close_price = fill_data.filled_price

            if not (open_price and filled_amount and close_price):
                print(f"[GridData] 错误: 缺失必要数据 - 开仓价: {open_price}, 数量: {filled_amount}, 平仓价: {close_price}")
                return Decimal('0')

            if self.is_long():
                profit = (close_price - open_price) * filled_amount
            else:
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

    def handle_take_profit(self, level: int, fill_data: 'FillResponse') -> None:
        with self._lock:
            print(f"\n[GridData] === 处理止盈成交 === Level {level}")
            if level not in self.grid_levels:
                print(f"[GridData] 错误: 层级 {level} 不存在")
                return
            
            config = self.grid_levels[level]
            try:
                realized_profit = fill_data.profit or Decimal('0')
                if not realized_profit:
                    realized_profit = self._calculate_profit(level, fill_data)

                print(f"[GridData] 盈亏计算:")
                print(f"  收益: {realized_profit}")
                print(f"  手续费: {fill_data.fee}")
                print(f"  净盈亏: {realized_profit - (fill_data.fee or Decimal('0'))}")

                setattr(config, 'last_tp_price', fill_data.filled_price)
                self.total_realized_profit += realized_profit
                print(f"[GridData] 累计已实现盈亏: {self.total_realized_profit}")
                
                if self.reset_level(level):
                    print(f"[GridData] 层级 {level} 重置成功")
                    self.data_updated.emit(self.uid)
                    print(f"[GridData] 数据更新信号已发送")
                else:
                    print(f"[GridData] 错误: 层级 {level} 重置失败")
                    
            except Exception as e:
                print(f"[GridData] 处理止盈错误: {e}")
                print(f"[GridData] 错误详情: {traceback.format_exc()}")

    def add_realized_profit(self, profit: Decimal):
        """添加已实现盈利"""
        self.total_realized_profit += profit
        grid_logger.info(f"[GridData] 更新累计已实现盈利: {self.total_realized_profit}")
        self.data_updated.emit(self.uid)
        
        position_metrics = self.calculate_position_metrics()
        unrealized_pnl = position_metrics['unrealized_pnl']
        if self._check_take_profit_condition(unrealized_pnl):
            grid_logger.info(f"[GridData] 达到总体止盈条件：{self.total_realized_profit} >= {self.take_profit_config.profit_amount}")
            return True
        return False

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

    def get_next_level(self) -> Optional[int]:
        """获取下一个未成交的层级"""
        # with self._lock:
        if not self.grid_levels:  # 未设置网格
            return None
        for level in sorted(self.grid_levels.keys()):
            if not self.grid_levels[level].is_filled:
                return level
        return None  # 已开满仓