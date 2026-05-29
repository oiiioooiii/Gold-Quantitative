"""
技术指标计算模块
"""
import numpy as np
from typing import List, Dict, Any, Optional


def calculate_sma(data: List[float], period: int) -> List[Optional[float]]:
    """计算简单移动平均线"""
    result = []
    for i in range(len(data)):
        if i < period - 1:
            result.append(None)
        else:
            result.append(np.mean(data[i - period + 1:i + 1]))
    return result


def calculate_ema(data: List[float], period: int) -> List[Optional[float]]:
    """计算指数移动平均线"""
    result = []
    multiplier = 2 / (period + 1)
    
    # 第一个EMA使用SMA
    if len(data) < period:
        return [None] * len(data)
    
    ema = np.mean(data[:period])
    for i in range(len(data)):
        if i < period - 1:
            result.append(None)
        elif i == period - 1:
            result.append(ema)
        else:
            ema = (data[i] - ema) * multiplier + ema
            result.append(ema)
    return result


def calculate_macd(data: List[float], fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> Dict[str, List[Optional[float]]]:
    """计算MACD指标"""
    ema_fast = calculate_ema(data, fast_period)
    ema_slow = calculate_ema(data, slow_period)
    
    macd_line = []
    for fast, slow in zip(ema_fast, ema_slow):
        if fast is not None and slow is not None:
            macd_line.append(fast - slow)
        else:
            macd_line.append(None)
    
    # 计算信号线
    macd_valid = [x for x in macd_line if x is not None]
    signal_line = [None] * (len(macd_line) - len(macd_valid))
    signal_line.extend(calculate_ema(macd_valid, signal_period))
    
    # 计算柱状图
    histogram = []
    for m, s in zip(macd_line, signal_line):
        if m is not None and s is not None:
            histogram.append(m - s)
        else:
            histogram.append(None)
    
    return {
        "macd": macd_line,
        "signal": signal_line,
        "histogram": histogram
    }


def calculate_rsi(data: List[float], period: int = 14) -> List[Optional[float]]:
    """计算RSI指标"""
    if len(data) < period + 1:
        return [None] * len(data)
    
    changes = [data[i] - data[i - 1] for i in range(1, len(data))]
    
    gains = []
    losses = []
    
    for change in changes:
        if change > 0:
            gains.append(change)
            losses.append(0)
        elif change < 0:
            gains.append(0)
            losses.append(-change)
        else:
            gains.append(0)
            losses.append(0)
    
    result = [None]  # 第一个元素None
    
    # 计算初始平均增益和损失
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    
    # 计算初始RSI
    if avg_loss == 0:
        rsi = 100
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
    result.append(rsi)
    
    # 计算后续RSI
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        result.append(rsi)
    
    # 补足长度
    while len(result) < len(data):
        result.append(None)
    
    return result


def calculate_kdj(high: List[float], low: List[float], close: List[float], 
                 n: int = 9, m1: int = 3, m2: int = 3) -> Dict[str, List[Optional[float]]]:
    """计算KDJ指标"""
    k_values = []
    d_values = []
    j_values = []
    
    rsv_list = []
    
    for i in range(len(close)):
        if i < n - 1:
            rsv_list.append(None)
            k_values.append(None)
            d_values.append(None)
            j_values.append(None)
        else:
            # 计算RSV
            high_n = max(high[i - n + 1:i + 1])
            low_n = min(low[i - n + 1:i + 1])
            
            if high_n == low_n:
                rsv = 50
            else:
                rsv = ((close[i] - low_n) / (high_n - low_n)) * 100
            rsv_list.append(rsv)
            
            # 计算K和D
            if i == n - 1:
                k = 50
                d = 50
            else:
                prev_k = k_values[i - 1] or 50
                prev_d = d_values[i - 1] or 50
                k = (prev_k * (m1 - 1) + rsv) / m1
                d = (prev_d * (m2 - 1) + k) / m2
            
            k_values.append(k)
            d_values.append(d)
            j_values.append(3 * k - 2 * d)
    
    return {
        "k": k_values,
        "d": d_values,
        "j": j_values
    }


def calculate_bollinger_bands(data: List[float], period: int = 20, std_dev: float = 2) -> Dict[str, List[Optional[float]]]:
    """计算布林带"""
    middle = calculate_sma(data, period)
    
    upper = []
    lower = []
    
    for i in range(len(data)):
        if i < period - 1:
            upper.append(None)
            lower.append(None)
        else:
            slice_data = data[i - period + 1:i + 1]
            std = np.std(slice_data)
            upper.append(middle[i] + std_dev * std)
            lower.append(middle[i] - std_dev * std)
    
    return {
        "middle": middle,
        "upper": upper,
        "lower": lower
    }
