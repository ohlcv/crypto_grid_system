from decimal import ROUND_HALF_DOWN, ROUND_HALF_UP, Decimal
import threading
import time
import traceback
from typing import Dict, Optional, List
from qtpy.QtCore import Signal

from src.exchange.base_client import (
    BaseClient, FillResponse, InstType, OrderRequest, OrderResponse, PositionSide, WSRequest,
    OrderType, OrderSide, TradeSide
)

from src.exchange.bitget.bg_v2_api import BitgetMixAPI, BitgetSpotAPI
from src.exchange.bitget.ws.bgws_client import BGWebSocketClient
from src.utils.logger.log_helper import ws_logger, api_logger
from src.utils.error.error_handler import error_handler

class BitgetClient(BaseClient):
    """Bitget交易所客户端实现"""
    
    def __init__(self, api_key: str, api_secret: str, passphrase: str, inst_type: InstType):
        super().__init__(inst_type)
        self.logger = ws_logger
        self.api_logger = api_logger
        
        self.logger.info(f"开始初始化 {inst_type.value} 客户端")
        
        # API认证信息
        self._api_key = api_key
        self._api_secret = api_secret
        self._passphrase = passphrase
        self.exchange = "bitget"
        
        # REST API客户端
        if inst_type == InstType.SPOT:
            self.rest_api = BitgetSpotAPI(api_key, api_secret, passphrase)
        else:
            self.rest_api = BitgetMixAPI(api_key, api_secret, passphrase)

        # WebSocket客户端
        self._public_ws = None
        self._private_ws = None
        self._init_websockets()
        
        self.logger.info(f"{inst_type.name} 客户端初始化完成")

    def _init_websockets(self):
        """初始化WebSocket连接"""
        try:
            self._public_ws = BGWebSocketClient(is_private=False)
            self._private_ws = BGWebSocketClient(
                is_private=True,
                api_key=self._api_key,
                api_secret=self._api_secret,
                passphrase=self._passphrase
            )
            self._connect_signals()
            
        except Exception as e:
            self.logger.error(f"WebSocket初始化失败: {e}")
            raise

    def _connect_signals(self):
        """连接WebSocket信号"""
        # 公共WS信号
        self._public_ws.message_received.connect(self._handle_public_message)
        self._public_ws.error.connect(lambda e: self._handle_error("ws_public", e))
        self._public_ws.connected.connect(self._handle_public_connected)
        self._public_ws.disconnected.connect(self._handle_public_disconnected)

        # 私有WS信号 
        self._private_ws.message_received.connect(self._handle_private_message)
        self._private_ws.error.connect(lambda e: self._handle_error("ws_private", e))
        self._private_ws.connected.connect(self._handle_private_connected)
        self._private_ws.disconnected.connect(self._handle_private_disconnected)

    def connect(self, wait: bool = True) -> bool:
        """建立连接"""
        try:
            self.logger.info(f"{self.inst_type.name} 开始连接")
            
            def start_connections():
                self._public_ws.connect()
                self._private_ws.connect()
                
            if not wait:
                threading.Thread(
                    target=start_connections,
                    name=f"WebSocket-{self.inst_type.name}-Connect-{id(self)}",
                    daemon=True
                ).start()
                return True
                
            start_connections()
            return True
            
        except Exception as e:
            self.logger.error("连接失败", exc_info=e)
            self._handle_error("connection", str(e))
            return False

    def disconnect(self) -> bool:
        """断开连接"""
        try:
            if self._private_ws:
                self._private_ws.disconnect()
                
            if self._public_ws:
                self._public_ws.disconnect()
                
            self._connected = False
            self.logger.info(f"{self.inst_type.name} 连接已断开")
            return True
            
        except Exception as e:
            self.logger.error(f"断开连接失败: {e}")
            return False

    def _handle_public_connected(self):
            """处理公共WS连接成功"""
            self.logger.info("公共WebSocket连接成功")
            self.ws_status_changed.emit(True, True)
            self._check_connection_status()

    def _handle_public_disconnected(self):
        """处理公共WS断开连接"""
        self.logger.info("公共WebSocket断开连接")
        self.ws_status_changed.emit(True, False) 
        self._check_connection_status()

    def _handle_private_connected(self):
        """处理私有WS连接成功"""
        self.logger.info("私有WebSocket连接成功")
        self._check_connection_status()

    def _handle_private_disconnected(self):
        """处理私有WS断开连接"""
        self.logger.info("私有WebSocket断开连接")
        self.ws_status_changed.emit(False, False)
        self._check_connection_status()

    def _handle_login_success(self):
        """处理登录成功事件"""
        self.logger.info("私有WebSocket登录成功")
        self._private_ws._login_status = True
        self.ws_status_changed.emit(False, True)
        self._check_connection_status()

    def _check_connection_status(self):
        """检查连接状态"""
        try:
            ws_status = self.get_ws_status()
            current_status = ws_status["public"] and ws_status["private"]
            
            if self._connected != current_status:
                self._connected = current_status
                self.logger.info(f"{self.inst_type.name} 连接状态更新: {current_status}")
                
                if current_status:
                    self.connected.emit()
                else:
                    self.disconnected.emit()
                self.connection_status.emit(current_status)
                
        except Exception as e:
            self.logger.error(f"检查连接状态失败: {e}")

    def _handle_public_message(self, message: dict):
        """处理公共WebSocket消息"""
        try:
            if message.get("type") == "event":
                return
                
            channel = message.get("channel")
            if channel == "ticker":
                pair = message.get("symbol")
                data = message.get("data")
                if pair and data:
                    self.tick_received.emit(pair, data)
                    
        except Exception as e:
            self.logger.error(f"处理公共消息错误: {e}")

    def _handle_private_message(self, message: dict):
        """处理私有WebSocket消息"""
        try:
            # 处理登录响应
            if message.get("event") == "login" and message.get("code") == 0:
                self._handle_login_success()
                return

            # 处理订单消息
            if message.get("channel") == "orders":
                order_data = message.get("data")
                if order_data:
                    self.order_updated.emit(
                        order_data.get("clientOid", ""),
                        order_data
                    )
        except Exception as e:
            self.logger.error(f"处理私有消息错误: {e}")

    def get_ws_status(self) -> Dict[str, bool]:
        """获取WebSocket状态"""
        return {
            "public": (self._public_ws and self._public_ws.is_connected),
            "private": (self._private_ws and self._private_ws.is_connected 
                      and getattr(self._private_ws, '_login_status', False))
        }

    def _format_symbol(self, symbol: str) -> str:
        """格式化交易对名称"""
        return symbol.replace("/", "")

    def _get_inst_type_str(self) -> str:
        """获取产品类型字符串"""
        return "SPOT" if self.inst_type == InstType.SPOT else "USDT-FUTURES"

    def get_fills(self, symbol: str, order_id: str) -> List[OrderResponse]:
        """获取成交记录"""
        time.sleep(0.5)
        try:
            symbol = self._format_symbol(symbol)
            fills = self.rest_api.get_fills(symbol=symbol, order_id=order_id)
            
            result = []
            if fills.get('code') == '00000':
                # 根据 inst_type 区分现货和合约返回格式
                fill_list = fills.get('data', []) if self.inst_type == InstType.SPOT else fills.get('data', {}).get('fillList', [])
                
                for fill in fill_list:
                    # 通用字段
                    order_id = fill.get('orderId', '')
                    side = OrderSide(fill.get('side', '').lower())  # 统一转为小写，确保兼容
                    
                    # 处理 trade_side（现货无此字段，需从上下文推导）
                    trade_side_str = fill.get('tradeSide', None)
                    trade_side = TradeSide(trade_side_str.lower()) if trade_side_str else None
                    
                    # 处理成交金额和数量字段（现货和合约字段名不同）
                    if self.inst_type == InstType.SPOT:
                        filled_amount = Decimal(str(fill.get('size', '0')))  # 现货使用 size
                        filled_price = Decimal(str(fill.get('priceAvg', '0')))  # 现货使用 priceAvg
                        filled_value = Decimal(str(fill.get('amount', '0')))  # 现货使用 amount
                    else:
                        filled_amount = Decimal(str(fill.get('baseVolume', '0')))  # 合约使用 baseVolume
                        filled_price = Decimal(str(fill.get('price', '0')))  # 合约使用 price
                        filled_value = Decimal(str(fill.get('quoteVolume', '0')))  # 合约使用 quoteVolume
                    
                    # 处理手续费
                    fee = Decimal('0')
                    fee_detail = fill.get('feeDetail')
                    if isinstance(fee_detail, dict):
                        fee = Decimal(str(fee_detail.get('totalFee', '0')))
                    elif isinstance(fee_detail, list) and fee_detail:
                        fee = Decimal(str(fee_detail[0].get('totalFee', '0')))
                    
                    # 构建 OrderResponse
                    resp = OrderResponse(
                        status='success',
                        error_message=None,
                        order_id=order_id,
                        side=side,
                        trade_side=trade_side,
                        filled_amount=filled_amount,
                        filled_price=filled_price,
                        filled_value=filled_value,
                        fee=fee,
                        open_time=int(fill.get('cTime', 0)) if trade_side == TradeSide.OPEN else None,
                        close_time=int(fill.get('cTime', 0)) if trade_side == TradeSide.CLOSE else None,
                        profit=Decimal(str(fill.get('profit', '0'))) if 'profit' in fill else None
                    )
                    result.append(resp)
                
                return result
            
            self.logger.warning(f"获取成交记录失败: {fills.get('msg', 'Unknown error')}")
            return []

        except Exception as e:
            self.logger.error("获取成交记录失败", exc_info=e)
            return []

    def place_order(self, request: OrderRequest) -> OrderResponse:
        try:
            self.logger.info(f"下单请求: {request}")
            
            params = {
                "symbol": self._format_symbol(request.symbol),
                "orderType": request.order_type.value,
            }
            
            # 用于返回的 order_side，初始化为 request.side
            order_side = request.side
            
            if request.inst_type == InstType.FUTURES:
                # 合约订单
                if request.volume is not None:
                    size = request.volume
                elif request.quote_amount and request.base_price:
                    size = request.quote_amount / request.base_price
                else:
                    raise ValueError("合约订单必须提供 volume 或 quote_amount 和 base_price")
                    
                if not request.position_side:
                    raise ValueError("合约订单必须提供 position_side")
                    
                # 根据 Bitget 规则，OrderSide 仅依赖 PositionSide
                if request.position_side == PositionSide.LONG:
                    order_side = OrderSide.BUY  # long 对应 buy
                else:  # PositionSide.SHORT
                    order_side = OrderSide.SELL  # short 对应 sell
                
                params.update({
                    "size": str(size),
                    "side": order_side.value,
                    "tradeSide": request.trade_side.value,
                    "productType": request.product_type or "USDT-FUTURES",
                    "marginMode": request.margin_mode or "crossed",
                    "marginCoin": request.margin_coin or "USDT",
                })
            else:
                # 现货订单
                if request.order_type == OrderType.MARKET:
                    if request.side == OrderSide.BUY:
                        if request.quote_amount is not None:
                            size = request.quote_amount
                        elif request.volume and request.base_price:
                            size = request.volume * request.base_price
                        else:
                            raise ValueError("现货市价买单必须提供 quote_amount 或 volume 和 base_price")
                    else:  # OrderSide.SELL
                        if request.volume is not None:
                            size = request.volume
                        elif request.quote_amount and request.base_price:
                            size = request.quote_amount / request.base_price
                        else:
                            raise ValueError("现货市价卖单必须提供 volume 或 quote_amount 和 base_price")
                else:  # OrderType.LIMIT
                    if request.volume is not None:
                        size = request.volume
                    elif request.quote_amount and request.base_price:
                        size = request.quote_amount / request.base_price
                    else:
                        raise ValueError("现货限价单必须提供 volume 或 quote_amount 和 base_price")
                        
                params.update({
                    "size": str(size),
                    "side": request.side.value,
                })
            
            if request.order_type == OrderType.LIMIT:
                if request.price is None:
                    raise ValueError("限价单必须提供 price")
                params["price"] = str(request.price)
            
            if request.client_order_id:
                params["clientOid"] = request.client_order_id
            
            # 调用下单 API
            response = self.rest_api.place_order(**params)
            if response.get('code') != '00000':
                return OrderResponse(
                    status='failed',
                    error_message=response.get('msg', 'Unknown error'),
                    order_id='',
                    side=order_side,
                    trade_side=request.trade_side,
                    filled_amount=Decimal('0'),
                    filled_price=Decimal('0'),
                    filled_value=Decimal('0'),
                    fee=Decimal('0')
                )

            order_id = response['data']['orderId']
            if request.order_type == OrderType.MARKET:
                fills = self.get_fills(request.symbol, order_id)
                if fills and fills[0].status == 'success':
                    fill = fills[0]
                    if fill.trade_side is None:
                        fill.trade_side = request.trade_side
                    return OrderResponse(
                        status='success',
                        error_message=None,
                        order_id=order_id,
                        side=order_side,  # 使用根据 PositionSide 确定的 order_side
                        trade_side=fill.trade_side,
                        filled_amount=fill.filled_amount,
                        filled_price=fill.filled_price,
                        filled_value=fill.filled_value,
                        fee=fill.fee,
                        open_time=fill.open_time if fill.trade_side == TradeSide.OPEN else None,
                        close_time=fill.close_time if fill.trade_side == TradeSide.CLOSE else None,
                        profit=fill.profit if fill.trade_side == TradeSide.CLOSE else None
                    )
                else:
                    self.logger.warning(f"未获取到订单 {order_id} 的成交详情，可能是延迟或失败")
            
            return OrderResponse(
                status='success',
                error_message=None,
                order_id=order_id,
                side=order_side,  # 使用根据 PositionSide 确定的 order_side
                trade_side=request.trade_side,
                filled_amount=Decimal('0'),
                filled_price=Decimal('0'),
                filled_value=Decimal('0'),
                fee=Decimal('0'),
                open_time=int(response['data'].get('cTime', 0)) if request.trade_side == TradeSide.OPEN else None
            )
        
        except Exception as e:
            self.logger.error(f"下单失败 - 请求: {request}", exc_info=e)
            return OrderResponse(
                status='failed',
                error_message=str(e),
                order_id='',
                side=order_side,
                trade_side=request.trade_side,
                filled_amount=Decimal('0'),
                filled_price=Decimal('0'),
                filled_value=Decimal('0'),
                fee=Decimal('0')
            )

    def all_close_positions(self, symbol: str, side: Optional[str] = None) -> List[OrderResponse]:
        """
        一键平仓方法
        Args:
            symbol: 交易对 (如 "TRUMP/USDT")
            side: 持仓方向 (仅合约使用，可选值为 "long" 或 "short")
        Returns:
            List[OrderResponse]: 平仓订单响应列表
        """
        try:
            symbol = self._format_symbol(symbol)
            result = []

            if self.inst_type == InstType.FUTURES:
                # 合约一键平仓
                self.logger.info(f"合约一键平仓: {symbol}, 方向: {side}")
                if side not in ['long', 'short']:
                    raise ValueError("合约平仓必须指定 side 为 'long' 或 'short'")
                
                # 调用 Bitget 的平仓 API
                response = self.rest_api.all_close_positions(
                    symbol=symbol,
                    hold_side=side
                )
                if response.get('code') == '00000':
                    success_list = response.get('data', {}).get('successList', [])
                    for order in success_list:
                        # 根据 Bitget 规则，平仓的 OrderSide 与持仓方向一致
                        order_side = OrderSide.BUY if side == 'long' else OrderSide.SELL
                        result.append(OrderResponse(
                            status='success',
                            error_message=None,
                            order_id=order['orderId'],
                            side=order_side,  # 平多用 BUY，平空用 SELL
                            trade_side=TradeSide.CLOSE,
                            filled_amount=Decimal(str(order.get('fillSize', '0'))),
                            filled_price=Decimal(str(order.get('fillPrice', '0'))),
                            filled_value=Decimal(str(order.get('quoteSize', '0'))),
                            fee=Decimal(str(order.get('fee', '0'))),
                            close_time=int(order.get('cTime', 0)),
                            profit=Decimal(str(order.get('profit', '0'))) if 'profit' in order else None
                        ))
                    self.logger.info(f"合约平仓成功，订单数: {len(result)}")
                else:
                    raise ValueError(f"合约一键平仓失败: {response.get('msg')}")

            else:
                # 现货一键平仓
                self.logger.info(f"现货一键平仓: {symbol}")
                assets_response = self.rest_api.get_account_assets(
                    coin=symbol.split('USDT')[0]
                )
                if assets_response.get('code') != '00000':
                    raise ValueError(f"获取账户资产失败: {assets_response.get('msg')}")

                pair_info = self.rest_api.get_pairs(symbol=symbol)
                if pair_info.get('code') != '00000':
                    raise ValueError(f"获取交易对信息失败: {pair_info.get('msg')}")
                quantity_precision = int(pair_info['data'][0].get('quantityPrecision', 2))

                assets = assets_response.get('data', [])
                for asset in assets:
                    if asset['coin'].upper() == symbol.split('USDT')[0]:
                        available = Decimal(str(asset['available']))
                        if available <= 0:
                            self.logger.info("无可平仓数量")
                            return result

                        order_amount = (available * Decimal('0.99')).quantize(
                            Decimal('0.' + '0' * quantity_precision),
                            rounding=ROUND_HALF_DOWN
                        )
                        if order_amount <= 0:
                            self.logger.info("调整后数量为0，无需平仓")
                            return result

                        close_request = OrderRequest(
                            symbol=symbol,
                            inst_type=InstType.SPOT,
                            position_side=PositionSide.LONG,  # 现货默认 LONG，仅占位符
                            side=OrderSide.SELL,  # 现货平仓始终用 SELL
                            trade_side=TradeSide.CLOSE,
                            order_type=OrderType.MARKET,
                            volume=order_amount,
                            price=None,
                            client_order_id=f"close_all_{int(time.time()*1000)}",
                            quote_amount=None,
                            base_price=None,
                            product_type=None,
                            margin_mode=None,
                            margin_coin=None
                        )

                        self.logger.info(f"现货平仓下单: {close_request}")
                        response = self.place_order(close_request)
                        if response.status != 'success':
                            raise ValueError(f"现货平仓下单失败: {response.error_message}")

                        order_id = response.order_id
                        fills = self.get_fills(symbol, order_id)
                        if fills and fills[0].status == 'success':
                            fill = fills[0]
                            if fill.trade_side is None:
                                fill.trade_side = TradeSide.CLOSE
                            result.append(OrderResponse(
                                status='success',
                                error_message=None,
                                order_id=order_id,
                                side=OrderSide.SELL,  # 现货平仓用 SELL
                                trade_side=fill.trade_side,
                                filled_amount=fill.filled_amount,
                                filled_price=fill.filled_price,
                                filled_value=fill.filled_value,
                                fee=fill.fee,
                                close_time=fill.close_time
                            ))
                            self.logger.info(f"现货平仓成功，成交详情: {result[0]}")
                        else:
                            self.logger.warning(f"未获取到订单 {order_id} 的成交详情，可能是延迟")
                            result.append(response)

                        return result

                self.logger.info(f"未找到 {symbol.split('USDT')[0]} 的持仓")
                return result

            return result

        except Exception as e:
            self.logger.error("一键平仓失败", exc_info=e)
            raise

    def subscribe_pair(self, pair: str, channels: List[str], strategy_uid: str) -> bool:
        """订阅交易对行情"""
        try:
            # 格式化参数
            inst_type_str = self._get_inst_type_str()
            symbol = self._format_symbol(pair)
            
            self.logger.info(f"订阅行情 - 交易对:{symbol} 频道:{channels} 策略:{strategy_uid}")
            
            # 发送订阅请求
            for channel in channels:
                request = WSRequest(
                    channel=channel,
                    pair=symbol,
                    inst_type=inst_type_str
                )
                if not self._public_ws.subscribe(request):
                    return False
                    
            return True
            
        except Exception as e:
            self.logger.error(f"订阅失败", exc_info=e)
            return False

    def unsubscribe_pair(self, pair: str, channels: List[str], strategy_uid: str) -> bool:
        """取消订阅交易对行情"""
        try:
            # 格式化参数
            inst_type_str = self._get_inst_type_str()
            symbol = self._format_symbol(pair)
            
            self.logger.info(f"取消订阅 - 交易对:{symbol} 频道:{channels} 策略:{strategy_uid}")
            
            # 发送取消订阅请求
            for channel in channels:
                request = WSRequest(
                    channel=channel,
                    pair=symbol,
                    inst_type=inst_type_str
                )
                if not self._public_ws.unsubscribe(request):
                    return False
                    
            return True
            
        except Exception as e:
            self.logger.error(f"取消订阅失败", exc_info=e)
            return False

    def update_credentials(self, api_key: str, api_secret: str, passphrase: str):
        """更新API凭证"""
        try:
            self.logger.info("更新API凭证")
            
            self._api_key = api_key
            self._api_secret = api_secret
            self._passphrase = passphrase
            
            # 重新创建REST API客户端
            self.rest_api = (BitgetSpotAPI(api_key, api_secret, passphrase) 
                           if self.inst_type == InstType.SPOT 
                           else BitgetMixAPI(api_key, api_secret, passphrase))

            # 重新连接WebSocket
            self.disconnect()
            self.connect()
            
        except Exception as e:
            self.logger.error("更新API凭证失败", exc_info=e)
            raise

    def _handle_error(self, error_type: str, error_message: str):
        """统一错误处理"""
        self.logger.error(f"错误类型:{error_type} 信息:{error_message}")
        self.error_occurred.emit(f"{error_type}: {error_message}")
        
        # WebSocket错误需要检查连接状态
        if error_type in ['ws_public', 'ws_private']:
            self._check_connection_status()