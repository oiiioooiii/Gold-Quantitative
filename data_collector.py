# 数据采集模块
import os
import time
import csv
import pandas as pd
from datetime import datetime
from typing import Dict, Any, Optional, List
import MetaTrader5 as mt5
from utils.logger import get_logger
from mt5_interface import MT5Interface


class DataCollector:
    """数据采集器"""
    
    def __init__(self, config: Dict[str, Any], mt5_interface: MT5Interface):
        """
        初始化数据采集器
        
        Args:
            config: 配置字典
            mt5_interface: MT5 接口实例
        """
        self.config = config
        self.mt5 = mt5_interface
        self.logger = get_logger()
        self.data_config = config.get('data_collection', {})
        self.trading_config = config.get('trading', {})
        
        self.enabled = self.data_config.get('enabled', False)
        self.save_path = self.data_config.get('save_path', './data')
        self.intervals = self.data_config.get('intervals', ['1H', '4H', 'D1'])
        self.collect_interval = self.data_config.get('collect_interval', 3600)  # 默认 1 小时
        self.symbol = self.trading_config.get('symbol', 'XAUUSD')
        
        # 创建数据保存目录
        if self.enabled and not os.path.exists(self.save_path):
            os.makedirs(self.save_path, exist_ok=True)
    
    def _get_timeframe_constant(self, interval: str) -> Optional[int]:
        """
        将时间周期字符串转换为 MT5 常量
        
        Args:
            interval: 时间周期字符串，如 '1H', '4H', 'D1'
            
        Returns:
            MT5 时间周期常量
        """
        timeframe_map = {
            'M1': mt5.TIMEFRAME_M1,
            'M5': mt5.TIMEFRAME_M5,
            'M15': mt5.TIMEFRAME_M15,
            'M30': mt5.TIMEFRAME_M30,
            'H1': mt5.TIMEFRAME_H1,
            'H4': mt5.TIMEFRAME_H4,
            'D1': mt5.TIMEFRAME_D1,
            'W1': mt5.TIMEFRAME_W1,
            'MN1': mt5.TIMEFRAME_MN1
        }
        return timeframe_map.get(interval)
    
    def collect_data(self, interval: str, count: int = 500) -> Optional[pd.DataFrame]:
        """
        采集指定周期的数据
        
        Args:
            interval: 时间周期
            count: 采集的 K 线数量
            
        Returns:
            DataFrame 格式的数据，失败返回 None
        """
        if not self.enabled:
            return None
        
        timeframe = self._get_timeframe_constant(interval)
        if timeframe is None:
            self.logger.error(f"未知的时间周期: {interval}")
            return None
        
        # 获取 K 线数据
        rates = self.mt5.get_candles(self.symbol, timeframe, count)
        if rates is None:
            return None
        
        # 转换为 DataFrame
        df = pd.DataFrame(rates)
        
        # 转换时间戳
        df['time'] = pd.to_datetime(df['time'], unit='s')
        
        # 添加采集时间
        df['collect_time'] = datetime.now()
        
        return df
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        计算技术指标
        
        Args:
            df: 原始 K 线数据
            
        Returns:
            添加了技术指标的数据
        """
        if df is None or len(df) < 20:
            return df
        
        df = df.copy()
        
        # 简单移动平均线
        df['sma_5'] = df['close'].rolling(window=5).mean()
        df['sma_10'] = df['close'].rolling(window=10).mean()
        df['sma_20'] = df['close'].rolling(window=20).mean()
        df['sma_50'] = df['close'].rolling(window=50).mean()
        
        # 指数移动平均线
        df['ema_5'] = df['close'].ewm(span=5, adjust=False).mean()
        df['ema_10'] = df['close'].ewm(span=10, adjust=False).mean()
        df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
        
        # RSI (Relative Strength Index)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi_14'] = 100 - (100 / (1 + rs))
        
        # MACD
        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = exp1 - exp2
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        
        # 布林带
        df['bb_middle'] = df['close'].rolling(window=20).mean()
        bb_std = df['close'].rolling(window=20).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
        df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
        
        # 波动率
        df['returns'] = df['close'].pct_change()
        df['volatility_20'] = df['returns'].rolling(window=20).std()
        
        return df
    
    def save_data(self, df: pd.DataFrame, interval: str):
        """
        保存数据到 CSV 文件
        
        Args:
            df: 数据 DataFrame
            interval: 时间周期
        """
        if df is None or len(df) == 0:
            return
        
        filename = f"{self.symbol}_{interval}_{datetime.now().strftime('%Y%m%d')}.csv"
        filepath = os.path.join(self.save_path, filename)
        
        # 如果文件已存在，追加数据
        if os.path.exists(filepath):
            existing_df = pd.read_csv(filepath)
            # 去重
            combined_df = pd.concat([existing_df, df])
            combined_df = combined_df.drop_duplicates(subset=['time'], keep='last')
            combined_df.to_csv(filepath, index=False)
        else:
            df.to_csv(filepath, index=False)
        
        self.logger.info(f"数据已保存: {filepath}")
    
    def collect_and_save(self, count: int = 500):
        """
        采集并保存所有周期的数据
        
        Args:
            count: 每个周期采集的 K 线数量
        """
        if not self.enabled:
            return
        
        for interval in self.intervals:
            try:
                self.logger.info(f"开始采集 {interval} 周期数据...")
                
                # 采集数据
                df = self.collect_data(interval, count)
                if df is None:
                    continue
                
                # 计算指标
                df = self.calculate_indicators(df)
                
                # 保存数据
                self.save_data(df, interval)
                
                self.logger.info(f"{interval} 周期数据采集完成")
                
            except Exception as e:
                self.logger.error(f"采集 {interval} 周期数据时出错: {e}")
    
    def run_collection_loop(self):
        """运行持续采集循环"""
        if not self.enabled:
            self.logger.info("数据采集功能未启用")
            return
        
        self.logger.info(f"数据采集循环已启动，采集间隔: {self.collect_interval} 秒")
        
        try:
            while True:
                self.collect_and_save()
                time.sleep(self.collect_interval)
        except KeyboardInterrupt:
            self.logger.info("数据采集循环已停止")
        except Exception as e:
            self.logger.error(f"数据采集循环出错: {e}")
