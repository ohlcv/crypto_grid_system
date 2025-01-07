from src.utils.logger.log_helper import get_logger
from src.utils.logger.log_helper import LogMode

# 创建不同模式的日志记录器
console_logger = get_logger('test', mode=LogMode.CONSOLE_ONLY)
file_logger = get_logger('test', mode=LogMode.FILE_ONLY)
both_logger = get_logger('test', mode=LogMode.CONSOLE_AND_FILE)

# 在类中使用
class TestClass:
    def __init__(self):
        self.logger = get_logger('test')
        
    def test_method(self):
        self.logger.info("测试消息")  # 输出: [时间] [INFO] [TestClass.test_method] 测试消息