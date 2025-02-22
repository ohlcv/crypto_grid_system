# src/exchange/base/base_client.py

from abc import abstractmethod
from typing import Dict, List, Optional, Union
from decimal import Decimal
from dataclasses import dataclass, field
from enum import Enum
from qtpy.QtCore import QObject, Signal

# 保持现有枚举定义不变
class InstType(Enum):
    """交易所类型"""
    SPOT = "spot"
    FUTURES = "futures"

class OrderType(Enum):
    """订单类型"""
    MARKET = "market"
    LIMIT = "limit"

class OrderSide(Enum):
    """订单方向"""
    BUY = "buy"
    SELL = "sell"

class TradeSide(Enum):
    """交易方向"""
    OPEN = "open"
    CLOSE = "close"

class PositionSide(Enum):
    """持仓方向"""
    LONG = "long"   # 多头
    SHORT = "short" # 空头

@dataclass
class WSRequest:
    """WebSocket请求数据结构"""
    channel: str            # 频道名称
    pair: str               # 交易对
    inst_type: str          # 产品类型: SPOT/USDT-FUTURES
    other_params: Dict = field(default_factory=dict)  # 其他参数

@dataclass
class OrderRequest:
    """统一的订单请求格式"""
    symbol: str                    # 交易对
    inst_type: InstType            # 新增：交易所类型（现货或合约）
    position_side: PositionSide    # 持仓方向（必填，但可由交易所客户端根据 inst_type 处理）
    side: OrderSide                # 买卖方向
    trade_side: TradeSide          # 开平方向
    order_type: OrderType          # 订单类型
    volume: Decimal                # 数量（base amount 或 quote amount，视情况而定）
    price: Optional[Decimal] = None  # 价格（限价单使用）
    client_order_id: Optional[str] = None  # 客户端订单ID
    quote_amount: Optional[Decimal] = None  # USDT 数量（现货市价买单使用）
    base_price: Optional[Decimal] = None    # 基础货币价格（用于计算 size）
    
    # 合约专用字段
    product_type: Optional[str] = None     # 产品类型
    margin_mode: Optional[str] = None      # 保证金模式
    margin_coin: Optional[str] = None      # 保证金币种

# OrderResponse 和其他类保持不变
@dataclass
class OrderResponse:
    """订单响应"""
    status: str                    # success/failed
    error_message: Optional[str]   # 错误信息
    order_id: str                  # 订单ID
    side: OrderSide               # 买卖方向
    trade_side: TradeSide         # 交易方向（开仓/平仓）
    filled_amount: Decimal = Decimal('0')  # 成交数量
    filled_price: Decimal = Decimal('0')   # 成交均价
    filled_value: Decimal = Decimal('0')   # 成交金额
    fee: Decimal = Decimal('0')            # 手续费
    open_time: Optional[int] = None        # 开仓时间戳
    profit: Optional[Decimal] = None       # 平仓盈亏
    open_price: Optional[Decimal] = None   # 开仓价格
    close_time: Optional[int] = None       # 平仓时间戳

@dataclass
class FillResponse:
    """成交明细响应"""
    trade_id: str                 # 成交ID
    order_id: str                 # 订单ID
    symbol: str                   # 交易对
    side: OrderSide              # 买卖方向
    trade_side: TradeSide        # 开平方向
    filled_time: int             # 成交时间戳
    filled_amount: Decimal       # 成交数量
    filled_price: Decimal        # 成交价格
    filled_value: Decimal        # 成交金额
    fee: Decimal                 # 手续费
    fee_currency: str            # 手续费币种
    profit: Optional[Decimal] = None       # 平仓盈亏
    position_side: Optional[str] = None    # 持仓方向
    client_order_id: Optional[str] = None  # 客户端订单ID
    error_message: Optional[str] = None    # 错误信息

class BaseClient(QObject):
    """交易所客户端基类"""
    # 行情数据信号
    tick_received = Signal(str, dict)         # symbol, tick_data
    depth_received = Signal(str, dict)        # symbol, depth_data
    kline_received = Signal(str, str, dict)   # symbol, interval, kline_data
    # 交易数据信号
    order_updated = Signal(str, dict)         # order_id, order_data
    # 状态信号
    connected = Signal()                      # 连接成功
    disconnected = Signal()                   # 连接断开
    connection_status = Signal(bool)          # is_connected
    error_occurred = Signal(str)              # error_type, error_message
    ws_status_changed = Signal(bool, bool)          # 添加WS状态变化信号

    def __init__(self, inst_type: InstType):
        super().__init__()
        self.inst_type = inst_type
        self._connected = False
        self._subscribed_symbols = set()
        self.exchange: str = None  # 交易所名称
        self.instance_id = None  # 实例标识符

    def connect(self) -> bool:
        """建立连接"""
        raise NotImplementedError

    def disconnect(self) -> bool:
        """断开连接"""
        raise NotImplementedError

    @property
    def is_connected(self) -> bool:
        """连接状态"""
        try:
            ws_status = self.get_ws_status()
            connected = ws_status.get("public", False) and ws_status.get("private", False)
            return connected
        except Exception as e:
            # print(f"[BaseClient] 检查连接状态出错: {e}")
            return False

    def get_ws_status(self) -> Dict[str, bool]:
        """获取WebSocket状态"""
        raise NotImplementedError

    def validate_pair(self, pair: str) -> dict:
        """
        验证交易对是否有效并返回其参数
        
        Args:
            pair: 交易对名称 (例如: "BTC/USDT")
            
        Returns:
            dict: {
                "valid": bool,              # 是否有效
                "normalized_pair": str,      # 标准化后的交易对名称
                "quantity_precision": int,   # 数量精度
                "price_precision": int,      # 价格精度
                "min_quantity": str,         # 最小数量
                "min_amount": str,          # 最小金额
                "error": str                # 错误信息(如果有)
            }
        """
        raise NotImplementedError

    def subscribe_pair(self, symbol: str, channels: List[str]) -> bool:
        """
        订阅交易对的指定数据类型
        
        Args:
            symbol: 交易对
            channels: 数据类型列表，如 ["ticker", "depth", "kline"]
        """
        raise NotImplementedError

    def unsubscribe_pair(self, symbol: str, channels: List[str]) -> bool:
        """取消订阅"""
        raise NotImplementedError

    @abstractmethod
    def place_order(self, request: OrderRequest) -> OrderResponse:
        """统一下单接口"""
        pass

    @abstractmethod
    def get_fills(self, symbol: str, order_id: str) -> List[OrderResponse]:
        """获取成交明细"""
        pass

    @abstractmethod
    def all_close_positions(self, symbol: str, side: Optional[str] = None) -> List[OrderResponse]:
        """一键平仓"""
        pass

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        """撤单"""
        raise NotImplementedError

    def query_order(self, order_id: str, symbol: str) -> Optional[OrderResponse]:
        """查询订单"""
        raise NotImplementedError

    def get_position(self, symbol: str) -> Dict:
        """查询持仓"""
        raise NotImplementedError

    def get_account(self) -> Dict:
        """查询账户"""
        raise NotImplementedError

    def _handle_error(self, error_type: str, error_message: str):
        """错误处理"""
        self.error_occurred.emit(error_message)

    def _handle_connect(self):
        """处理连接成功"""
        try:
            old_status = self._connected
            ws_status = self.get_ws_status()
            new_status = ws_status.get("public", False) and ws_status.get("private", False)
            
            if old_status != new_status:
                self._connected = new_status
                if new_status:
                    self.connected.emit()
                    # 重新订阅所有交易对
                    for symbol in self._subscribed_symbols:
                        self.subscribe_pair(symbol, ["ticker"])
                else:
                    self.disconnected.emit()
                self.connection_status.emit(new_status)
        except Exception as e:
            print(f"[BaseClient] 处理连接状态出错: {e}")

    def _handle_disconnect(self):
        """处理断开连接"""
        print(f"[BaseClient] 处理断开连接")
        old_status = self._connected
        self._connected = False
        if old_status != self._connected:
            print(f"[BaseClient] 发送连接状态变化信号: {self._connected}")
            self.connection_status.emit(False)
            self.disconnected.emit()

    def _validate_symbol(self, symbol: str) -> bool:
        """验证交易对格式"""
        try:
            base, quote = symbol.split('/')
            return bool(base and quote)
        except ValueError:
            return False