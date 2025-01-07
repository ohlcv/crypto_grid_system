# API 调用示例
from src.utils.error.error_handler import error_handler, NetworkError, ApiError

# 定义错误处理函数
def handle_network_error(e, error_info):
    # 网络错误处理逻辑
    return {"error": "network", "info": error_info}

def handle_api_error(e, error_info):
    # API错误处理逻辑
    return {"error": "api", "info": error_info}

# 错误处理映射
error_handlers = {
    NetworkError: handle_network_error,
    ApiError: handle_api_error
}

# 重试配置
retry_config = {
    'max_retries': 3,
    'delay': 1.0,
    'exceptions': (NetworkError, ApiError)
}

class BitgetClient:
    @error_handler(error_types=error_handlers, retry_config=retry_config)
    def place_order(self, symbol, size, side):
        # 下单逻辑
        pass
    
    @error_handler(retry_config={'max_retries': 2, 'delay': 0.5})
    def get_ticker(self, symbol):
        # 获取行情
        pass