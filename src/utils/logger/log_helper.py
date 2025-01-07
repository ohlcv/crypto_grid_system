from .log_manager import LogManager, LogMode
import os

# 从环境变量或配置文件获取日志模式
LOG_MODE = os.getenv('LOG_MODE', 'both')
DEFAULT_MODE = {
    'console': LogMode.CONSOLE_ONLY,
    'file': LogMode.FILE_ONLY,
    'both': LogMode.CONSOLE_AND_FILE
}.get(LOG_MODE, LogMode.CONSOLE_AND_FILE)

def get_logger(name: str, mode: LogMode = None):
    """获取日志记录器"""
    mode = mode or DEFAULT_MODE
    return LogManager.get_instance().get_logger(name, mode=mode)

# 创建不同模块的记录器
grid_logger = get_logger('grid')         # 网格策略日志
trade_logger = get_logger('trade')       # 交易日志
ws_logger = get_logger('websocket')      # WebSocket日志
api_logger = get_logger('api')           # API请求日志
db_logger = get_logger('database')       # 数据库操作日志
ui_logger = get_logger('ui')             # UI操作日志
error_logger = get_logger("error")