import functools
import traceback
from enum import Enum
from typing import Optional, Type, Union, Callable
from datetime import datetime

from src.utils.logger.log_helper import error_logger

class ErrorCode(Enum):
    """错误码定义"""
    SUCCESS = (0, "成功")
    NETWORK_ERROR = (1001, "网络连接错误")
    API_ERROR = (1002, "API调用错误")
    PARAM_ERROR = (1003, "参数错误")
    AUTH_ERROR = (1004, "认证失败")
    SYSTEM_ERROR = (1005, "系统错误")
    TIMEOUT_ERROR = (1006, "超时错误")
    ORDER_ERROR = (2001, "下单失败")
    CANCEL_ERROR = (2002, "撤单失败")
    POSITION_ERROR = (2003, "持仓操作失败")
    
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message

class BaseError(Exception):
    """基础异常类"""
    def __init__(self, error_code: ErrorCode, message: Optional[str] = None):
        self.error_code = error_code
        self.message = message or error_code.message
        super().__init__(self.message)

class NetworkError(BaseError):
    """网络错误"""
    def __init__(self, message: Optional[str] = None):
        super().__init__(ErrorCode.NETWORK_ERROR, message)

class ApiError(BaseError):
    """API错误"""
    def __init__(self, message: Optional[str] = None):
        super().__init__(ErrorCode.API_ERROR, message)

class OrderError(BaseError):
    """订单错误"""
    def __init__(self, message: Optional[str] = None):
        super().__init__(ErrorCode.ORDER_ERROR, message)

def retry(max_retries: int = 3, delay: float = 1.0, 
          exceptions: Union[Type[Exception], tuple] = Exception,
          logger=None):
    """重试装饰器"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if logger:
                        logger.warning(f"第{attempt + 1}次重试失败: {str(e)}")
                    if attempt < max_retries - 1:
                        time.sleep(delay * (attempt + 1))
            raise last_exception
        return wrapper
    return decorator

def error_handler(error_types: Optional[dict] = None,
                 retry_config: Optional[dict] = None,
                 logger=None):
    """
    全局错误处理装饰器
    Args:
        error_types: 错误类型处理映射
        retry_config: 重试配置
        logger: 日志记录器
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            log = logger or error_logger
            func_name = func.__name__
            
            # 重试配置
            if retry_config:
                wrapper = retry(**retry_config, logger=log)(wrapper)
            
            try:
                return func(*args, **kwargs)
                
            except Exception as e:
                # 获取调用信息
                stack_trace = traceback.extract_stack()
                caller_info = stack_trace[-2]  # -2 获取装饰器调用处的信息
                
                # 错误日志信息
                error_info = {
                    'function': func_name,
                    'error_type': type(e).__name__,
                    'error_msg': str(e),
                    'file': caller_info.filename,
                    'line': caller_info.lineno,
                    'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                
                # 根据错误类型处理
                if error_types and type(e) in error_types:
                    handler = error_types[type(e)]
                    if isinstance(handler, Callable):
                        return handler(e, error_info)
                    
                # 记录错误日志
                log.error(
                    f"函数 {func_name} 执行错误\n"
                    f"位置: {error_info['file']}:{error_info['line']}\n"
                    f"类型: {error_info['error_type']}\n"
                    f"信息: {error_info['error_msg']}\n"
                    f"时间: {error_info['time']}", 
                    exc_info=e
                )
                
                # 重新抛出异常
                raise
                
        return wrapper
    return decorator

# 使用示例
if __name__ == '__main__':
    # 错误处理函数
    def handle_network_error(e, error_info):
        print(f"处理网络错误: {error_info}")
        return None
        
    def handle_api_error(e, error_info):
        print(f"处理API错误: {error_info}")
        return None
    
    # 错误处理映射
    error_handlers = {
        NetworkError: handle_network_error,
        ApiError: handle_api_error
    }
    
    # 重试配置
    retry_settings = {
        'max_retries': 3,
        'delay': 1.0,
        'exceptions': (NetworkError, ApiError)
    }
    
    # 使用装饰器
    @error_handler(error_types=error_handlers, retry_config=retry_settings)
    def test_func():
        raise NetworkError("测试网络错误")