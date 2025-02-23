from dataclasses import dataclass
from decimal import Decimal
import json
from typing import Dict, List, Optional, Any, Set
from datetime import datetime
import time

from src.exchange.base_client import (
    AssetBalance, BaseAPIClient, InstType, OrderRequest, OrderResponse, FillResponse, SymbolConfig,
    UserAuthority, OrderType, OrderSide, TradeSide, PositionSide
)
from src.exchange.bitget.consts import GET
from src.exchange.bitget.exceptions import BitgetAPIException
from src.utils.common.tools import adjust_decimal_places
from src.utils.logger.log_helper import api_logger

from src.exchange.bitget.v2.spot.account_api import AccountApi as SpotAccountApi
from src.exchange.bitget.v2.spot.market_api import MarketApi as SpotMarketApi
from src.exchange.bitget.v2.spot.order_api import OrderApi as SpotOrderApi
from src.exchange.bitget.v2.mix.account_api import AccountApi as MixAccountApi
from src.exchange.bitget.v2.mix.market_api import MarketApi as MixMarketApi
from src.exchange.bitget.v2.mix.order_api import OrderApi as MixOrderApi


class BitgetAPIClient(BaseAPIClient):
    """Bitget REST API客户端"""
    
    def __init__(self, api_key: str, api_secret: str, passphrase: str = None, inst_type: InstType = None):
        super().__init__(api_key, api_secret, passphrase)
        self.inst_type = inst_type
        self.logger = api_logger
        
        # 初始化API客户端
        self.spot_apis = {
            'account': SpotAccountApi(api_key, api_secret, passphrase),
            'market': SpotMarketApi(api_key, api_secret, passphrase),
            'order': SpotOrderApi(api_key, api_secret, passphrase)
        }
        
        self.futures_apis = {
            'account': MixAccountApi(api_key, api_secret, passphrase),
            'market': MixMarketApi(api_key, api_secret, passphrase),
            'order': MixOrderApi(api_key, api_secret, passphrase)
        }

    def _get_inst_type(self, request: OrderRequest = None) -> InstType:
        """获取交易类型"""
        if request and request.inst_type:
            return request.inst_type
        if self.inst_type:
            return self.inst_type
        raise ValueError("inst_type must be provided in OrderRequest or set in client initialization")

    def _get_api(self, inst_type: InstType, api_type: str):
        """获取对应的API实例"""
        apis = self.spot_apis if inst_type == InstType.SPOT else self.futures_apis
        return apis.get(api_type)

    def get_info(self) -> Dict:
        """获取账户信息"""
        try:
            account_api = self._get_api(InstType.SPOT, 'account')
            response = account_api.info({})
                
            if response.get('code') != '00000':
                raise BitgetAPIException(response.get('msg'), response.get('code'))

            data = response.get('data', {})
            # 转换为标准数据结构
            user_info = UserAuthority(
                user_id=data.get('userId', ''),
                inviter_id=data.get('inviterId', ''),
                authorities=set(data.get('authorities', [])),
                parent_id=int(data.get('parentId', 0)),
                trader_type=data.get('traderType', ''),
                channel_code=data.get('channelCode', ''),
                channel=data.get('channel', ''),
                regis_time=int(data.get('regisTime', 0)),
                ips=data.get('ips')
            )
            
            return {
                'code': response.get('code'),
                'msg': response.get('msg'),
                'request_time': response.get('requestTime'),
                'data': user_info
            }
            
        except Exception as e:
            self.logger.error(f"获取账户信息失败: {str(e)}")
            raise

    def get_symbol_config(self, symbol: str = None, inst_type: InstType = None) -> List[SymbolConfig]:
        """获取交易对配置信息
        
        Args:
            symbol: 交易对名称，如 "BTCUSDT"，不填则返回全部
            inst_type: 产品类型（SPOT/FUTURES），不填则使用初始化时的类型
            
        Returns:
            List[SymbolConfig]: 交易对配置列表
        """
        try:
            # 确定产品类型
            inst_type = inst_type or self._get_inst_type()
            market_api = self._get_api(inst_type, 'market')
            
            # 构建请求参数
            params = {}
            if symbol:
                params['symbol'] = symbol.upper()
            
            # 根据产品类型调用对应的API
            if inst_type == InstType.SPOT:
                response = market_api.symbols(params)
                return self._parse_spot_symbols(response)
            else:
                params['productType'] = 'USDT-FUTURES'  # 默认使用USDT专业合约
                response = market_api.contracts(params)
                return self._parse_futures_symbols(response)
                
        except Exception as e:
            self.logger.error(f"获取交易对配置失败: {str(e)}")
            raise

    def _parse_spot_symbols(self, response: Dict) -> List[SymbolConfig]:
        """解析现货交易对信息"""
        if response.get('code') != '00000':
            raise BitgetAPIException(response.get('msg'), response.get('code'))
            
        symbols = []
        for item in response.get('data', []):
            symbol = item['symbol']
            base_coin = item['baseCoin']
            quote_coin = item['quoteCoin']
            
            config = SymbolConfig(
                symbol=symbol,
                pair=f"{base_coin}/{quote_coin}",
                base_coin=base_coin,
                quote_coin=quote_coin,
                base_precision=int(item['quantityPrecision']),
                quote_precision=int(item['quotePrecision']),
                price_precision=int(item['pricePrecision']),
                min_base_amount=Decimal(item['minTradeAmount']),
                min_quote_amount=Decimal(item['minTradeUSDT']),
                inst_type=InstType.SPOT,
                status=item['status'],
                extra_params={
                    'max_trade_amount': Decimal(item['maxTradeAmount']),
                    'taker_fee_rate': Decimal(item['takerFeeRate']),
                    'maker_fee_rate': Decimal(item['makerFeeRate']),
                    'buy_limit_price_ratio': Decimal(item['buyLimitPriceRatio']),
                    'sell_limit_price_ratio': Decimal(item['sellLimitPriceRatio'])
                }
            )
            symbols.append(config)
            
        return symbols

    def _close_futures_positions(self, request: OrderRequest) -> OrderResponse:
        try:
            # 构建请求参数
            params = {
                'productType': 'USDT-FUTURES',
                'symbol': request.pair.replace('/', '').upper(),
            }
            if request.position_side:
                params['holdSide'] = request.position_side.value

            # 发送平仓请求
            order_api = self._get_api(InstType.FUTURES, 'order')
            response = order_api.closePositions(params)
            
            if response.get('code') != '00000':
                raise BitgetAPIException(response.get('msg'), response.get('code'))
            
            # 获取订单ID并查询成交明细
            order_id = response.get('data', {}).get('orderId')
            time.sleep(0.5)  # 等待成交完成
            fill_response = self.get_fills(request, order_id=order_id)
            
            if fill_response and len(fill_response) > 0:
                return OrderResponse(
                    status="success",
                    success=True,
                    order_id=order_id,
                    data=fill_response[0],  # FillResponse
                    code=response.get('code'),
                    api_endpoint="/api/v2/mix/order/close-positions"
                )
            else:
                return OrderResponse(
                    status="success",
                    success=True,
                    order_id=order_id,
                    data=None,  # 无成交明细
                    code=response.get('code'),
                    api_endpoint="/api/v2/mix/order/close-positions"
                )
        except Exception as e:
            self.logger.error(f"合约一键平仓失败: {str(e)}")
            raise

    def place_order(self, request: OrderRequest) -> OrderResponse:
        """统一下单接口"""
        try:
            # 获取交易类型和API
            inst_type = self._get_inst_type(request)
            order_api = self._get_api(inst_type, 'order')
            
            # 构建下单参数
            params = self._build_order_params(request)
            self.logger.debug(f"完整请求参数:\n请求参数: {json.dumps(params, indent=2)}")
            
            # 发送下单请求
            response = order_api.placeOrder(params)
            self.logger.debug(f"API原始响应:\n{json.dumps(response, indent=2)}")
            
            if response.get('code') != '00000':
                return OrderResponse(
                    status="failed",
                    success=False,
                    function_name="place_order",  # 设置函数名
                    error_message=response.get('msg'),
                    code=response.get('code'),
                    api_endpoint=f"/api/v2/{'spot' if inst_type == InstType.SPOT else 'mix'}/trade/place-order"
                )

            # 获取订单信息
            order_data = response.get('data', {})
            order_id = order_data.get('orderId')
            
            # 查询订单详情和成交信息
            time.sleep(0.5)  # 等待一下确保订单处理完成
            fill_response = self.get_fills(request, order_id=order_id)
            if fill_response and len(fill_response) > 0:
                # 直接将 FillResponse 对象赋值给 data
                return OrderResponse(
                    status="success",
                    success=True,
                    function_name="place_order",  # 设置函数名
                    order_id=order_id,
                    client_order_id=order_data.get('clientOid'),
                    create_time=int(response.get('requestTime', time.time() * 1000)),
                    code=response.get('code'),
                    api_endpoint=f"/api/v2/{'spot' if inst_type == InstType.SPOT else 'mix'}/trade/place-order",
                    data=fill_response[0]  # 直接使用 FillResponse 对象
                )
            
            return OrderResponse(
                status="success",
                success=True,
                function_name="place_order",  # 设置函数名
                order_id=order_id,
                client_order_id=order_data.get('clientOid'),
                create_time=int(response.get('requestTime', time.time() * 1000)),
                code=response.get('code'),
                api_endpoint=f"/api/v2/{'spot' if inst_type == InstType.SPOT else 'mix'}/trade/place-order"
            )
                    
        except Exception as e:
            self.logger.error(f"下单失败: {str(e)}")
            return OrderResponse(
                status="failed",
                success=False,
                function_name="place_order",  # 设置函数名
                error_message=str(e)
            )

    def _build_order_params(self, request: OrderRequest) -> Dict:
        """构建下单参数"""
        inst_type = self._get_inst_type(request)
        
        if inst_type == InstType.SPOT:
            # 现货下单参数
            params = {
                'symbol': request.symbol.replace('/', '').upper(),  # BTCUSDT
                'side': request.side.value,  # buy/sell
                'orderType': request.order_type.value,  # limit/market
                'force': request.time_in_force or 'gtc',
                'clientOid': request.client_order_id
            }
            
            # 市价买入基于quote_size,其他基于base_size
            if request.order_type == OrderType.MARKET and request.side == OrderSide.BUY:
                params['size'] = str(request.quote_size)
            else:
                params['size'] = str(request.base_size)
                
            # 限价单需要price
            if request.order_type == OrderType.LIMIT:
                params['price'] = str(request.price)
                
        else:
            # 合约下单参数
            params = {
                'symbol': request.symbol.replace('/', '').upper(),
                'productType': 'USDT-FUTURES',  # 默认USDT专业合约
                'marginMode': request.margin_mode or 'crossed',
                'marginCoin': 'USDT',
                'size': str(request.base_size),
                'side': request.side.value,
                'orderType': request.order_type.value,
                'force': request.time_in_force or 'gtc',
                'clientOid': request.client_order_id
            }
            
            # 双向持仓需要tradeSide
            if request.trade_side:
                params['tradeSide'] = request.trade_side.value
                
            # 限价单需要price
            if request.order_type == OrderType.LIMIT:
                params['price'] = str(request.price)
                
            # 其他可选参数
            if request.reduce_only:
                params['reduceOnly'] = 'YES'
            if request.leverage:
                params['leverage'] = str(request.leverage)
                
        # 移除None值
        return {k: v for k, v in params.items() if v is not None}

    def get_fills(self, request: OrderRequest = None, **kwargs) -> List[FillResponse]:
        """获取成交明细"""
        try:
            inst_type = self._get_inst_type(request)
            order_api = self._get_api(inst_type, 'order')

            # 构建请求参数 
            params = {
                'symbol': request.symbol.replace('/', '').upper() if request else None,
                'orderId': kwargs.get('order_id'),
                'startTime': str(kwargs.get('start_time')) if kwargs.get('start_time') else None,
                'endTime': str(kwargs.get('end_time')) if kwargs.get('end_time') else None,
                'limit': str(kwargs.get('limit', 100))
            }
            # 移除空值
            params = {k: v for k, v in params.items() if v is not None}
            
            # 合约需要productType
            if inst_type == InstType.FUTURES:
                params['productType'] = 'USDT-FUTURES'
                
            self.logger.debug(f"查询成交参数: {params}")
            
            # 发送请求
            response = order_api.fills(params)
            self.logger.debug(f"查询成交响应: {response}")
            
            if response.get('code') != '00000':
                raise BitgetAPIException(response.get('msg'), response.get('code'))
                
            # 解析成交记录
            fills = []
            for fill in response.get('data', []):
                if inst_type == InstType.SPOT:
                    fills.append(self._parse_spot_fill(fill))
                else:
                    fills.append(self._parse_contract_fill(fill))
                    
            return fills
            
        except Exception as e:
            self.logger.error(f"查询成交记录失败: {str(e)}")
            raise

    def _parse_spot_fill(self, fill: Dict) -> FillResponse:
        """解析现货成交记录"""
        symbol = fill['symbol']
        base_coin = symbol[:-4] if symbol.endswith('USDT') else symbol[:-3]
        quote_coin = symbol[-4:] if symbol.endswith('USDT') else symbol[-3:]
        
        # 根据 side 推断 trade_side（可选）
        side = fill.get('side')
        trade_side = TradeSide.OPEN if side == 'buy' else TradeSide.CLOSE if side == 'sell' else None
        
        return FillResponse(
            trade_id=fill['tradeId'],
            order_id=fill['orderId'],
            symbol=symbol,
            pair=f"{base_coin}/{quote_coin}",
            base_coin=base_coin,
            quote_coin=quote_coin,
            trade_side=trade_side,  # 添加 trade_side 参数
            position_side=PositionSide.LONG,  # 现货通常为做多
            trade_time=int(fill['cTime']),
            trade_scope=fill['tradeScope'],  # taker/maker
            filled_price=Decimal(fill['priceAvg']),
            filled_base_amount=Decimal(fill['size']),
            filled_quote_value=Decimal(fill['amount']),
            fee=Decimal(fill['feeDetail']['totalFee']),
            fee_currency=fill['feeDetail']['feeCoin'],
            source=fill.get('enterPointSource', 'API')
        )
        
    def _parse_contract_fill(self, fill: Dict) -> FillResponse:
        """解析合约成交记录"""
        symbol = fill['symbol'].upper()
        base_coin = symbol[:-4] if symbol.endswith('USDT') else symbol[:-3]
        quote_coin = symbol[-4:] if symbol.endswith('USDT') else symbol[-3:]
        
        # 解析持仓方向
        if fill['posMode'] == 'hedge_mode':  # 双向持仓
            position_side = (PositionSide.LONG if fill['side'] == 'buy' 
                           else PositionSide.SHORT)
        else:  # 单向持仓
            position_side = PositionSide.LONG
            
        return FillResponse(
            trade_id=fill['tradeId'],
            order_id=fill['orderId'],
            symbol=symbol,
            pair=f"{base_coin}/{quote_coin}",
            base_coin=base_coin,
            quote_coin=quote_coin,
            position_side=position_side,
            trade_side=TradeSide(fill['tradeSide']) if 'tradeSide' in fill else None,
            trade_time=int(fill['cTime']),
            trade_scope=fill['tradeScope'],
            filled_price=Decimal(fill['price']),
            filled_base_amount=Decimal(fill['baseVolume']),
            filled_quote_value=Decimal(fill['quoteVolume']),
            fee=Decimal(fill['feeDetail'][0]['totalFee']),
            fee_currency=fill['feeDetail'][0]['feeCoin'],
            profit=Decimal(fill['profit']) if 'profit' in fill else None,
            position_mode=fill['posMode'],  
            source=fill.get('enterPointSource', 'API')
        )

    def get_spot_assets(self, coin: str = None, asset_type: str = 'hold_only') -> List[AssetBalance]:
        try:
            params = {'assetType': asset_type}
            if coin:
                params['coin'] = coin.lower()
            
            account_api = self._get_api(InstType.SPOT, 'account')
            response = account_api.assets(params)

            if response.get('code') != '00000':
                raise BitgetAPIException(response.get('msg'), response.get('code'))

            asset_list = []
            for item in response.get('data', []):
                try:
                    # 确保所有字段都有默认值
                    utime = item.get('uTime')
                    update_time = int(utime) if utime is not None else int(time.time() * 1000)
                    
                    asset = AssetBalance(
                        coin=item.get('coin', '').upper(),
                        available=Decimal(str(item.get('available', '0'))),
                        frozen=Decimal(str(item.get('frozen', '0'))),
                        locked=Decimal(str(item.get('locked', '0'))),
                        limit_available=Decimal(str(item.get('limitAvailable', '0'))),
                        update_time=update_time
                    )
                    asset_list.append(asset)
                except (TypeError, ValueError) as e:
                    self.logger.error(f"解析资产数据失败: {str(e)}, 数据: {item}")
                    continue

            return asset_list

        except Exception as e:
            self.logger.error(f"获取现货资产失败: {str(e)}")
            raise

    def closeAllPositionsMarket(self, request: OrderRequest) -> OrderResponse:
        """一键市价平仓指定交易对
        
        Args:
            request: OrderRequest对象,必须包含pair和inst_type
        """
        try:
            if not request.pair:
                raise ValueError("OrderRequest必须包含pair字段")
                
            inst_type = self._get_inst_type(request)
            
            # 根据类型选择平仓方法
            if inst_type == InstType.SPOT:
                return self._close_spot_positions(request)
            else:  
                return self._close_futures_positions(request)
                
        except Exception as e:
            self.logger.error(f"一键平仓失败: {str(e)}")
            return OrderResponse(
                status="failed",
                success=False,
                error_message=str(e)
            )

    def _close_spot_positions(self, request: OrderRequest) -> OrderResponse:
        try:
            # 获取指定币种的持仓
            base_coin = request.pair.split('/')[0]
            assets = self.get_spot_assets(coin=base_coin, asset_type='hold_only')
            
            if not assets or not assets[0].available:
                return OrderResponse(
                    status="success",
                    success=True,
                    error_message="无可平仓数量"
                )
                
            asset = assets[0]
            if asset.available <= 0:
                return OrderResponse(
                    status="success",
                    success=True,
                    error_message="无可平仓数量"
                )
                    
            # 使用传入的 base_size
            sell_request = OrderRequest(
                inst_type=InstType.SPOT,
                symbol=request.symbol.replace('/', '').upper(),
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                base_size=request.base_size,
                client_order_id=request.client_order_id
            )
            
            response = self.place_order(sell_request)
            
            if response.success:
                # 直接使用 place_order 返回的 FillResponse 对象
                return OrderResponse(
                    status="success",
                    success=True,
                    order_id=response.order_id,
                    client_order_id=response.client_order_id,
                    create_time=response.create_time,
                    data=response.data,  # FillResponse 对象
                    code=response.code,
                    api_endpoint="/api/v2/spot/trade/place-order"
                )
            else:
                return OrderResponse(
                    status="failed",
                    success=False,
                    error_message=response.error_message,
                    code=response.code,
                    order_id=response.order_id,
                    client_order_id=response.client_order_id,
                    data=None
                )
                
        except Exception as e:
            self.logger.error(f"现货一键平仓失败: {str(e)}")
            raise

    def _close_futures_positions(self, request: OrderRequest) -> OrderResponse:
        """合约一键平仓实现"""
        try:
            # 构建请求参数
            base_coin = request.pair.split('/')[0]
            quote_coin = request.pair.split('/')[1]
            if quote_coin == 'USDT':
                params = {
                    'productType': 'USDT-FUTURES',
                    'symbol': request.pair.replace('/', '').upper(),  # 转换格式: BTC/USDT -> BTCUSDT
                }
            else:
                self.logger.error(f"合约一键平仓失败: {request.pair} 不是USDT-FUTURES")
                raise
            
            # 如果指定了持仓方向
            if request.position_side:
                params['holdSide'] = request.position_side.value
            
            # 发送一键平仓请求
            order_api = self._get_api(InstType.FUTURES, 'order')
            response = order_api.closePositions(params)
            
            if response.get('code') != '00000':
                raise BitgetAPIException(response.get('msg'), response.get('code'))
                
            # 处理响应
            data = response.get('data', {})
            success = not data.get('failureList')
            
            return OrderResponse(
                status="success" if success else "partial",
                success=True,
                data=data,
                code=response.get('code'),
                api_endpoint="/api/v2/mix/order/close-positions"
            )
            
        except Exception as e:
            self.logger.error(f"合约一键平仓失败: {str(e)}")
            raise