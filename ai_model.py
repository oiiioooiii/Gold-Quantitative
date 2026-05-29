# AI 模型接口模块
import os
import pickle
import json
import numpy as np
import requests
import time
from typing import Dict, Any, Optional, List, Tuple
from abc import ABC, abstractmethod
from enum import Enum
from utils.logger import get_logger


class SignalType(Enum):
    """信号类型"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    CLOSE = "close"


class SignalStrength(Enum):
    """信号强度"""
    VERY_WEAK = 1
    WEAK = 2
    MODERATE = 3
    STRONG = 4
    VERY_STRONG = 5


class TradingSignal:
    """交易信号"""
    
    def __init__(
        self,
        signal_type: SignalType,
        strength: SignalStrength = SignalStrength.MODERATE,
        confidence: float = 0.5,
        reason: str = "",
        source: str = ""
    ):
        self.signal_type = signal_type
        self.strength = strength
        self.confidence = confidence
        self.reason = reason
        self.source = source
        self.timestamp = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_type": self.signal_type.value,
            "strength": self.strength.value,
            "confidence": self.confidence,
            "reason": self.reason,
            "source": self.source,
            "timestamp": self.timestamp
        }


class BaseAIModel(ABC):
    """AI 模型基类"""
    
    @abstractmethod
    def predict(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """
        使用模型进行预测
        
        Args:
            features: 特征字典
            
        Returns:
            预测结果字典
        """
        pass
    
    @abstractmethod
    def load_model(self, model_path: str) -> bool:
        """
        加载模型
        
        Args:
            model_path: 模型文件路径
            
        Returns:
            是否加载成功
        """
        pass
    
    @abstractmethod
    def generate_signal(self, features: Dict[str, Any]) -> Optional[TradingSignal]:
        """
        生成交易信号
        
        Args:
            features: 特征字典
            
        Returns:
            交易信号对象
        """
        pass


class TradingViewAIAnalyzer(BaseAIModel):
    """TradingView AI指标分析器"""
    
    def __init__(self):
        self.logger = get_logger()
        self.enabled = True
        self.config = {
            "rsi_period": 14,
            "rsi_oversold": 30,
            "rsi_overbought": 70,
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            "bb_period": 20,
            "bb_std": 2.0
        }
        self.indicator_weights = {
            "rsi": 0.2,
            "macd": 0.25,
            "ma_crossover": 0.2,
            "bbands": 0.15,
            "volume": 0.1,
            "multi_timeframe": 0.1
        }
    
    def update_config(self, config: Dict[str, Any]):
        """更新配置"""
        self.enabled = config.get('enabled', True)
        for key in ["rsi_period", "rsi_oversold", "rsi_overbought",
                   "macd_fast", "macd_slow", "macd_signal",
                   "bb_period", "bb_std"]:
            if key in config:
                self.config[key] = config[key]
        self.logger.info(f"TradingView AI配置已更新: {self.config}")
    
    def load_model(self, model_path: str) -> bool:
        """加载配置文件"""
        try:
            if os.path.exists(model_path):
                with open(model_path, 'r') as f:
                    config = json.load(f)
                    if 'indicator_weights' in config:
                        self.indicator_weights.update(config['indicator_weights'])
                self.logger.info(f"TradingView AI配置加载成功: {model_path}")
            return True
        except Exception as e:
            self.logger.error(f"加载TradingView配置时出错: {e}")
            return False
    
    def predict(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """预测 - 返回综合评分"""
        signal = self.generate_signal(features)
        if signal:
            return {
                "signal_type": signal.signal_type.value,
                "confidence": signal.confidence,
                "strength": signal.strength.value
            }
        return {}
    
    def generate_signal(self, features: Dict[str, Any]) -> Optional[TradingSignal]:
        """
        基于TradingView风格技术指标生成信号
        
        Args:
            features: 特征字典
            
        Returns:
            交易信号
        """
        buy_score = 0.0
        sell_score = 0.0
        reasons = []
        
        # 1. RSI分析
        rsi_signal, rsi_confidence = self._analyze_rsi(features)
        if rsi_signal == SignalType.BUY:
            buy_score += self.indicator_weights["rsi"] * rsi_confidence
            reasons.append(f"RSI超卖({features.get('rsi', 0):.1f})")
        elif rsi_signal == SignalType.SELL:
            sell_score += self.indicator_weights["rsi"] * rsi_confidence
            reasons.append(f"RSI超买({features.get('rsi', 0):.1f})")
        
        # 2. MACD分析
        macd_signal, macd_confidence = self._analyze_macd(features)
        if macd_signal == SignalType.BUY:
            buy_score += self.indicator_weights["macd"] * macd_confidence
            reasons.append("MACD金叉")
        elif macd_signal == SignalType.SELL:
            sell_score += self.indicator_weights["macd"] * macd_confidence
            reasons.append("MACD死叉")
        
        # 3. 均线交叉分析
        ma_signal, ma_confidence = self._analyze_ma(features)
        if ma_signal == SignalType.BUY:
            buy_score += self.indicator_weights["ma_crossover"] * ma_confidence
            reasons.append("均线多头排列")
        elif ma_signal == SignalType.SELL:
            sell_score += self.indicator_weights["ma_crossover"] * ma_confidence
            reasons.append("均线空头排列")
        
        # 4. 布林带分析
        bb_signal, bb_confidence = self._analyze_bbands(features)
        if bb_signal == SignalType.BUY:
            buy_score += self.indicator_weights["bbands"] * bb_confidence
            reasons.append("价格触及布林带下轨")
        elif bb_signal == SignalType.SELL:
            sell_score += self.indicator_weights["bbands"] * bb_confidence
            reasons.append("价格触及布林带上轨")
        
        # 5. 成交量分析
        volume_signal, volume_confidence = self._analyze_volume(features)
        if volume_signal == SignalType.BUY:
            buy_score += self.indicator_weights["volume"] * volume_confidence
            reasons.append("放量上涨")
        elif volume_signal == SignalType.SELL:
            sell_score += self.indicator_weights["volume"] * volume_confidence
            reasons.append("放量下跌")
        
        # 6. 多周期分析
        mtf_signal, mtf_confidence = self._analyze_multi_timeframe(features)
        if mtf_signal == SignalType.BUY:
            buy_score += self.indicator_weights["multi_timeframe"] * mtf_confidence
            reasons.append("多周期共振上涨")
        elif mtf_signal == SignalType.SELL:
            sell_score += self.indicator_weights["multi_timeframe"] * mtf_confidence
            reasons.append("多周期共振下跌")
        
        # 确定最终信号
        threshold = 0.3
        if buy_score > sell_score + threshold:
            signal_type = SignalType.BUY
            confidence = min(buy_score, 1.0)
        elif sell_score > buy_score + threshold:
            signal_type = SignalType.SELL
            confidence = min(sell_score, 1.0)
        else:
            signal_type = SignalType.HOLD
            confidence = max(1 - abs(buy_score - sell_score), 0.3)
        
        # 确定信号强度
        strength = self._calculate_strength(confidence)
        
        return TradingSignal(
            signal_type=signal_type,
            strength=strength,
            confidence=confidence,
            reason=" | ".join(reasons) if reasons else "市场震荡，建议观望",
            source="TradingView AI"
        )
    
    def _analyze_rsi(self, features: Dict[str, Any]) -> Tuple[Optional[SignalType], float]:
        """分析RSI指标"""
        rsi = features.get('rsi', 50)
        rsi_rising = features.get('rsi_rising', 0)
        
        if rsi < 30:
            confidence = (30 - rsi) / 30
            return SignalType.BUY, confidence if rsi_rising else confidence * 0.7
        elif rsi > 70:
            confidence = (rsi - 70) / 30
            return SignalType.SELL, confidence if not rsi_rising else confidence * 0.7
        return None, 0
    
    def _analyze_macd(self, features: Dict[str, Any]) -> Tuple[Optional[SignalType], float]:
        """分析MACD指标"""
        macd_above_signal = features.get('macd_above_signal', 0)
        macd_hist = features.get('macd_hist', 0)
        
        if macd_above_signal and macd_hist > 0:
            confidence = min(abs(macd_hist) * 10, 1.0)
            return SignalType.BUY, confidence
        elif not macd_above_signal and macd_hist < 0:
            confidence = min(abs(macd_hist) * 10, 1.0)
            return SignalType.SELL, confidence
        return None, 0
    
    def _analyze_ma(self, features: Dict[str, Any]) -> Tuple[Optional[SignalType], float]:
        """分析均线"""
        ma5_above_ma20 = features.get('ma5_above_ma20', 0)
        ma_distance = features.get('ma5_ma20_distance', 0)
        
        if ma5_above_ma20:
            confidence = min(abs(ma_distance) * 100, 1.0)
            return SignalType.BUY, confidence
        elif not ma5_above_ma20:
            confidence = min(abs(ma_distance) * 100, 1.0)
            return SignalType.SELL, confidence
        return None, 0
    
    def _analyze_bbands(self, features: Dict[str, Any]) -> Tuple[Optional[SignalType], float]:
        """分析布林带"""
        bb_position = features.get('bb_position', 0.5)
        
        if bb_position < 0.1:
            confidence = (0.1 - bb_position) / 0.1
            return SignalType.BUY, confidence
        elif bb_position > 0.9:
            confidence = (bb_position - 0.9) / 0.1
            return SignalType.SELL, confidence
        return None, 0
    
    def _analyze_volume(self, features: Dict[str, Any]) -> Tuple[Optional[SignalType], float]:
        """分析成交量"""
        volume_ratio = features.get('volume_ratio_20', 1.0)
        price_change = features.get('price_change_1', 0)
        
        if volume_ratio > 1.5:
            if price_change > 0:
                confidence = min((volume_ratio - 1.0) * 2, 1.0)
                return SignalType.BUY, confidence
            elif price_change < 0:
                confidence = min((volume_ratio - 1.0) * 2, 1.0)
                return SignalType.SELL, confidence
        return None, 0
    
    def _analyze_multi_timeframe(self, features: Dict[str, Any]) -> Tuple[Optional[SignalType], float]:
        """分析多周期"""
        buy_count = 0
        sell_count = 0
        
        for key, value in features.items():
            if key.startswith('trend_'):
                if value == 1:
                    buy_count += 1
                elif value == -1:
                    sell_count += 1
        
        total = buy_count + sell_count
        if total >= 2:
            if buy_count >= total * 0.7:
                return SignalType.BUY, buy_count / total
            elif sell_count >= total * 0.7:
                return SignalType.SELL, sell_count / total
        return None, 0
    
    def _calculate_strength(self, confidence: float) -> SignalStrength:
        """根据置信度计算信号强度"""
        if confidence >= 0.9:
            return SignalStrength.VERY_STRONG
        elif confidence >= 0.7:
            return SignalStrength.STRONG
        elif confidence >= 0.5:
            return SignalStrength.MODERATE
        elif confidence >= 0.3:
            return SignalStrength.WEAK
        else:
            return SignalStrength.VERY_WEAK


class PyTorchAIModel(BaseAIModel):
    """PyTorch AI模型"""
    
    def __init__(self):
        self.logger = get_logger()
        self.model = None
        self.device = 'cpu'
        self.feature_scaler = None
        self.enabled = False
    
    def load_model(self, model_path: str) -> bool:
        """加载PyTorch模型"""
        try:
            import torch
            # 尝试导入PyTorch
            self.logger.info(f"尝试加载PyTorch模型: {model_path}")
            
            if not os.path.exists(model_path):
                self.logger.warning(f"PyTorch模型文件不存在: {model_path}")
                return False
            
            # 这里实现实际的模型加载逻辑
            # checkpoint = torch.load(model_path, map_location=self.device)
            # self.model = checkpoint.get('model')
            # self.feature_scaler = checkpoint.get('scaler')
            
            self.enabled = True
            self.logger.info("PyTorch AI模型加载成功（模拟）")
            return True
        except ImportError:
            self.logger.warning("PyTorch未安装，使用备用模式")
            return False
        except Exception as e:
            self.logger.error(f"加载PyTorch模型时出错: {e}")
            return False
    
    def predict(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """PyTorch模型预测"""
        if not self.enabled or self.model is None:
            return self._fallback_predict(features)
        
        # 这里实现实际的模型预测
        return self._fallback_predict(features)
    
    def generate_signal(self, features: Dict[str, Any]) -> Optional[TradingSignal]:
        """生成交易信号"""
        if not self.enabled:
            return None
        
        prediction = self.predict(features)
        signal_type = SignalType.HOLD
        
        if prediction.get('buy_probability', 0) > 0.6:
            signal_type = SignalType.BUY
        elif prediction.get('sell_probability', 0) > 0.6:
            signal_type = SignalType.SELL
        
        return TradingSignal(
            signal_type=signal_type,
            confidence=prediction.get('confidence', 0.5),
            reason="PyTorch深度模型预测",
            source="PyTorch AI"
        )
    
    def _fallback_predict(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """备用预测逻辑"""
        return {
            "buy_probability": 0.5,
            "sell_probability": 0.5,
            "confidence": 0.5
        }


class TensorFlowAIModel(BaseAIModel):
    """TensorFlow AI模型"""
    
    def __init__(self):
        self.logger = get_logger()
        self.model = None
        self.enabled = False
    
    def load_model(self, model_path: str) -> bool:
        """加载TensorFlow模型"""
        try:
            import tensorflow as tf
            self.logger.info(f"尝试加载TensorFlow模型: {model_path}")
            
            if not os.path.exists(model_path):
                self.logger.warning(f"TensorFlow模型文件不存在: {model_path}")
                return False
            
            # 这里实现实际的模型加载
            # self.model = tf.keras.models.load_model(model_path)
            
            self.enabled = True
            self.logger.info("TensorFlow AI模型加载成功（模拟）")
            return True
        except ImportError:
            self.logger.warning("TensorFlow未安装，使用备用模式")
            return False
        except Exception as e:
            self.logger.error(f"加载TensorFlow模型时出错: {e}")
            return False
    
    def predict(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """TensorFlow模型预测"""
        if not self.enabled or self.model is None:
            return self._fallback_predict(features)
        
        return self._fallback_predict(features)
    
    def generate_signal(self, features: Dict[str, Any]) -> Optional[TradingSignal]:
        """生成交易信号"""
        if not self.enabled:
            return None
        
        prediction = self.predict(features)
        return TradingSignal(
            signal_type=SignalType.HOLD,
            confidence=0.5,
            reason="TensorFlow模型预测",
            source="TensorFlow AI"
        )
    
    def _fallback_predict(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """备用预测逻辑"""
        return {
            "prediction": 0,
            "confidence": 0.5
        }


class AIModelManager:
    """AI 模型管理器"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化 AI 模型管理器
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.logger = get_logger()
        self.ai_config = config.get('ai', {})
        self.enabled = self.ai_config.get('enabled', False)
        
        # 初始化各个AI模型
        self.models = {}
        self.active_models = []
        
        if self.enabled:
            self._initialize_models()
    
    def _initialize_models(self):
        """初始化所有AI模型"""
        # 1. TradingView AI（始终启用）
        tv_config = self.ai_config.get('tv_analyzer', {})
        if tv_config.get('enabled', True):
            tv_model = TradingViewAIAnalyzer()
            tv_model.update_config(tv_config)
            self.models['tradingview'] = tv_model
            self.active_models.append('tradingview')
            self.logger.info("TradingView AI初始化成功")
        
        # 2. LLM AI
        llm_config = self.ai_config.get('llm', {})
        if llm_config.get('enabled', False) and llm_config.get('api_key'):
            llm_model = LLMAIAnalyzer()
            llm_model.update_config(llm_config)
            self.models['llm'] = llm_model
            self.active_models.append('llm')
            self.logger.info("LLM AI初始化成功")
        
        # 3. PyTorch模型
        pytorch_config = self.ai_config.get('deep_learning', {}).get('pytorch', {})
        if pytorch_config.get('enabled', False):
            pytorch_model = PyTorchAIModel()
            model_path = self.ai_config.get('model_path', '')
            if pytorch_model.load_model(model_path):
                self.models['pytorch'] = pytorch_model
                self.active_models.append('pytorch')
                self.logger.info("PyTorch AI初始化成功")
        
        # 4. TensorFlow模型
        tf_config = self.ai_config.get('deep_learning', {}).get('tensorflow', {})
        if tf_config.get('enabled', False):
            tf_model = TensorFlowAIModel()
            model_path = self.ai_config.get('model_path', '')
            if tf_model.load_model(model_path):
                self.models['tensorflow'] = tf_model
                self.active_models.append('tensorflow')
                self.logger.info("TensorFlow AI初始化成功")
        
        self.logger.info(f"已激活的AI模型: {self.active_models}")
    
    def predict(self, features: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        使用所有激活的模型进行预测
        
        Args:
            features: 特征字典
            
        Returns:
            综合预测结果
        """
        if not self.enabled or len(self.active_models) == 0:
            return None
        
        results = {}
        for model_name in self.active_models:
            model = self.models.get(model_name)
            if model:
                try:
                    results[model_name] = model.predict(features)
                except Exception as e:
                    self.logger.error(f"{model_name}预测时出错: {e}")
        
        return results
    
    def generate_signals(self, features: Dict[str, Any]) -> List[TradingSignal]:
        """
        生成所有激活模型的交易信号
        
        Args:
            features: 特征字典
            
        Returns:
            交易信号列表
        """
        signals = []
        
        if not self.enabled:
            return signals
        
        for model_name in self.active_models:
            model = self.models.get(model_name)
            if model:
                try:
                    signal = model.generate_signal(features)
                    if signal:
                        signals.append(signal)
                except Exception as e:
                    self.logger.error(f"{model_name}生成信号时出错: {e}")
        
        return signals
    
    def get_combined_signal(self, features: Dict[str, Any]) -> Optional[TradingSignal]:
        """
        获取综合交易信号
        
        Args:
            features: 特征字典
            
        Returns:
            综合交易信号
        """
        signals = self.generate_signals(features)
        
        if not signals:
            return None
        
        # 统计各信号
        buy_signals = [s for s in signals if s.signal_type == SignalType.BUY]
        sell_signals = [s for s in signals if s.signal_type == SignalType.SELL]
        
        buy_score = sum(s.confidence * s.strength.value for s in buy_signals)
        sell_score = sum(s.confidence * s.strength.value for s in sell_signals)
        
        if buy_score > sell_score and buy_score > 0:
            signal_type = SignalType.BUY
            confidence = buy_score / max((buy_score + sell_score), 1)
            reasons = [s.reason for s in buy_signals]
        elif sell_score > buy_score and sell_score > 0:
            signal_type = SignalType.SELL
            confidence = sell_score / max((buy_score + sell_score), 1)
            reasons = [s.reason for s in sell_signals]
        else:
            signal_type = SignalType.HOLD
            confidence = 0.5
            reasons = ["信号分歧，建议观望"]
        
        # 计算综合强度
        avg_strength = np.mean([s.strength.value for s in signals])
        strength_value = min(max(round(avg_strength), 1), 5)
        strength = SignalStrength(strength_value)
        
        combined_signal = TradingSignal(
            signal_type=signal_type,
            strength=strength,
            confidence=confidence,
            reason=" | ".join(reasons[:3]),
            source=f"AI综合({len(signals)}个模型)"
        )
        
        return combined_signal
    
    def adjust_risk_params(
        self,
        features: Dict[str, Any],
        base_lot: float,
        base_sl_points: float,
        base_tp_points: float
    ) -> Dict[str, Any]:
        """
        使用 AI 调整风险参数
        
        Args:
            features: 特征字典
            base_lot: 基础手数
            base_sl_points: 基础止损点数
            base_tp_points: 基础止盈点数
            
        Returns:
            调整后的参数字典
        """
        combined_signal = self.get_combined_signal(features)
        
        if combined_signal is None:
            return {
                "lot": base_lot,
                "sl_points": base_sl_points,
                "tp_points": base_tp_points,
                "allow_trade": True
            }
        
        # 根据信号强度调整仓位
        strength_multiplier = {
            SignalStrength.VERY_WEAK: 0.3,
            SignalStrength.WEAK: 0.5,
            SignalStrength.MODERATE: 1.0,
            SignalStrength.STRONG: 1.2,
            SignalStrength.VERY_STRONG: 1.5
        }
        
        lot_multiplier = strength_multiplier.get(combined_signal.strength, 1.0)
        
        # 根据市场波动率动态调整止损止盈
        volatility = features.get('volatility_20', 0.5)
        volatility_adjust = 1.0 + (volatility - 0.5) * 0.5
        
        # 只有当信号足够强时才允许交易
        allow_trade = combined_signal.confidence >= 0.5 and combined_signal.strength.value >= 3
        
        adjusted_params = {
            "lot": base_lot * lot_multiplier * combined_signal.confidence,
            "sl_points": max(20, int(base_sl_points * volatility_adjust)),
            "tp_points": int(base_tp_points * volatility_adjust),
            "allow_trade": allow_trade,
            "recommended_action": combined_signal.signal_type.value
        }
        
        self.logger.info(f"AI 动态风控参数: {adjusted_params}")
        return adjusted_params
    
    def update_config(self, new_config: Dict[str, Any]):
        """
        更新 AI 模型管理器的配置
        
        Args:
            new_config: 新的配置字典
        """
        self.config['ai'] = new_config
        self.ai_config = new_config
        self.enabled = new_config.get('enabled', False)
        
        # 更新 TradingView AI 配置
        tv_config = new_config.get('tv_analyzer', {})
        if 'tradingview' in self.models and hasattr(self.models['tradingview'], 'update_config'):
            self.models['tradingview'].update_config(tv_config)
        
        # 更新 LLM AI 配置
        llm_config = new_config.get('llm', {})
        if 'llm' in self.models and hasattr(self.models['llm'], 'update_config'):
            self.models['llm'].update_config(llm_config)
        
        self.logger.info(f"AI 模型管理器配置已更新: enabled={self.enabled}")


class LLMAIAnalyzer(BaseAIModel):
    """大语言模型 AI 分析器"""
    
    def __init__(self):
        self.logger = get_logger()
        self.enabled = False
        self.config = {
            "provider": "openai",
            "api_key": "",
            "model": "gpt-4",
            "base_url": "",
            "timeout": 30,
            "max_tokens": 1000,
            "temperature": 0.7
        }
        self.use_for = {
            "signal_analysis": False,
            "market_analysis": False,
            "auto_trade": False
        }
    
    def update_config(self, config: Dict[str, Any]):
        """更新配置"""
        self.enabled = config.get('enabled', False)
        for key in ["provider", "api_key", "model", "base_url", "timeout", "max_tokens", "temperature"]:
            if key in config:
                self.config[key] = config[key]
        if 'use_for' in config:
            self.use_for.update(config['use_for'])
        self.logger.info(f"LLM AI配置已更新: enabled={self.enabled}, provider={self.config['provider']}")
    
    def load_model(self, model_path: str) -> bool:
        """加载配置（LLM不需要文件）"""
        return True
    
    def predict(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """LLM 预测（返回分析结果）"""
        if not self.enabled or not self.config.get('api_key'):
            return {}
        
        try:
            analysis = self._call_llm_api(features)
            return {
                "analysis": analysis,
                "llm_used": True,
                "provider": self.config['provider']
            }
        except Exception as e:
            self.logger.error(f"LLM 分析失败: {e}")
            return {
                "analysis": "LLM 分析暂不可用",
                "llm_used": False,
                "error": str(e)
            }
    
    def generate_signal(self, features: Dict[str, Any]) -> Optional[TradingSignal]:
        """
        基于 LLM 生成交易信号
        
        Args:
            features: 特征字典
            
        Returns:
            交易信号
        """
        if not self.enabled or not self.config.get('api_key'):
            return None
        
        try:
            analysis = self._call_llm_api(features, for_signal=True)
            
            # 解析 LLM 返回的信号
            signal_type = SignalType.HOLD
            confidence = 0.5
            reason = analysis
            
            if "买入" in analysis or "做多" in analysis or "BUY" in analysis.upper():
                signal_type = SignalType.BUY
                confidence = min(0.8, 0.5 + analysis.count("买入") * 0.1)
            elif "卖出" in analysis or "做空" in analysis or "SELL" in analysis.upper():
                signal_type = SignalType.SELL
                confidence = min(0.8, 0.5 + analysis.count("卖出") * 0.1)
            
            # 计算信号强度
            strength = self._calculate_strength(confidence)
            
            return TradingSignal(
                signal_type=signal_type,
                strength=strength,
                confidence=confidence,
                reason=reason,
                source=f"LLM({self.config['provider']})"
            )
            
        except Exception as e:
            self.logger.error(f"LLM 生成信号失败: {e}")
            return None
    
    def _call_llm_api(self, features: Dict[str, Any], for_signal: bool = False) -> str:
        """
        调用 LLM API
        
        Args:
            features: 特征字典
            for_signal: 是否为生成信号调用
            
        Returns:
            LLM 分析文本
        """
        api_key = self.config.get('api_key', '')
        if not api_key:
            raise Exception("API Key 未配置")
        
        # 构建提示词
        prompt = self._build_prompt(features, for_signal)
        
        # 根据提供商调用不同的 API
        provider = self.config.get('provider', 'openai')
        
        try:
            if provider in ['openai', 'deepseek', 'siliconflow', 'tongyi', 'custom']:
                return self._call_openai_compatible_api(prompt)
            elif provider == 'anthropic':
                return self._call_anthropic_api(prompt)
            else:
                return f"不支持的提供商: {provider}"
        except Exception as e:
            self.logger.error(f"调用 {provider} API 失败: {e}")
            raise
    
    def _build_prompt(self, features: Dict[str, Any], for_signal: bool) -> str:
        """构建提示词"""
        # 简化特征，避免过长
        simple_features = {
            "当前价格": features.get('current_close', 0),
            "RSI": features.get('rsi', 50),
            "20日波动率": features.get('volatility_20', 0),
            "价格位置": features.get('price_position_20', 0.5),
            "均线状态": "多头" if features.get('ma5_above_ma20', 0) == 1 else "空头",
            "MACD": "金叉" if features.get('macd_above_signal', 0) == 1 else "死叉"
        }
        
        if for_signal:
            return f"""你是一个专业的黄金交易分析师。请根据以下技术指标分析当前的市场情况，并给出明确的交易建议：

市场数据:
{json.dumps(simple_features, ensure_ascii=False, indent=2)}

请给出：
1. 对当前市场的分析
2. 明确的交易建议（买入/卖出/观望）
3. 简单的理由说明

回答格式请简洁明了，不要超过300字。"""
        else:
            return f"""请分析以下黄金交易市场的技术指标，并给出你的见解：

市场数据:
{json.dumps(simple_features, ensure_ascii=False, indent=2)}

请提供：
1. 对当前价格走势的判断
2. 市场风险评估
3. 对交易的建议

回答要求专业、简洁，不超过400字。"""
    
    def _call_openai_compatible_api(self, prompt: str) -> str:
        """调用 OpenAI 兼容的 API"""
        base_url = self.config.get('base_url', '')
        
        # 根据提供商设置默认的 base_url
        if not base_url:
            if self.config['provider'] == 'openai':
                base_url = 'https://api.openai.com/v1'
            elif self.config['provider'] == 'deepseek':
                base_url = 'https://api.deepseek.com/v1'
            elif self.config['provider'] == 'siliconflow':
                base_url = 'https://api.siliconflow.cn/v1'
            elif self.config['provider'] == 'tongyi':
                base_url = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.config["api_key"]}'
        }
        
        data = {
            'model': self.config['model'],
            'messages': [
                {'role': 'system', 'content': '你是一个专业的黄金交易分析师。'},
                {'role': 'user', 'content': prompt}
            ],
            'temperature': self.config.get('temperature', 0.7),
            'max_tokens': self.config.get('max_tokens', 1000),
            'timeout': self.config.get('timeout', 30)
        }
        
        self.logger.info(f"调用 {self.config['provider']} API: {base_url}")
        
        response = requests.post(
            f'{base_url}/chat/completions',
            headers=headers,
            json=data,
            timeout=self.config.get('timeout', 30)
        )
        
        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content']
        else:
            raise Exception(f"API 请求失败: {response.status_code} - {response.text}")
    
    def _call_anthropic_api(self, prompt: str) -> str:
        """调用 Anthropic API"""
        base_url = self.config.get('base_url', 'https://api.anthropic.com/v1')
        
        headers = {
            'Content-Type': 'application/json',
            'x-api-key': self.config['api_key'],
            'anthropic-version': '2023-06-01'
        }
        
        data = {
            'model': self.config['model'],
            'messages': [
                {'role': 'user', 'content': prompt}
            ],
            'temperature': self.config.get('temperature', 0.7),
            'max_tokens': self.config.get('max_tokens', 1000)
        }
        
        response = requests.post(
            f'{base_url}/messages',
            headers=headers,
            json=data,
            timeout=self.config.get('timeout', 30)
        )
        
        if response.status_code == 200:
            result = response.json()
            return result['content'][0]['text']
        else:
            raise Exception(f"API 请求失败: {response.status_code} - {response.text}")
    
    def _calculate_strength(self, confidence: float) -> SignalStrength:
        """根据置信度计算信号强度"""
        if confidence >= 0.9:
            return SignalStrength.VERY_STRONG
        elif confidence >= 0.7:
            return SignalStrength.STRONG
        elif confidence >= 0.5:
            return SignalStrength.MODERATE
        elif confidence >= 0.3:
            return SignalStrength.WEAK
        else:
            return SignalStrength.VERY_WEAK
