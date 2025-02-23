# /exchange/bitget/v2/spot/
from ...client import Client
from ...consts import GET, POST


class OrderApi(Client):
    """
    现货交易 API，提供订单管理、历史查询等功能。
    """

    def __init__(self, api_key, api_secret_key, passphrase, use_server_time=False, first=False):
        """
        初始化 SpotOrderApi 实例。

        :param api_key: API 密钥
        :param api_secret_key: API 密钥的密钥
        :param passphrase: 交易密码
        :param use_server_time: 是否使用服务器时间
        :param first: 是否是首次请求
        """
        Client.__init__(self, api_key, api_secret_key, passphrase, use_server_time, first)

    def placeOrder(self, params):
        """创建现货交易订单。"""
        return self._request_with_params(POST, '/api/v2/spot/trade/place-order', params)

    def batchOrders(self, params):
        """批量创建现货交易订单。"""
        return self._request_with_params(POST, '/api/v2/spot/trade/batch-orders', params)

    def cancelOrder(self, params):
        """取消现货交易订单。"""
        return self._request_with_params(POST, '/api/v2/spot/trade/cancel-order', params)

    def batchCancelOrder(self, params):
        """批量取消现货交易订单。"""
        return self._request_with_params(POST, '/api/v2/spot/trade/batch-cancel-order', params)

    def historyOrders(self, params):
        """获取未完成的历史订单。"""
        return self._request_with_params(GET, '/api/v2/spot/trade/unfilled-orders', params)

    def historyOrders(self, params):
        """获取历史订单记录。"""
        return self._request_with_params(GET, '/api/v2/spot/trade/history-orders', params)

    def fills(self, params):
        """获取已成交的订单记录。"""
        return self._request_with_params(GET, '/api/v2/spot/trade/fills', params)

    def placePlanOrder(self, params):
        """创建计划订单。"""
        return self._request_with_params(POST, '/api/v2/spot/trade/place-plan-order', params)

    def modifyPlanOrder(self, params):
        """修改计划订单。"""
        return self._request_with_params(POST, '/api/v2/spot/trade/modify-plan-order', params)

    def cancelPlanOrder(self, params):
        """取消计划订单。"""
        return self._request_with_params(POST, '/api/v2/spot/trade/cancel-plan-order', params)

    def currentPlanOrder(self, params):
        """获取当前计划订单。"""
        return self._request_with_params(GET, '/api/v2/spot/trade/current-plan-order', params)

    def historyPlanOrder(self, params):
        """获取历史计划订单记录。"""
        return self._request_with_params(GET, '/api/v2/spot/trade/history-plan-order', params)

    def traderOrderCloseTracking(self, params):
        """跟踪交易员订单关闭状态。"""
        return self._request_with_params(POST, '/api/v2/copy/spot-trader/order-close-tracking', params)

    def traderOrderCurrentTrack(self, params):
        """获取当前交易员订单跟踪信息。"""
        return self._request_with_params(GET, '/api/v2/copy/spot-trader/order-current-track', params)

    def traderOrderHistoryTrack(self, params):
        """获取历史交易员订单的跟踪记录。"""
        return self._request_with_params(GET, '/api/v2/copy/spot-trader/order-history-track', params)
