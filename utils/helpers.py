# 辅助函数模块
import yaml
import os
from typing import Any, Dict, Optional


def load_config(config_path: str = 'config.yaml') -> Dict[str, Any]:
    """
    加载 YAML 配置文件
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        配置字典
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    return config


def validate_signal(signal: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    验证交易信号的必填字段
    
    Args:
        signal: 信号字典
        
    Returns:
        (是否有效, 错误信息)
    """
    required_fields = ['strategy', 'action', 'symbol']
    
    for field in required_fields:
        if field not in signal:
            return False, f"缺少必填字段: {field}"
    
    # 验证 action 字段
    valid_actions = ['buy', 'sell', 'close', 'close_all']
    if signal['action'] not in valid_actions:
        return False, f"无效的 action 值: {signal['action']}, 有效值为 {valid_actions}"
    
    return True, None


def format_price(price: float, digits: int = 2) -> str:
    """
    格式化价格显示
    
    Args:
        price: 价格
        digits: 小数位数
        
    Returns:
        格式化后的价格字符串
    """
    return f"{price:.{digits}f}"


def calculate_pip_value(symbol: str, price: float, lot: float = 1.0) -> float:
    """
    计算一个点的价值（对于 XAUUSD，1 点通常是 0.01）
    
    Args:
        symbol: 交易品种
        price: 当前价格
        lot: 手数
        
    Returns:
        一个点的价值
    """
    if symbol == 'XAUUSD':
        # 黄金：1 手，1 点（0.01）价值约 10 美元
        return lot * 10.0
    else:
        # 默认估算，实际应从 MT5 获取
        return lot * 10.0


def retry_on_failure(max_retries: int = 3, delay: float = 1.0):
    """
    重试装饰器
    
    Args:
        max_retries: 最大重试次数
        delay: 重试间隔（秒）
    """
    import time
    from functools import wraps
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            last_exception = None
            
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    retries += 1
                    if retries < max_retries:
                        time.sleep(delay)
            
            raise last_exception
        
        return wrapper
    
    return decorator
