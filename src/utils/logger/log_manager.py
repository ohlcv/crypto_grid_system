import os
import sys
import inspect
from datetime import datetime
import traceback
from threading import Lock
from typing import Dict, Optional
from enum import Enum

class LogMode(Enum):
    CONSOLE_ONLY = "console"      # 仅控制台输出
    FILE_ONLY = "file"           # 仅文件输出
    CONSOLE_AND_FILE = "both"    # 同时输出

class LogManager:
    _instance = None
    _lock = Lock()
    _loggers: Dict[str, 'Logger'] = {}
    
    @classmethod
    def get_instance(cls) -> 'LogManager':
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = cls()
        return cls._instance
    
    def get_logger(self, name: str, log_dir: str = None, mode: LogMode = LogMode.CONSOLE_AND_FILE) -> 'Logger':
        if name not in self._loggers:
            with self._lock:
                if name not in self._loggers:
                    log_dir = log_dir or os.path.join('logs', name)
                    self._loggers[name] = Logger(log_dir=log_dir, log_file_name=name, mode=mode)
        return self._loggers[name]
    
    def clear_loggers(self):
        with self._lock:
            self._loggers.clear()

class Logger:
    def __init__(self, log_dir: str, log_file_name: str, mode: LogMode = LogMode.CONSOLE_AND_FILE):
        self.log_dir = log_dir
        self.log_file_name = log_file_name
        self.mode = mode
        self._lock = Lock()
        self._current_date = None
        self._log_file = None
        self._update_log_file()
        
    def _get_log_file_path(self) -> str:
        current_date = datetime.now().strftime('%Y%m%d')
        return os.path.join(self.log_dir, f"{self.log_file_name}_{current_date}.log")
        
    def _update_log_file(self):
        if self.mode in [LogMode.FILE_ONLY, LogMode.CONSOLE_AND_FILE]:
            current_date = datetime.now().strftime('%Y%m%d')
            if current_date != self._current_date:
                with self._lock:
                    if self._log_file:
                        self._log_file.close()
                    os.makedirs(self.log_dir, exist_ok=True)
                    self._log_file = open(self._get_log_file_path(), 'a', encoding='utf-8')
                    self._current_date = current_date

    def _get_caller_info(self) -> str:
        """获取实际调用日志方法的类名和方法名"""
        try:
            # 获取调用堆栈帧
            current_frame = inspect.currentframe()
            caller_frame = current_frame.f_back.f_back.f_back  # 跳过 _write 和具体日志方法 (debug, info 等)
            
            # 获取调用者类名和方法名
            if caller_frame:
                frame_info = inspect.getframeinfo(caller_frame)
                caller_class = None
                if 'self' in caller_frame.f_locals:
                    caller_class = caller_frame.f_locals['self'].__class__.__name__
                
                # 方法名
                caller_method = frame_info.function
                
                if caller_class:
                    return f"{caller_class}.{caller_method}"
                return caller_method
        except Exception:
            return "Unknown"
                
    def _write(self, level: str, message: str, exc_info: Optional[Exception] = None):
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            caller_info = self._get_caller_info()
            log_message = f"[{timestamp}] [{level}] [{caller_info}] {message}"
            
            if exc_info:
                log_message += f"\nException: {str(exc_info)}\n{traceback.format_exc()}"
            
            # 根据模式决定输出位置
            if self.mode in [LogMode.CONSOLE_ONLY, LogMode.CONSOLE_AND_FILE]:
                print(log_message)
                
            if self.mode in [LogMode.FILE_ONLY, LogMode.CONSOLE_AND_FILE]:
                self._update_log_file()
                with self._lock:
                    self._log_file.write(log_message + "\n")
                    self._log_file.flush()
                    
        except Exception as e:
            print(f"Error writing log: {e}")
            
    def debug(self, message: str):
        self._write("DEBUG", message)
        
    def info(self, message: str):
        self._write("INFO", message)
        
    def warning(self, message: str):
        self._write("WARNING", message)
        
    def error(self, message: str, exc_info: Optional[Exception] = None):
        self._write("ERROR", message, exc_info)
        
    def critical(self, message: str, exc_info: Optional[Exception] = None):
        self._write("CRITICAL", message, exc_info)

    def set_mode(self, mode: LogMode):
        """修改日志输出模式"""
        self.mode = mode
        
    def __del__(self):
        if self._log_file:
            self._log_file.close()