from ...client import Client
from ...consts import GET, POST


class MixOrderApi(Client):
    def __init__(self, api_key, api_secret_key, passphrase, use_server_time=False, first=False):
        """初始化 MixOrderApi 实例。"""
        Client.__init__(self, api_key, api_secret_key, passphrase, use_server_time, first)

    def placeOrder(self, params):
        """创建混合订单。"""
        return self._request_with_params(POST, '/api/v2/mix/order/place-order', params)

    def clickBackhand(self, params):
        """点击后端操作。"""
        return self._request_with_params(POST, '/api/v2/mix/order/click-backhand', params)

    def batchPlaceOrder(self, params):
        """批量创建混合订单。"""
        return self._request_with_params(POST, '/api/v2/mix/order/batch-place-order', params)

    def cancelOrder(self, params):
        """取消混合订单。"""
        return self._request_with_params(POST, '/api/v2/mix/order/cancel-order', params)

    def batchCancelOrders(self, params):
        """批量取消混合订单。"""
        return self._request_with_params(POST, '/api/v2/mix/order/batch-cancel-orders', params)

    def closePositions(self, params):
        """关闭混合交易仓位。"""
        return self._request_with_params(POST, '/api/v2/mix/order/close-positions', params)

    def ordersHistory(self, params):
        """获取混合订单历史记录。"""
        return self._request_with_params(GET, '/api/v2/mix/order/orders-history', params)

    def ordersPending(self, params):
        """获取待处理的混合订单。"""
        return self._request_with_params(GET, '/api/v2/mix/order/orders-pending', params)

    def detail(self, params):
        """获取混合订单详情。"""
        return self._request_with_params(GET, '/api/v2/mix/order/detail', params)

    def fills(self, params):
        """获取混合订单的成交记录。"""
        return self._request_with_params(GET, '/api/v2/mix/order/fills', params)

    def placePlanOrder(self, params):
        """创建混合计划订单。"""
        return self._request_with_params(POST, '/api/v2/mix/order/place-plan-order', params)

    def cancelPlanOrder(self, params):
        """取消混合计划订单。"""
        return self._request_with_params(POST, '/api/v2/mix/order/cancel-plan-order', params)

    def ordersPlanPending(self, params):
        """获取待处理的混合计划订单。"""
        return self._request_with_params(GET, '/api/v2/mix/order/orders-plan-pending', params)

    def ordersPlanHistory(self, params):
        """获取混合计划订单历史记录。"""
        return self._request_with_params(GET, '/api/v2/mix/order/orders-plan-history', params)

    def traderOrderClosePositions(self, params):
        """跟踪交易员关闭混合仓位的操作。"""
        return self._request_with_params(POST, '/api/v2/copy/mix-trader/order-close-positions', params)

    def traderOrderCurrentTrack(self, params):
        """获取当前交易员混合订单的跟踪信息。"""
        return self._request_with_params(GET, '/api/v2/copy/mix-trader/order-current-track', params)

    def traderOrderHistoryTrack(self, params):
        """获取历史交易员混合订单的跟踪记录。"""
        return self._request_with_params(GET, '/api/v2/copy/mix-trader/order-history-track', params)

    def followerClosePositions(self, params):
        """跟踪跟随者关闭混合仓位的操作。"""
        return self._request_with_params(POST, '/api/v2/copy/mix-follower/close-positions', params)

    def followerQueryCurrentOrders(self, params):
        """查询跟随者的当前混合订单。"""
        return self._request_with_params(GET, '/api/v2/copy/mix-follower/query-current-orders', params)

    def followerQueryHistoryOrders(self, params):
        """查询跟随者的历史混合订单。"""
        return self._request_with_params(GET, '/api/v2/copy/mix-follower/query-history-orders', params)
