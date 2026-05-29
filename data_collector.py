# 数据采集模块
import os
import time
import csv
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, Any, Optional, List
import MetaTrader5 as mt5
from utils.logger import get_logger
from mt5_interface import MT5Interface


class FeatureExtractor:
    """特征提取器 - 用于AI输入特征采集"""
    
    def __init__(self):
        self.logger = get_logger()
    
    def _convert_to_python_type(self, value):
        """将NumPy类型转换为Python原生类型，以便JSON序列化"""
        if isinstance(value, np.integer):
            return int(value)
        elif isinstance(value, np.floating):
            return float(value)
        elif isinstance(value, np.ndarray):
            return value.tolist()
        elif isinstance(value, np.bool_):
            return bool(value)
        return value
    
    def extract_price_features(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        提取价格相关特征
        
        Args:
            df: K线数据 DataFrame
            
        Returns:
            价格特征字典
        """
        features = {}
        
        if len(df) < 100:
            return features
        
        # 当前价格信息
        last_row = df.iloc[-1]
        features['current_open'] = last_row['open']
        features['current_high'] = last_row['high']
        features['current_low'] = last_row['low']
        features['current_close'] = last_row['close']
        
        # 价格变化
        features['price_change_1'] = df['close'].iloc[-1] - df['close'].iloc[-2] if len(df) >= 2 else 0
        features['price_change_5'] = df['close'].iloc[-1] - df['close'].iloc[-6] if len(df) >= 6 else 0
        features['price_change_10'] = df['close'].iloc[-1] - df['close'].iloc[-11] if len(df) >= 11 else 0
        features['price_change_20'] = df['close'].iloc[-1] - df['close'].iloc[-21] if len(df) >= 21 else 0
        
        # 价格变化百分比
        features['price_pct_change_1'] = (df['close'].iloc[-1] / df['close'].iloc[-2] - 1) * 100 if len(df) >= 2 and df['close'].iloc[-2] != 0 else 0
        features['price_pct_change_5'] = (df['close'].iloc[-1] / df['close'].iloc[-6] - 1) * 100 if len(df) >= 6 and df['close'].iloc[-6] != 0 else 0
        features['price_pct_change_10'] = (df['close'].iloc[-1] / df['close'].iloc[-11] - 1) * 100 if len(df) >= 11 and df['close'].iloc[-11] != 0 else 0
        
        # 价格位置（相对于近期高低点）
        recent_high = df['high'].iloc[-20:].max()
        recent_low = df['low'].iloc[-20:].min()
        price_range = recent_high - recent_low if recent_high != recent_low else 1
        features['price_position_20'] = (df['close'].iloc[-1] - recent_low) / price_range
        
        # 波动率
        returns = df['close'].pct_change().dropna()
        features['volatility_5'] = returns.iloc[-5:].std() * 100 if len(returns) >= 5 else 0
        features['volatility_10'] = returns.iloc[-10:].std() * 100 if len(returns) >= 10 else 0
        features['volatility_20'] = returns.iloc[-20:].std() * 100 if len(returns) >= 20 else 0
        
        # 转换为Python原生类型
        for key in features:
            features[key] = self._convert_to_python_type(features[key])
        
        return features
    
    def extract_volume_features(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        提取成交量相关特征
        
        Args:
            df: K线数据 DataFrame
            
        Returns:
            成交量特征字典
        """
        features = {}
        
        if len(df) < 50:
            return features
        
        if 'tick_volume' not in df.columns and 'volume' not in df.columns:
            return features
        
        volume_col = 'tick_volume' if 'tick_volume' in df.columns else 'volume'
        
        # 当前成交量
        features['current_volume'] = df[volume_col].iloc[-1]
        
        # 成交量变化
        features['volume_change_1'] = df[volume_col].iloc[-1] - df[volume_col].iloc[-2] if len(df) >= 2 else 0
        features['volume_change_5'] = df[volume_col].iloc[-1] - df[volume_col].iloc[-6] if len(df) >= 6 else 0
        
        # 成交量相对于均值
        avg_volume_5 = df[volume_col].iloc[-5:].mean() if len(df) >= 5 else 1
        avg_volume_20 = df[volume_col].iloc[-20:].mean() if len(df) >= 20 else 1
        features['volume_ratio_5'] = df[volume_col].iloc[-1] / avg_volume_5 if avg_volume_5 != 0 else 1
        features['volume_ratio_20'] = df[volume_col].iloc[-1] / avg_volume_20 if avg_volume_20 != 0 else 1
        
        # 成交量趋势
        volume_sma_5 = df[volume_col].rolling(5).mean()
        volume_sma_20 = df[volume_col].rolling(20).mean()
        features['volume_trend_5_20'] = volume_sma_5.iloc[-1] / volume_sma_20.iloc[-1] if volume_sma_20.iloc[-1] != 0 else 1
        
        # 转换为Python原生类型
        for key in features:
            features[key] = self._convert_to_python_type(features[key])
        
        return features
    
    def extract_spread_features(self, current_spread: float, historical_spreads: Optional[List[float]] = None) -> Dict[str, Any]:
        """
        提取价差相关特征
        
        Args:
            current_spread: 当前价差
            historical_spreads: 历史价差列表
            
        Returns:
            价差特征字典
        """
        features = {}
        features['current_spread'] = current_spread
        
        if historical_spreads and len(historical_spreads) > 0:
            features['spread_avg'] = np.mean(historical_spreads)
            features['spread_std'] = np.std(historical_spreads)
            features['spread_ratio'] = current_spread / features['spread_avg'] if features['spread_avg'] != 0 else 1
            features['spread_zscore'] = (current_spread - features['spread_avg']) / features['spread_std'] if features['spread_std'] != 0 else 0
        
        # 转换为Python原生类型
        for key in features:
            features[key] = self._convert_to_python_type(features[key])
        
        return features
    
    def extract_multi_timeframe_features(self, dfs: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """
        提取多周期特征
        
        Args:
            dfs: 多个周期的 K线数据字典 {周期名: DataFrame}
            
        Returns:
            多周期特征字典
        """
        features = {}
        
        # 计算各周期的趋势方向
        for timeframe, df in dfs.items():
            if df is None or len(df) < 20:
                continue
                
            # 短期趋势（基于均线）
            ma5 = df['close'].rolling(5).mean().iloc[-1]
            ma20 = df['close'].rolling(20).mean().iloc[-1]
            features[f'trend_{timeframe}_ma5_ma20'] = 1 if ma5 > ma20 else (-1 if ma5 < ma20 else 0)
            
            # 价格位置
            recent_high = df['high'].iloc[-20:].max()
            recent_low = df['low'].iloc[-20:].min()
            price_range = recent_high - recent_low if recent_high != recent_low else 1
            features[f'price_position_{timeframe}'] = (df['close'].iloc[-1] - recent_low) / price_range
            
            # RSI状态
            if 'rsi_14' in df.columns:
                rsi = df['rsi_14'].iloc[-1]
                features[f'rsi_{timeframe}'] = rsi
                features[f'rsi_overbought_{timeframe}'] = 1 if rsi > 70 else 0
                features[f'rsi_oversold_{timeframe}'] = 1 if rsi < 30 else 0
        
        # 转换为Python原生类型
        for key in features:
            features[key] = self._convert_to_python_type(features[key])
        
        return features


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
        
        # 历史价差记录
        self.historical_spreads = []
        
        # 特征提取器
        self.feature_extractor = FeatureExtractor()
    
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
            'MN1': mt5.TIMEFRAME_MN1,
            '1M': mt5.TIMEFRAME_M1,
            '5M': mt5.TIMEFRAME_M5,
            '15M': mt5.TIMEFRAME_M15,
            '30M': mt5.TIMEFRAME_M30,
            '1H': mt5.TIMEFRAME_H1,
            '4H': mt5.TIMEFRAME_H4
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
        保存数据到文件
        
        Args:
            df: 要保存的数据
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
    
    def get_ai_features(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        获取AI模型所需的完整特征集合
        
        Args:
            symbol: 交易品种，None则使用默认品种
            
        Returns:
            完整的AI特征字典
        """
        if symbol is None:
            symbol = self.symbol
        
        ai_features = {}
        
        try:
            # 1. 获取多周期数据
            multi_timeframe_data = {}
            for interval in self.intervals:
                df = self.collect_data(interval, count=100)
                if df is not None:
                    df = self.calculate_indicators(df)
                    multi_timeframe_data[interval] = df
            
            # 2. 提取特征
            primary_timeframe = self.intervals[0] if self.intervals else 'H1'
            primary_df = multi_timeframe_data.get(primary_timeframe)
            
            if primary_df is not None:
                # 价格特征
                price_features = self.feature_extractor.extract_price_features(primary_df)
                ai_features.update(price_features)
                
                # 成交量特征
                volume_features = self.feature_extractor.extract_volume_features(primary_df)
                ai_features.update(volume_features)
                
                # 多周期特征
                mtf_features = self.feature_extractor.extract_multi_timeframe_features(multi_timeframe_data)
                ai_features.update(mtf_features)
            
            # 3. 提取价差特征
            current_spread = self._get_current_spread(symbol)
            spread_features = self.feature_extractor.extract_spread_features(
                current_spread, 
                self.historical_spreads
            )
            ai_features.update(spread_features)
            
            # 4. 添加技术指标特征
            if primary_df is not None:
                ai_features.update(self._extract_indicator_features(primary_df))
            
            ai_features['timestamp'] = datetime.now().isoformat()
            ai_features['symbol'] = symbol
            
            self.logger.debug(f"AI特征提取完成，共 {len(ai_features)} 个特征")
            
        except Exception as e:
            self.logger.error(f"获取AI特征时出错: {e}")
        
        return ai_features
    
    def _get_current_spread(self, symbol: str) -> float:
        """获取当前价差"""
        try:
            price_info = self.mt5.get_current_price(symbol)
            if price_info:
                bid, ask = price_info
                spread = ask - bid
                
                # 更新历史价差记录
                self.historical_spreads.append(spread)
                if len(self.historical_spreads) > 100:
                    self.historical_spreads.pop(0)
                
                return spread
        except Exception as e:
            self.logger.error(f"获取价差时出错: {e}")
        
        return 0.0
    
    def _extract_indicator_features(self, df: pd.DataFrame) -> Dict[str, Any]:
        """提取技术指标特征"""
        features = {}
        
        if len(df) < 20:
            return features
        
        # 均线特征
        if 'sma_5' in df.columns and 'sma_20' in df.columns:
            features['ma5_above_ma20'] = 1 if df['sma_5'].iloc[-1] > df['sma_20'].iloc[-1] else 0
            features['ma5_ma20_distance'] = (df['sma_5'].iloc[-1] - df['sma_20'].iloc[-1]) / df['sma_20'].iloc[-1] if df['sma_20'].iloc[-1] != 0 else 0
        
        # RSI特征
        if 'rsi_14' in df.columns:
            features['rsi'] = df['rsi_14'].iloc[-1]
            features['rsi_rising'] = 1 if df['rsi_14'].iloc[-1] > df['rsi_14'].iloc[-2] else 0
        
        # MACD特征
        if 'macd' in df.columns and 'macd_signal' in df.columns:
            features['macd_above_signal'] = 1 if df['macd'].iloc[-1] > df['macd_signal'].iloc[-1] else 0
            features['macd'] = df['macd'].iloc[-1]
            features['macd_hist'] = df['macd_hist'].iloc[-1] if 'macd_hist' in df.columns else 0
        
        # 布林带特征
        if 'bb_upper' in df.columns and 'bb_lower' in df.columns and 'bb_middle' in df.columns:
            current_price = df['close'].iloc[-1]
            bb_range = df['bb_upper'].iloc[-1] - df['bb_lower'].iloc[-1]
            if bb_range != 0:
                features['bb_position'] = (current_price - df['bb_lower'].iloc[-1]) / bb_range
            features['price_above_bb_middle'] = 1 if current_price > df['bb_middle'].iloc[-1] else 0
        
        # 转换为Python原生类型
        for key in features:
            value = features[key]
            if isinstance(value, np.integer):
                features[key] = int(value)
            elif isinstance(value, np.floating):
                features[key] = float(value)
            elif isinstance(value, np.ndarray):
                features[key] = value.tolist()
            elif isinstance(value, np.bool_):
                features[key] = bool(value)
        
        return features
    
    def run_collection_loop(self):
        """运行持续采集循环"""
        if not self.enabled:
            self.logger.info("数据采集未启用")
            return
        
        self.logger.info(f"开始数据采集循环，采集间隔: {self.collect_interval}秒")
        
        while self.enabled:
            try:
                self.collect_and_save()
            except Exception as e:
                self.logger.error(f"数据采集循环出错: {e}")
            
            # 等待下一次采集
            time.sleep(self.collect_interval)

