import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from rich.logging import RichHandler
from rich.console import Console

# 默认日志目录
LOG_DIR = "logs"

def setup_logger(log_level=logging.INFO, console_output=False):
    """
    初始化全局日志配置
    
    Args:
        log_level: 日志级别
        console_output: 是否同时输出到控制台
    """
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
    
    # 日志文件名包含日期，方便区分
    log_filename = "agent.log"
    log_path = os.path.join(LOG_DIR, log_filename)
    
    # 获取根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # 清除现有的处理器，防止重复打印或冲突
    if root_logger.handlers:
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
    
    # 定义日志格式
    file_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s"
    )
    
    # 文件输出 (带自动切分，保留 5 个备份，每个最大 10MB)
    file_handler = RotatingFileHandler(
        log_path, 
        maxBytes=10*1024*1024, 
        backupCount=5, 
        encoding="utf-8"
    )
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(log_level)
    root_logger.addHandler(file_handler)
    
    # 控制台输出 (可选)
    if console_output:
        # 使用 RichHandler 保持控制台日志美观
        rich_handler = RichHandler(
            console=Console(stderr=True), 
            show_path=False,
            omit_repeated_times=False
        )
        rich_handler.setLevel(logging.WARNING) # 控制台只显示警告及以上级别
        root_logger.addHandler(rich_handler)
    
    logger = logging.getLogger("CodingAgent")
    logger.info(f"日志系统初始化完成。日志文件: {log_path}, 级别: {logging.getLevelName(log_level)}")
    
    # 捕获未处理的异常
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.critical("未捕获的异常", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception
    
    return logger

# 创建全局 logger 实例（在 main.py 中调用 setup_logger 后会生效）
logger = logging.getLogger("CodingAgent")

