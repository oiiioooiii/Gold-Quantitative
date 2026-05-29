# 日志配置模块
import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime


def setup_logger(config: dict) -> logging.Logger:
    """
    配置日志系统
    
    Args:
        config: 配置字典，包含日志相关配置
        
    Returns:
        配置好的 Logger 对象
    """
    # 创建日志目录（如果不存在）
    log_config = config.get('logging', {})
    log_file_path = log_config.get('file_path', './logs/trading_bot.log')
    log_dir = os.path.dirname(log_file_path)
    
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    
    # 创建 logger
    logger = logging.getLogger('GoldTradingBot')
    logger.setLevel(getattr(logging, log_config.get('level', 'INFO')))
    
    # 避免重复添加 handler
    if logger.handlers:
        return logger
    
    # 日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 控制台 handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 文件 handler（使用 RotatingFileHandler 防止日志文件过大）
    max_bytes = log_config.get('max_bytes', 10485760)  # 默认 10MB
    backup_count = log_config.get('backup_count', 5)
    
    file_handler = RotatingFileHandler(
        log_file_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger


def get_logger() -> logging.Logger:
    """
    获取已配置的 logger
    
    Returns:
        Logger 对象
    """
    return logging.getLogger('GoldTradingBot')
