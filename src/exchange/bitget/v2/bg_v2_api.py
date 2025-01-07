from decimal import ROUND_HALF_UP, Decimal
from ..consts import GET, POST
from .spot.order_api import SpotOrderApi
from .mix.order_api import MixOrderApi
from src.utils.logger.log_helper import api_logger
from src.utils.error.error_handler import error_handler


class BitgetSpotAPI:
    def __init__(self, api_key, api_secret_key, passphrase):
        # 初始化 API 密钥、秘密密钥和密码短语
        self.api_key = api_key
        self.api_secret_key = api_secret_key
        self.passphrase = passphrase
        self.order_api = SpotOrderApi(api_key, api_secret_key, passphrase)
        self.logger = api_logger

    def get_account_info(self):
        self.logger.info("获取现货账户信息")
        try:
            response = self.order_api._request_with_params(GET, '/api/v2/spot/account/info', {})
            self.logger.debug(f"账户信息响应: {response}")
            return response
        except Exception as e:
            self.logger.error("获取账户信息失败", exc_info=e)
            return e

    @error_handler()
    def get_pairs(self, symbol=None):
        """获取现货交易对信息"""
        params = {}
        if symbol:
            params["symbol"] = symbol
        response = self.order_api._request_with_params(GET, '/api/v2/spot/public/symbols', params)
        # print("[BitgetSpotAPI] get_pairs: ", response)
        return response


    @error_handler()
    def place_order(self, symbol, size, trade_side, side=None, price=None, client_oid=None):
        self.logger.info(f"下现货订单 - {symbol} - {trade_side} - {size}")
        params = {
            "symbol": symbol,
            "size": str(Decimal(size).quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)),
            "orderType": "market"
        }
        if trade_side == "open":
            params["side"] = "buy"
        elif trade_side == "close":
            params["side"] = "sell"
        else:
            err_msg = "trade_side 参数必须是 'open' 或 'close'"
            self.logger.error(err_msg)
            raise ValueError(err_msg)

        if price:
            params["orderType"] = "limit"
            params["price"] = price
        if client_oid:
            params["clientOid"] = client_oid

        self.logger.debug(f"订单参数: {params}")
        response = self.order_api.placeOrder(params)
        self.logger.info(f"下单成功 - {response.get('data', {}).get('orderId')}")
        return response

    @error_handler()
    def get_fills(self, symbol, order_id=None, start_time=None, end_time=None, limit=None, id_less_than=None):
        """获取合约成交明细"""
        # 初始化请求参数字典
        params = {
            "symbol": symbol,  # 交易对名称
        }
        # 动态构建参数
        if order_id is not None:
            params["orderId"] = order_id  # 如果传入了 order_id，添加到请求中
        if start_time is not None:
            params["startTime"] = start_time  # 如果传入了 start_time，添加到请求中
        if end_time is not None:
            params["endTime"] = end_time  # 如果传入了 end_time，添加到请求中
        if limit is not None:
            params["limit"] = limit  # 如果传入了 limit，添加到请求中
        if id_less_than is not None:
            params["idLessThan"] = id_less_than  # 如果传入了 id_less_than，添加到请求中
        # print(f"[BitgetSpotAPI] spot_fills_params: {params}")
        response = self.order_api.fills(params)
        return response

    @error_handler()
    def calculate_spot_average_price(self, spot_fills):
        """计算现货成交明细的加权平均成交价格"""
        if spot_fills.get('code') == '00000' or spot_fills.get('msg') == 'success':
            fill_list = spot_fills['data']
            total_quote_volume = 0
            total_price = 0
            # 遍历成交明细列表
            for fill in fill_list:
                price = float(fill.get('priceAvg'))  # 获取成交均价
                amount = float(fill.get('amount'))  # 获取成交金额
                # 累加成交金额和加权价格
                total_quote_volume += amount
                total_price += price * amount  # 价格乘以金额来计算加权价格
            # 计算平均成交价格
            if total_quote_volume != 0:
                average_price = total_price / total_quote_volume
            else:
                average_price = 0
            return average_price
        else:
            # print("Failed to get fills or error in response.")
            return None


class BitgetMixAPI:
    def __init__(self, api_key, api_secret_key, passphrase):
        # 初始化 API 密钥、秘密密钥和密码短语
        self.api_key = api_key
        self.api_secret_key = api_secret_key
        self.passphrase = passphrase
        self.order_api = MixOrderApi(api_key, api_secret_key, passphrase)
        self.logger = api_logger

    @error_handler()
    def get_account_info(self):
        self.logger.info("获取合约账户信息")
        response = self.order_api._request_with_params(GET, '/api/v2/spot/account/info', {})
        self.logger.debug(f"账户信息响应: {response}")
        return response

    def get_pairs(self, symbol=None, productType="USDT-FUTURES"):
        """获取合约交易对信息"""
        try:
            params = {
                "productType": productType  # 产品类型，固定为 "USDT-FUTURES"
            }
            if symbol:
                params["symbol"] = symbol
            response = self.order_api._request_with_params(GET, '/api/v2/mix/market/contracts', params)
            # print("[BitgetSpotAPI] get_pairs: ", response)
            return response
        except Exception as e:
            return e

    @error_handler()
    def place_order(self, symbol, size, trade_side, side, price=None, client_oid=None):
        self.logger.info(f"下合约订单 - {symbol} - {trade_side} - {side} - {size}")
        if trade_side not in ["open", "close"]:
            err_msg = "tradeSide 必须为 'open' 或 'close'"
            self.logger.error(err_msg)
            raise ValueError(err_msg)

        params = {
            "symbol": symbol,
            "side": side,
            "tradeSide": trade_side,
            "size": str(Decimal(size).quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)),
            "productType": "USDT-FUTURES",
            "marginMode": "crossed",
            "marginCoin": "USDT",
            "orderType": "market"
        }
        if price:
            params["orderType"] = "limit"
            params["price"] = price
        if client_oid:
            params["clientOid"] = client_oid
        self.logger.debug(f"订单参数: {params}")
        response = self.order_api.placeOrder(params)
        self.logger.info(f"下单成功 - {response.get('data', {}).get('orderId')}")
        return response

    @error_handler()
    def all_close_positions(self, symbol, hold_side=None):
        self.logger.info(f"平仓操作 - {symbol} - {hold_side}")
        params = {
            "symbol": symbol,
            "productType": "USDT-FUTURES"
        }
        if hold_side:
            params["holdSide"] = hold_side

        self.logger.debug(f"平仓参数: {params}")
        response = self.order_api.closePositions(params)
        self.logger.info("平仓成功")
        return response

    @error_handler()
    def get_fills(self, symbol, order_id=None, start_time=None, end_time=None, limit=None, id_less_than=None, productType="USDT-FUTURES"):
        """获取合约成交明细"""
        # 初始化请求参数字典
        params = {
            "productType": productType  # 产品类型，固定为 "USDT-FUTURES"
        }
        # 动态构建参数
        if symbol:
            params["symbol"] = symbol  # 如果传入了 order_id，添加到请求中
        if order_id is not None:
            params["orderId"] = order_id  # 如果传入了 order_id，添加到请求中
        if start_time is not None:
            params["startTime"] = start_time  # 如果传入了 start_time，添加到请求中
        if end_time is not None:
            params["endTime"] = end_time  # 如果传入了 end_time，添加到请求中
        if limit is not None:
            params["limit"] = limit  # 如果传入了 limit，添加到请求中
        if id_less_than is not None:
            params["idLessThan"] = id_less_than  # 如果传入了 id_less_than，添加到请求中
        # print(f"[BitgetMixAPI] mix_fills_params: {params}")
        response = self.order_api.fills(params)
        return response

    @error_handler()
    def calculate_average_price(self, future_fills):
        """计算合约成交明细的加权平均成交价格"""
        if future_fills.get('code') == '00000' or future_fills.get('msg') == 'success':
            fill_list = future_fills['data']['fillList']
            total_quote_volume = 0
            total_price = 0
            # 遍历 fillList 列表
            for fill in fill_list:
                price = float(fill.get('price'))  # 获取价格
                quote_volume = float(fill.get('quoteVolume'))  # 获取成交量
                # 累加成交量和加权价格
                total_quote_volume += quote_volume
                total_price += price * quote_volume  # 价格乘以成交量来计算加权价格
            # 计算平均成交价格
            if total_quote_volume != 0:
                average_price = total_price / total_quote_volume
            else:
                average_price = 0
            return average_price
        else:
            # print("Failed to get fills or error in response.")
            return None


