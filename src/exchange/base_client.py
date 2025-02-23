# src/exchange/base_client.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set
from enum import Enum
from qtpy.QtCore import QObject, Signal

class InstType(Enum):
    SPOT = "spot"
    FUTURES = "futures"

class TradeScope(Enum):
    """交易角色"""
    TAKER = "taker"
    MAKER = "maker"

class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"

class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"

class TradeSide(Enum):
    OPEN = "open"
    CLOSE = "close"

class PositionSide(Enum):
    LONG = "long"
    SHORT = "short"

class OrderSourceType(Enum):
    """订单来源类型"""
    WEB = "web"           # Web端创建
    API = "api"           # API端创建
    SYS = "sys"           # 系统托管订单
    IOS = "ios"           # iOS端创建
    ANDROID = "android"   # Android端创建

@dataclass
class TickerData:
    """Ticker频道的行情数据"""
    instId: str                  # 产品ID
    lastPr: Decimal              # 最新成交价格 
    open24h: Decimal = Decimal(0)    # 24小时开盘价
    high24h: Decimal = Decimal(0)    # 24小时最高价格
    low24h: Decimal = Decimal(0)     # 24小时最低价格
    change24h: Decimal = Decimal(0)  # 24小时价格变动
    bidPr: Decimal = Decimal(0)      # 买一价
    askPr: Decimal = Decimal(0)      # 卖一价  
    bidSz: Decimal = Decimal(0)      # 买一量
    askSz: Decimal = Decimal(0)      # 卖一量
    baseVolume: Decimal = Decimal(0) # 基础币种成交量,以张为单位
    quoteVolume: Decimal = Decimal(0)  # 计价币种成交量
    openUtc: Decimal = Decimal(0)    # UTC 0 时开盘价格
    changeUtc24h: Decimal = Decimal(0)  # 伦敦时间开盘价格
    ts: int = 0                  # 数据生成时间,单位:毫秒

@dataclass
class SymbolConfig:
    """通用交易对参数配置"""
    symbol: str                    # 交易对名称，如 "BTCUSDT"
    pair: str                      # 交易对表示，如 "BTC/USDT"
    base_coin: str                 # 基础货币，如 "BTC"
    quote_coin: str                # 计价货币，如 "USDT"
    base_precision: int            # 基础货币数量小数位
    quote_precision: int           # 计价货币数量小数位
    price_precision: int           # 价格小数位
    min_base_amount: Decimal       # 最小基础货币开单数量
    min_quote_amount: Decimal      # 最小计价货币开单数量
    max_leverage: Optional[int] = None  # 最大杠杆倍数（合约适用）
    inst_type: Optional[InstType] = None  # 产品类型（现货/合约）
    status: Optional[str] = None        # 交易对状态
    extra_params: dict = field(default_factory=dict)  # 其他特定参数

@dataclass
class TickerResponse:
    """Ticker频道推送数据的包装类"""
    action: str               # 消息类型,如"snapshot"
    arg: dict                 # 请求参数
    data: List[TickerData]    # ticker数据列表
    ts: int = 0               # 推送时间戳

@dataclass
class UserAuthority:
    """用户权限数据"""
    user_id: str
    inviter_id: str
    authorities: Set[str]
    parent_id: int
    trader_type: str
    channel_code: str
    channel: str
    regis_time: int
    ips: Optional[str] = None

@dataclass
class AssetBalance:
    """资产余额数据"""
    coin: str
    available: Decimal
    frozen: Decimal
    locked: Decimal
    limit_available: Decimal
    update_time: int

@dataclass 
class Position:
    """持仓数据结构"""
    symbol: str                    # 交易对
    position_side: PositionSide    # 持仓方向
    amount: Decimal               # 持仓数量
    entry_price: Decimal          # 开仓均价
    mark_price: Decimal           # 标记价格
    unrealized_pnl: Decimal       # 未实现盈亏
    margin: Optional[Decimal]     # 保证金
    leverage: Optional[int]       # 杠杆倍数

@dataclass
class OrderResponse:
    """通用订单响应"""
    status: str  # 请求状态，如 "success" 或 "failed"
    success: bool  # 是否成功请求
    function_name: Optional[str] = None  # 新增字段：调用该响应的函数名
    error_message: Optional[str] = None  # 错误信息
    code: Optional[str] = None  # 错误代码（如 Bitget 的 "00000" 表示成功）
    msg: Optional[str] = None  # 错误消息（兼容不同交易所的字段名）
    order_id: Optional[str] = None  # 订单ID
    client_order_id: Optional[str] = None  # 客户端订单ID
    create_time: Optional[int] = None  # 创建时间戳
    request_time: Optional[int] = None  # 请求发送时间戳
    response_time: Optional[int] = None  # 响应接收时间戳
    api_endpoint: Optional[str] = None  # 请求的接口
    data: Optional[Dict[str, Any]] = None  # 额外数据（如成交明细）

@dataclass
class OrderRequest:
    """通用下单请求参数"""
    symbol: str  # 交易对，如 "BTCUSDT"
    inst_type: InstType = None
    pair: Optional[str] = None  # 交易对的另一种表示，如 "BTC/USDT"
    base_coin: Optional[str] = None  # 基础货币，如 "BTC"
    quote_coin: Optional[str] = None  # 报价货币，如 "USDT"
    side: OrderSide = None  # 买卖方向 (buy/sell)
    trade_side: Optional[TradeSide] = None  # 交易方向（open/close）
    position_side: PositionSide = PositionSide.LONG  # 持仓方向（long/short）
    order_type: OrderType = OrderType.MARKET  # 订单类型
    base_size: Optional[Decimal] = None  # 基础货币数量（如 BTC 数量）
    quote_size: Optional[Decimal] = None  # 报价货币数量（如 USDT 数量）
    price: Optional[Decimal] = None  # 下单价格（限价单必填，可用于计算仓位）
    client_order_id: Optional[str] = None  # 客户端自定义订单ID
    time_in_force: Optional[str] = None  # 订单有效期（如 "gtc", "ioc"）
    reduce_only: Optional[bool] = False  # 是否只减仓
    leverage: Optional[int] = None  # 杠杆倍数（合约）
    margin_mode: Optional[str] = None  # 保证金模式（如 "isolated" 或 "crossed"）
    extra_params: Dict[str, Any] = field(default_factory=dict)  # 交易所特定参数

@dataclass
class FillResponse:
    """成交明细响应"""
    symbol: str  # 交易对（如 "BTCUSDT"）
    trade_time: int  # 成交时间戳
    position_side: PositionSide  # 持仓方向（long/short）
    trade_side: Optional[TradeSide]  # 交易方向（open/close）
    filled_price: Decimal  # 成交价格
    filled_base_amount: Decimal  # 成交基础货币数量
    filled_quote_value: Decimal  # 成交报价货币金额
    trade_id: str = None  # 成交ID
    order_id: str = None  # 订单ID
    client_order_id: Optional[str] = None  # 客户端订单ID
    pair: Optional[str] = None  # 交易对表示（如 "BTC/USDT"）
    base_coin: Optional[str] = None  # 基础货币
    quote_coin: Optional[str] = None  # 报价货币
    order_type: OrderType = OrderType.MARKET  # 订单类型（taker/maker）
    trade_scope: Optional[str] = None  # 成交类型（taker/maker）
    fee: Decimal = None  # 手续费
    fee_currency: str = None  # 手续费币种
    source: Optional[str] = None  # 订单来源
    profit: Optional[Decimal] = None  # 平仓盈亏（合约）
    position_mode: Optional[str] = None  # 持仓模式（单向/双向）
    order_request: Optional[OrderRequest] = None  # 原始下单参数
    additional_info: Optional[Any] = None  # 其他信息


class BaseAPIClient(ABC):
    """REST API客户端基类"""
    
    def __init__(self, api_key: str, api_secret: str, passphrase: str = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase

    @abstractmethod
    def get_info(self) -> Dict:
        """获取账户信息"""
        pass

    @abstractmethod
    def get_symbol_config(self, **kwargs) -> List[SymbolConfig]:
        """获取交易对配置信息"""
        pass

    @abstractmethod
    def place_order(self, **kwargs) -> OrderResponse:
        """统一下单接口"""
        pass

    @abstractmethod
    def get_fills(self, **kwargs) -> List[FillResponse]:
        """获取成交明细"""
        pass

class BaseWSClient(QObject):
    """WebSocket客户端基类"""
    
    # WebSocket事件信号
    message_received = Signal(dict)  # 消息接收信号
    error = Signal(str)             # 错误信号
    
    # 连接状态信号
    connected = Signal()            # 连接成功信号
    disconnected = Signal()         # 断开连接信号
    public_connected = Signal()     # 公共WS连接成功
    public_disconnected = Signal()  # 公共WS断开连接
    private_connected = Signal()    # 私有WS连接成功
    private_disconnected = Signal() # 私有WS断开连接
    
    # 行情数据信号
    tick_received = Signal(str, dict)         # symbol, tick_data
    depth_received = Signal(str, dict)        # symbol, depth_data
    kline_received = Signal(str, str, dict)   # symbol, interval, kline_data
    
    # 交易数据信号
    order_updated = Signal(str, dict)         # order_id, order_data
    position_updated = Signal(str, dict)      # symbol, position_data
    balance_updated = Signal(str, dict)       # asset, balance_data

    def __init__(self, url: str, is_private: bool = False):
        super().__init__()
        self.url = url
        self.is_private = is_private
        self._is_connected = False

    @abstractmethod
    def connect(self) -> bool:
        """建立连接"""
        pass

    @abstractmethod
    def disconnect(self) -> bool:
        """断开连接"""
        pass

    @abstractmethod
    def subscribe(self, **kwargs) -> bool:
        """订阅频道"""
        pass

    @abstractmethod
    def unsubscribe(self, **kwargs) -> bool:
        """取消订阅"""
        pass

    @property
    def is_connected(self) -> bool:
        """连接状态"""
        return self._is_connected

class BaseClient(QObject):
    """交易所客户端基类"""

    # 状态信号
    error_occurred = Signal(str)             # error_message
    connection_status = Signal(bool)         # is_connected
    
    # WebSocket状态信号 
    public_connected = Signal()              # 公共WS连接成功
    public_disconnected = Signal()           # 公共WS断开
    private_connected = Signal()             # 私有WS连接成功
    private_disconnected = Signal()          # 私有WS断开

    # 数据信号
    tick_received = Signal(str, dict)        # symbol, tick_data
    depth_received = Signal(str, dict)       # symbol, depth_data
    kline_received = Signal(str, str, dict)  # symbol, interval, kline_data
    
    # 交易数据信号
    order_updated = Signal(str, dict)        # order_id, order_data
    position_updated = Signal(str, dict)     # symbol, position_data
    balance_updated = Signal(str, dict)      # asset, balance_data

    def __init__(self, inst_type: InstType):
        super().__init__()
        self._connected = False
        self.inst_type = inst_type
        self.exchange_str: str = None  # 交易所名称
        self.api_client: BaseAPIClient = None
        self.public_ws: BaseWSClient = None
        self.private_ws: BaseWSClient = None

    def _handle_error(self, error_type: str, error_message: str):
        """统一错误处理"""
        self.error_occurred.emit(f"{error_type}: {error_message}")

    @abstractmethod
    def connect(self) -> bool:
        """建立连接"""
        pass

    @abstractmethod  
    def disconnect(self) -> bool:
        """断开连接"""
        pass

    @property
    def is_connected(self) -> bool:
        """连接状态"""
        return self._connected

    def get_ws_status(self) -> Dict[str, bool]:
        """获取WebSocket连接状态"""
        return {
            "public": self.public_ws is not None and self.public_ws.is_connected,
            "private": self.private_ws is not None and self.private_ws.is_connected
        }
