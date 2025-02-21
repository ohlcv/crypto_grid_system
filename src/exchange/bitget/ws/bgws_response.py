import json
from datetime import datetime, timedelta

class TickerData:
    def __init__(self, data):
        """
        初始化Ticker数据，处理字段缺失和容错。
        """
        self.instId = data.get('instId', 'Unknown')  # 默认值'Unknown'防止字段缺失
        self.lastPr = self._to_float(data.get('lastPr'))
        self.open24h = self._to_float(data.get('open24h'))
        self.high24h = self._to_float(data.get('high24h'))
        self.low24h = self._to_float(data.get('low24h'))
        self.change24h = self._to_float(data.get('change24h'))
        self.bidPr = self._to_float(data.get('bidPr'))
        self.askPr = self._to_float(data.get('askPr'))
        self.bidSz = self._to_float(data.get('bidSz'))
        self.askSz = self._to_float(data.get('askSz'))
        self.baseVolume = self._to_float(data.get('baseVolume'))
        self.quoteVolume = self._to_float(data.get('quoteVolume'))
        self.openUtc = self._to_float(data.get('openUtc'))
        self.changeUtc24h = self._to_float(data.get('changeUtc24h'), default=0.0)  # 默认值为0.0
        self.timestamp = self._to_int(data.get('ts'))

    def _to_float(self, value, default=0.0):
        """
        转换值为浮点型，若转换失败则返回默认值。
        """
        try:
            return float(value) if value is not None else default
        except (ValueError, TypeError):
            return default

    def _to_int(self, value, default=0):
        """
        转换值为整数，若转换失败则返回默认值。
        """
        try:
            return int(value) if value is not None else default
        except (ValueError, TypeError):
            return default

    def __repr__(self):
        """
        返回JSON格式的Ticker数据，便于调试。
        """
        return json.dumps({
            'instId': self.instId,
            'lastPr': self.lastPr,
            'open24h': self.open24h,
            'high24h': self.high24h,
            'low24h': self.low24h,
            'change24h': self.change24h,
            'bidPr': self.bidPr,
            'askPr': self.askPr,
            'bidSz': self.bidSz,
            'askSz': self.askSz,
            'baseVolume': self.baseVolume,
            'quoteVolume': self.quoteVolume,
            'openUtc': self.openUtc,
            'changeUtc24h': self.changeUtc24h,
            'ts': self.timestamp
        }, ensure_ascii=False, indent=4)

    def get_datetime(self):
        """
        获取时间戳的上海时间表示。
        """
        timestamp_in_seconds = self.timestamp / 1000.0
        utc_datetime = datetime.utcfromtimestamp(timestamp_in_seconds)
        shanghai_time_delta = timedelta(hours=8)
        shanghai_datetime = utc_datetime + shanghai_time_delta
        return shanghai_datetime.strftime('%Y-%m-%d %H:%M:%S')

    def update(self, new_data):
        """
        更新Ticker数据，重新初始化。
        """
        self.__init__(new_data)


class WebSocketResponse:
    def __init__(self, response_data):
        """
        处理WebSocket响应。
        """
        if isinstance(response_data, str):
            response_data = json.loads(response_data)
        
        self.action = response_data.get('action', '')
        self.arg = response_data.get('arg', {})
        self.data = [
            TickerData(item) for item in response_data.get('data', [])
        ]
        self.ts = self._to_int(response_data.get('ts'))

    def _to_int(self, value, default=0):
        """
        转换值为整数，若转换失败则返回默认值。
        """
        try:
            return int(value) if value is not None else default
        except (ValueError, TypeError):
            return default

    def __repr__(self):
        """
        返回响应对象的字符串表示。
        """
        return f"Action: {self.action}\nArg: {self.arg}\nData: {self.data}\nTimestamp: {self.ts}"

    def update_data(self, new_data):
        """
        更新响应中的数据。
        """
        self.data = [TickerData(item) for item in new_data]


if __name__ == '__main__':
    # 合约示例数据
    futures_response = '''
    {
        "action": "snapshot",
        "arg": {
            "instType": "USDT-FUTURES",
            "channel": "ticker",
            "instId": "BTCUSDT"
        },
        "data": [
            {
                "instId": "BTCUSDT",
                "lastPr": "27000.5",
                "bidPr": "27000",
                "askPr": "27000.5",
                "bidSz": "2.71",
                "askSz": "8.76",
                "open24h": "27000.5",
                "high24h": "30668.5",
                "low24h": "26999.0",
                "change24h": "-0.00002",
                "fundingRate": "0.000010",
                "nextFundingTime": "1695722400000",
                "markPrice": "27000.0",
                "indexPrice": "25702.4",
                "holdingAmount": "929.502",
                "baseVolume": "368.900",
                "quoteVolume": "10152429.961",
                "openUtc": "27000.5",
                "symbolType": 1,
                "symbol": "BTCUSDT",
                "deliveryPrice": "0",
                "ts": "1695715383021"
            }
        ],
        "ts": 1695715383039
    }
    '''
    
    # 现货示例数据
    spot_response = '''
    {
        "action": "snapshot",
        "arg": {
            "instType": "SPOT",
            "channel": "ticker",
            "instId": "ETHUSDT"
        },
        "data": [
            {
                "instId": "ETHUSDT",
                "lastPr": "2200.10",
                "open24h": "0.00",
                "high24h": "0.00",
                "low24h": "0.00",
                "change24h": "0.00",
                "bidPr": "1792",
                "askPr": "2200.1",
                "bidSz": "0.0084",
                "askSz": "19740.8811",
                "baseVolume": "0.0000",
                "quoteVolume": "0.0000",
                "openUtc": "0.00",
                "changeUtc24h": "0",
                "ts": "1695702438018"
            }
        ],
        "ts": 1695702438029
    }
    '''

    # 测试
    futures_ws_response = WebSocketResponse(futures_response)
    print(futures_ws_response)
    print(futures_ws_response.data[0].get_datetime())

    spot_ws_response = WebSocketResponse(spot_response)
    print(spot_ws_response)
    print(spot_ws_response.data[0].get_datetime())
