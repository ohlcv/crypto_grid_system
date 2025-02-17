# src/exchange/bingx/exceptions.py

"""
异常处理模块，用于处理BingX API相关的异常
"""

from typing import Optional

class BingXAPIException(Exception):
    """BingX API异常基类"""
    
    def __init__(self, 
                 error_code: Optional[int] = None,
                 error_message: Optional[str] = None):
        self.error_code = error_code
        self.error_message = error_message

    def __str__(self):
        return f'BingXAPIException - code: {self.error_code}, msg: {self.error_message}'

class BingXRequestException(Exception):
    """BingX请求异常"""
    
    def __init__(self, message: str):
        self.message = message

    def __str__(self):
        return f'BingXRequestException: {self.message}'

error_codes = {
    100001: 'Signature authentication failed',
    100202: 'Insufficient balance',
    100400: 'Invalid parameter',
    100440: 'Order price deviates greatly from the market price',
    100500: 'Internal server error',
    100503: 'Server busy'
}