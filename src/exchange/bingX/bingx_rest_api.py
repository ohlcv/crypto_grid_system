from typing import Optional, Dict, Any, List
from decimal import Decimal
import time
import hmac
import hashlib
import requests
import json

from .exceptions import BingXAPIException

class BingXRestAPI:
    """BingX REST API封装"""

    def __init__(self, api_key: str, api_secret: str, passphrase: str, is_spot: bool = True):
        """初始化REST API客户端
        
        Args:
            api_key: API Key
            api_secret: API密钥
            passphrase: API密码
            is_spot: 是否为现货API
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.base_url = "https://open-api.bingx.com"
        self._is_spot = is_spot
        
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'X-BX-APIKEY': self.api_key,
        })

    def _generate_signature(self, params: dict) -> str:
        """生成API签名"""
        # 添加时间戳
        params['timestamp'] = str(int(time.time() * 1000))
        
        # 按key排序并拼接参数
        query_string = '&'.join(
            f"{key}={params[key]}" 
            for key in sorted(params.keys())
            if params[key] is not None  # 排除None值
        )
        
        # 使用HMAC-SHA256生成签名
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return signature

    def _request(self, method: str, endpoint: str, params: dict = None) -> dict:
        """发送API请求
        
        Args:
            method: 请求方法 (GET/POST/DELETE)
            endpoint: API端点
            params: 请求参数
            
        Returns:
            API响应数据
            
        Raises:
            BingXAPIException: API调用异常
        """
        try:
            # 构建完整URL
            url = f"{self.base_url}{endpoint}"
            params = params or {}
            
            # 添加时间戳
            params['timestamp'] = str(int(time.time() * 1000))
            
            # 生成签名
            query_string = '&'.join(f"{k}={v}" for k, v in sorted(params.items()) if v is not None)
            signature = self._generate_signature(query_string)
            params['signature'] = signature

            # 设置请求头
            headers = {
                'Content-Type': 'application/json',
                'X-BX-APIKEY': self.api_key
            }

            # 发送请求
            if method == 'GET':
                response = requests.get(url, params=params, headers=headers)
            elif method == 'POST':
                response = requests.post(url, json=params, headers=headers)
            elif method == 'DELETE':
                response = requests.delete(url, params=params, headers=headers)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            # 检查HTTP状态码
            response.raise_for_status()

            # 解析响应
            data = response.json()
            
            # BingX使用code=0表示成功
            if data.get('code') != 0:
                raise BingXAPIException(
                    error_code=data.get('code'),
                    error_message=data.get('msg', 'Unknown error')
                )

            return data.get('data', {})

        except requests.exceptions.RequestException as e:
            raise BingXAPIException(f"HTTP request failed: {str(e)}")
        except json.JSONDecodeError as e:
            raise BingXAPIException(f"Failed to parse response: {str(e)}")
    
    def get_info(self) -> Dict:
        """获取账户信息"""
        endpoint = "/api/v1/account" if self._is_spot else "/api/v1/user"
        return self._request('GET', endpoint)

    def get_symbol_config(self, symbol: str = None) -> List[Dict]:
        """获取交易对信息
        
        Args:
            symbol: 交易对名称(可选)
            
        Returns:
            交易对信息列表
        """
        endpoint = "/api/v1/symbols" if self._is_spot else "/api/v1/contracts"
        params = {"symbol": symbol} if symbol else {}
        return self._request('GET', endpoint, params)

    def get_ticker(self, symbol: str) -> Dict:
        """获取行情ticker
        
        Args:
            symbol: 交易对名称
            
        Returns:
            ticker数据
        """
        endpoint = "/api/v1/ticker/24hr" if self._is_spot else "/api/v1/ticker"
        params = {"symbol": symbol}
        return self._request('GET', endpoint, params)

    def get_positions(self, symbol: str = None) -> List[Dict]:
        """获取持仓信息(仅合约)
        
        Args:
            symbol: 交易对名称(可选)
            
        Returns:
            持仓信息列表
        """
        if self._is_spot:
            raise BingXAPIException("This endpoint is for perpetual only")
            
        endpoint = "/api/v1/positions"
        params = {"symbol": symbol} if symbol else {}
        return self._request('GET', endpoint, params)

    def place_order(self, 
                   symbol: str,
                   side: str,
                   order_type: str,
                   quantity: Decimal,
                   price: Optional[Decimal] = None,
                   client_order_id: Optional[str] = None) -> Dict:
        """下单
        
        Args:
            symbol: 交易对名称
            side: 订单方向(buy/sell)
            order_type: 订单类型(market/limit)
            quantity: 数量
            price: 价格(限价单必填)
            client_order_id: 客户端订单ID(可选)
            
        Returns:
            订单信息
        """
        endpoint = "/api/v1/order"
        
        params = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "quantity": str(quantity),
            "price": str(price) if price else None,
            "newClientOrderId": client_order_id
        }
        
        return self._request('POST', endpoint, params)

    def cancel_order(self, symbol: str, order_id: str) -> Dict:
        """撤销订单
        
        Args:
            symbol: 交易对名称
            order_id: 订单ID
            
        Returns:
            撤单结果
        """
        endpoint = "/api/v1/order"
        params = {
            "symbol": symbol,
            "orderId": order_id
        }
        return self._request('DELETE', endpoint, params)

    def get_order(self, symbol: str, order_id: str) -> Dict:
        """查询订单
        
        Args:
            symbol: 交易对名称
            order_id: 订单ID
            
        Returns:
            订单信息
        """
        endpoint = "/api/v1/order"
        params = {
            "symbol": symbol,
            "orderId": order_id
        }
        return self._request('GET', endpoint, params)

    def get_open_orders(self, symbol: str = None) -> List[Dict]:
        """查询当前挂单
        
        Args:
            symbol: 交易对名称(可选)
            
        Returns:
            订单列表
        """
        endpoint = "/api/v1/openOrders"
        params = {"symbol": symbol} if symbol else {}
        return self._request('GET', endpoint, params)