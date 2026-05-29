# 风控管理模块
import MetaTrader5 as mt5
import numpy as np
from typing import Optional, Tuple, Dict, Any, List
from datetime import datetime, timedelta
from utils.logger import get_logger
from utils.helpers import calculate_pip_value


class MarketRegime:
    """市场状态分析器"""
    
    def __init__(self):
        self.logger = get_logger()
        self.volatility_history = []
        self.trend_strength_history = []
    
    def analyze_market_condition(
        self,
        prices: List[float],
        volumes: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """
        分析市场状况
        
        Args:
            prices: 价格序列
            volumes: 成交量序列
            
        Returns:
            市场状况分析
        """
        if len(prices) < 20:
            return {
                'regime': 'unknown',
                'volatility': 0.5,
                'trend_strength': 0.5,
                'market_quality': 0.5
            }
        
        # 计算波动率
        returns = np.diff(prices) / prices[:-1]
        volatility = np.std(returns) * 100
        
        # 计算趋势强度（基于均线）
        sma_short = np.mean(prices[-5:])
        sma_long = np.mean(prices[-20:])
        trend_strength = abs((sma_short - sma_long) / sma_long) * 100 if sma_long != 0 else 0
        
        # 判断市场状态
        if volatility > 2.0:
            regime = 'high_volatility'
        elif volatility < 0.5:
            regime = 'low_volatility'
        elif trend_strength > 1.0:
            regime = 'trending'
        else:
            regime = 'ranging'
        
        # 市场质量评分（0-1）
        market_quality = 1.0 - min(volatility / 3.0, 1.0)
        
        result = {
            'regime': regime,
            'volatility': volatility,
            'trend_strength': trend_strength,
            'market_quality': market_quality
        }
        
        self.logger.debug(f"市场状态分析: {result}")
        return result


class AIDynamicRiskManager:
    """AI动态风控管理器"""
    
    def __init__(self):
        self.logger = get_logger()
        self.position_history = []
        self.performance_stats = {
            'win_rate': 0.5,
            'avg_profit': 0,
            'avg_loss': 0,
            'max_drawdown': 0,
            'profit_factor': 1.0
        }
    
    def calculate_adaptive_risk_params(
        self,
        features: Dict[str, Any],
        base_lot: float,
        base_sl_points: float,
        base_tp_points: float,
        market_condition: Dict[str, Any],
        signal_confidence: float = 0.5
    ) -> Dict[str, Any]:
        """
        计算自适应风控参数
        
        Args:
            features: AI特征
            base_lot: 基础手数
            base_sl_points: 基础止损点数
            base_tp_points: 基础止盈点数
            market_condition: 市场状况
            signal_confidence: 信号置信度
            
        Returns:
            调整后的风控参数
        """
        # 1. 根据市场状态调整
        regime = market_condition.get('regime', 'ranging')
        volatility = market_condition.get('volatility', 0.5)
        market_quality = market_condition.get('market_quality', 0.5)
        
        # 市场状态调整系数
        regime_multipliers = {
            'high_volatility': 0.5,
            'low_volatility': 1.2,
            'trending': 1.0,
            'ranging': 0.8,
            'unknown': 1.0
        }
        
        regime_multiplier = regime_multipliers.get(regime, 1.0)
        
        # 2. 根据波动率调整止损止盈
        volatility_adjust = 1.0 + (volatility - 0.5) * 0.5
        sl_points = max(20, int(base_sl_points * volatility_adjust))
        tp_points = int(base_tp_points * volatility_adjust)
        
        # 3. 根据信号置信度调整仓位
        confidence_multiplier = 0.3 + signal_confidence * 0.7  # 0.3 到 1.0
        
        # 4. 根据市场质量调整
        quality_multiplier = 0.5 + market_quality * 0.5
        
        # 5. 考虑历史表现（如果有数据）
        performance_multiplier = self._get_performance_multiplier()
        
        # 计算最终仓位
        lot = base_lot * regime_multiplier * confidence_multiplier * quality_multiplier * performance_multiplier
        
        # 计算风险回报比调整
        risk_reward_ratio = tp_points / sl_points if sl_points > 0 else 2.0
        if risk_reward_ratio < 1.5:
            lot *= 0.7  # 降低风险回报比差的仓位
        
        # 判断是否允许交易
        allow_trade = (
            signal_confidence >= 0.4 and
            market_quality >= 0.3 and
            regime != 'high_volatility'
        )
        
        result = {
            'lot': lot,
            'sl_points': sl_points,
            'tp_points': tp_points,
            'allow_trade': allow_trade,
            'risk_reward_ratio': risk_reward_ratio,
            'regime': regime,
            'volatility': volatility,
            'confidence': signal_confidence,
            'market_quality': market_quality,
            'adjustments': {
                'regime_multiplier': regime_multiplier,
                'confidence_multiplier': confidence_multiplier,
                'quality_multiplier': quality_multiplier,
                'performance_multiplier': performance_multiplier
            }
        }
        
        self.logger.info(f"AI动态风控参数: {result}")
        return result
    
    def _get_performance_multiplier(self) -> float:
        """
        根据历史表现获取调整系数
        
        Returns:
            调整系数
        """
        win_rate = self.performance_stats.get('win_rate', 0.5)
        profit_factor = self.performance_stats.get('profit_factor', 1.0)
        
        # 综合表现评分
        performance_score = (win_rate * 0.6 + min(profit_factor, 2.0) / 2.0 * 0.4)
        
        # 映射到 0.5 到 1.5 之间
        multiplier = 0.5 + performance_score
        
        return max(0.5, min(1.5, multiplier))
    
    def update_performance_stats(self, trade_result: Dict[str, Any]):
        """
        更新交易表现统计
        
        Args:
            trade_result: 交易结果
        """
        self.position_history.append(trade_result)
        
        # 只保留最近100笔交易
        if len(self.position_history) > 100:
            self.position_history = self.position_history[-100:]
        
        # 重新计算统计
        profits = [t.get('profit', 0) for t in self.position_history]
        wins = [p for p in profits if p > 0]
        losses = [p for p in profits if p <= 0]
        
        if len(profits) > 0:
            self.performance_stats['win_rate'] = len(wins) / len(profits) if len(profits) > 0 else 0.5
            self.performance_stats['avg_profit'] = np.mean(wins) if wins else 0
            self.performance_stats['avg_loss'] = np.mean(losses) if losses else 0
            
            total_profit = sum(wins)
            total_loss = abs(sum(losses)) if losses else 1
            self.performance_stats['profit_factor'] = total_profit / total_loss if total_loss > 0 else 1.0


class TrailingStopManager:
    """移动止损管理器"""
    
    def __init__(self):
        self.logger = get_logger()
        self.trailing_config = {
            'activation_points': 30,  # 盈利达到此点数开始追踪
            'trailing_distance': 20,  # 止损距离
            'step_size': 5            # 调整步长
        }
    
    def calculate_trailing_stop(
        self,
        position: Any,
        current_price: float,
        symbol_info: Any
    ) -> Optional[float]:
        """
        计算移动止损价格
        
        Args:
            position: 持仓对象
            current_price: 当前价格
            symbol_info: 品种信息
            
        Returns:
            新的止损价格，None表示不需要调整
        """
        point = symbol_info.point
        open_price = position.price_open
        current_sl = position.sl
        
        # 计算当前浮盈点数
        if position.type == mt5.POSITION_TYPE_BUY:
            profit_points = (current_price - open_price) / point
        else:
            profit_points = (open_price - current_price) / point
        
        # 检查是否激活移动止损
        if profit_points < self.trailing_config['activation_points']:
            return None
        
        # 计算新的止损价格
        if position.type == mt5.POSITION_TYPE_BUY:
            new_sl = current_price - self.trailing_config['trailing_distance'] * point
            # 只有当新止损更有利时才调整
            if current_sl == 0 or new_sl > current_sl:
                return new_sl
        else:
            new_sl = current_price + self.trailing_config['trailing_distance'] * point
            # 只有当新止损更有利时才调整
            if current_sl == 0 or new_sl < current_sl:
                return new_sl
        
        return None


class RiskManager:
    """风控管理类 - 增强版"""
    
    def __init__(self, config: Dict[str, Any], mt5_interface):
        """
        初始化风控管理器
        
        Args:
            config: 配置字典
            mt5_interface: MT5 接口实例
        """
        self.config = config
        self.mt5 = mt5_interface
        self.logger = get_logger()
        self.trading_config = config.get('trading', {})
        self.risk_config = config.get('risk', {})
        
        # AI动态风控组件
        self.ai_risk_manager = AIDynamicRiskManager()
        self.market_regime = MarketRegime()
        self.trailing_stop_manager = TrailingStopManager()
        
        # 历史价格缓存
        self.price_history = []
        
        # AI集成配置
        self.ai_enabled = self.risk_config.get('ai_enabled', False)
        self.use_dynamic_risk = self.risk_config.get('use_dynamic_risk', False)
        self.use_trailing_stop = self.risk_config.get('use_trailing_stop', False)
    
    def calculate_lot_size(
        self,
        symbol: str,
        sl_points: float,
        price: float,
        account_balance: Optional[float] = None,
        features: Optional[Dict[str, Any]] = None,
        signal_confidence: float = 0.5
    ) -> float:
        """
        计算合适的手数（支持AI动态调整）
        
        Args:
            symbol: 交易品种
            sl_points: 止损点数
            price: 当前价格
            account_balance: 账户余额
            features: AI特征
            signal_confidence: 信号置信度
            
        Returns:
            计算后的手数
        """
        base_lot = self.trading_config.get('lot_size', 0.1)
        
        # 如果启用AI动态风控
        if self.ai_enabled and self.use_dynamic_risk and features:
            # 分析市场状况
            market_condition = self._analyze_current_market(symbol)
            
            # 获取AI调整的参数
            ai_params = self.ai_risk_manager.calculate_adaptive_risk_params(
                features,
                base_lot,
                sl_points,
                self.trading_config.get('tp_points', 100),
                market_condition,
                signal_confidence
            )
            
            lot = ai_params['lot']
            self.logger.info(f"AI动态仓位计算: 基础={base_lot}, 调整后={lot}")
        else:
            # 传统动态仓位计算
            if not self.risk_config.get('dynamic_position', False):
                lot = base_lot
                self.logger.debug(f"使用固定手数: {lot}")
                return lot
            
            # 获取账户余额
            if account_balance is None:
                account_info = self.mt5.get_account_info()
                if account_info is None:
                    self.logger.warning("无法获取账户信息，使用固定手数")
                    return base_lot
                account_balance = account_info.balance
            
            # 计算风险金额
            risk_percent = self.risk_config.get('risk_percent', 1.0)
            risk_amount = account_balance * (risk_percent / 100.0)
            
            # 计算每个点的价值
            pip_value = calculate_pip_value(symbol, price, 1.0)
            
            # 计算手数
            if sl_points > 0 and pip_value > 0:
                lot = risk_amount / (sl_points * pip_value)
            else:
                lot = base_lot
        
        return lot
    
    def calculate_risk_params_with_ai(
        self,
        symbol: str,
        features: Dict[str, Any],
        signal_confidence: float = 0.5
    ) -> Dict[str, Any]:
        """
        使用AI计算完整风控参数
        
        Args:
            symbol: 交易品种
            features: AI特征
            signal_confidence: 信号置信度
            
        Returns:
            完整风控参数
        """
        base_lot = self.trading_config.get('lot_size', 0.1)
        base_sl = self.trading_config.get('sl_points', 50)
        base_tp = self.trading_config.get('tp_points', 100)
        
        # 分析市场状况
        market_condition = self._analyze_current_market(symbol)
        
        # 获取AI调整的参数
        ai_params = self.ai_risk_manager.calculate_adaptive_risk_params(
            features,
            base_lot,
            base_sl,
            base_tp,
            market_condition,
            signal_confidence
        )
        
        return ai_params
    
    def _analyze_current_market(self, symbol: str) -> Dict[str, Any]:
        """
        分析当前市场状况
        
        Args:
            symbol: 交易品种
            
        Returns:
            市场状况分析
        """
        try:
            # 获取最近的K线数据
            candles = self.mt5.get_candles(symbol, mt5.TIMEFRAME_H1, 50)
            if candles is not None and len(candles) > 0:
                prices = [c.close for c in candles]
                volumes = [c.tick_volume for c in candles] if hasattr(candles[0], 'tick_volume') else None
                return self.market_regime.analyze_market_condition(prices, volumes)
        except Exception as e:
            self.logger.error(f"市场分析失败: {e}")
        
        return {
            'regime': 'unknown',
            'volatility': 0.5,
            'trend_strength': 0.5,
            'market_quality': 0.5
        }
    
    def validate_lot_size(self, symbol: str, lot: float) -> Tuple[bool, float, Optional[str]]:
        """
        验证并调整手数大小
        
        Args:
            symbol: 交易品种
            lot: 计算的手数
            
        Returns:
            (是否有效, 调整后的手数, 错误信息)
        """
        self.logger.info(f"开始验证手数: 输入手数={lot}")
        
        # 获取品种信息
        symbol_info = self.mt5.get_symbol_info(symbol)
        if symbol_info is None:
            return False, lot, "无法获取品种信息"
        
        # 检查手数是否在允许范围内
        min_lot = symbol_info.volume_min
        max_lot = self.trading_config.get('max_lot', symbol_info.volume_max)
        lot_step = symbol_info.volume_step
        
        self.logger.info(f"品种 {symbol} 参数: min={min_lot}, max={max_lot}, step={lot_step}")
        
        # 手数不能小于最小值
        if lot < min_lot:
            lot = min_lot
            self.logger.warning(f"手数小于最小值，调整为: {lot}")
        
        # 手数不能大于最大值
        if lot > max_lot:
            lot = max_lot
            self.logger.warning(f"手数大于最大值，调整为: {lot}")
        
        # 调整到手数步长的倍数
        lot = round(lot / lot_step) * lot_step
        
        self.logger.info(f"验证后最终手数: {lot}")
        
        return True, lot, None
    
    def calculate_sl_tp_prices(
        self,
        symbol: str,
        order_type: int,
        sl_points: Optional[float] = None,
        tp_points: Optional[float] = None
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        计算止损止盈价格
        
        Args:
            symbol: 交易品种
            order_type: 订单类型
            sl_points: 止损点数
            tp_points: 止盈点数
            
        Returns:
            (止损价格, 止盈价格) 元组
        """
        # 获取当前价格
        price_info = self.mt5.get_current_price(symbol)
        if price_info is None:
            return None, None
        
        bid, ask = price_info
        
        # 获取品种信息
        symbol_info = self.mt5.get_symbol_info(symbol)
        if symbol_info is None:
            return None, None
        
        point = symbol_info.point
        
        # 使用配置的点数（如果未提供）
        if sl_points is None:
            sl_points = self.trading_config.get('sl_points', 50)
        if tp_points is None:
            tp_points = self.trading_config.get('tp_points', 100)
        
        sl_price = None
        tp_price = None
        
        # 计算止损止盈价格
        if order_type == mt5.ORDER_TYPE_BUY:
            if sl_points > 0:
                sl_price = ask - sl_points * point
            if tp_points > 0:
                tp_price = ask + tp_points * point
        else:
            if sl_points > 0:
                sl_price = bid + sl_points * point
            if tp_points > 0:
                tp_price = bid - tp_points * point
        
        return sl_price, tp_price
    
    def update_trailing_stops(self, symbol: str):
        """
        更新所有持仓的移动止损
        
        Args:
            symbol: 交易品种
        """
        if not self.use_trailing_stop:
            return
        
        try:
            positions = self.mt5.get_positions(symbol)
            symbol_info = self.mt5.get_symbol_info(symbol)
            price_info = self.mt5.get_current_price(symbol)
            
            if symbol_info is None or price_info is None:
                return
            
            bid, ask = price_info
            
            for position in positions:
                current_price = ask if position.type == mt5.POSITION_TYPE_BUY else bid
                new_sl = self.trailing_stop_manager.calculate_trailing_stop(
                    position, current_price, symbol_info
                )
                
                if new_sl is not None:
                    # 修改止损
                    success = self.mt5.modify_position_stop_loss(position.ticket, new_sl)
                    if success:
                        self.logger.info(f"移动止损已更新: 仓位={position.ticket}, 新止损={new_sl}")
        
        except Exception as e:
            self.logger.error(f"更新移动止损失败: {e}")
    
    def check_duplicate_position(self, symbol: str, order_type: int) -> Tuple[bool, Optional[Any]]:
        """检查是否已有同方向持仓"""
        positions = self.mt5.get_positions(symbol)
        target_position_type = mt5.POSITION_TYPE_BUY if order_type == mt5.ORDER_TYPE_BUY else mt5.POSITION_TYPE_SELL
        
        for position in positions:
            if position.type == target_position_type:
                self.logger.warning(f"检测到同方向持仓，仓位号: {position.ticket}")
                return True, position
        
        return False, None
    
    def check_margin_sufficient(
        self,
        symbol: str,
        order_type: int,
        lot: float,
        price: float
    ) -> Tuple[bool, Optional[str]]:
        """检查保证金是否充足"""
        if not self.risk_config.get('check_margin', True):
            return True, None
        
        margin_required = self.mt5.calculate_margin_required(symbol, order_type, lot, price)
        if margin_required is None:
            return False, "无法计算所需保证金"
        
        account_info = self.mt5.get_account_info()
        if account_info is None:
            return False, "无法获取账户信息"
        
        free_margin = account_info.margin_free
        
        if margin_required > free_margin:
            return False, f"保证金不足: 需要 {margin_required:.2f}, 可用 {free_margin:.2f}"
        
        self.logger.debug(f"保证金检查通过: 需要 {margin_required:.2f}, 可用 {free_margin:.2f}")
        return True, None
    
    def validate_stop_loss_distance(
        self,
        symbol: str,
        sl_price: Optional[float],
        current_price: float
    ) -> Tuple[bool, Optional[str]]:
        """验证止损距离是否足够"""
        if sl_price is None:
            return False, "必须设置止损"
        
        min_sl_distance = self.risk_config.get('min_sl_distance', 20)
        symbol_info = self.mt5.get_symbol_info(symbol)
        if symbol_info is None:
            return False, "无法获取品种信息"
        
        point = symbol_info.point
        sl_distance = abs(sl_price - current_price) / point
        
        if sl_distance < min_sl_distance:
            return False, f"止损距离过小: {sl_distance:.1f} 点, 最小要求 {min_sl_distance} 点"
        
        return True, None
    
    def check_position_count(self, symbol: str, target_order_type: Optional[int] = None) -> Tuple[bool, Optional[str]]:
        """检查持仓数量是否超限"""
        max_positions_per_direction = self.risk_config.get('max_positions_per_direction', 1)
        positions = self.mt5.get_positions(symbol)
        
        if target_order_type is not None:
            target_type = mt5.POSITION_TYPE_BUY if target_order_type == mt5.ORDER_TYPE_BUY else mt5.POSITION_TYPE_SELL
            same_direction_count = sum(1 for p in positions if p.type == target_type)
            
            if same_direction_count >= max_positions_per_direction:
                return False, f"同方向持仓数量已达上限: {same_direction_count}/{max_positions_per_direction}"
        
        max_total_positions = self.risk_config.get('max_total_positions', 10)
        if len(positions) >= max_total_positions:
            return False, f"总持仓数量已达上限: {len(positions)}/{max_total_positions}"
        
        return True, None
    
    def perform_risk_check(
        self,
        symbol: str,
        order_type: int,
        lot: float,
        sl_price: Optional[float],
        tp_price: Optional[float],
        price: float
    ) -> Tuple[bool, Optional[str]]:
        """执行完整的风控检查"""
        has_dup, _ = self.check_duplicate_position(symbol, order_type)
        if has_dup:
            return False, "已有同方向持仓"
        
        pos_ok, pos_msg = self.check_position_count(symbol, order_type)
        if not pos_ok:
            return False, pos_msg
        
        sl_ok, sl_msg = self.validate_stop_loss_distance(symbol, sl_price, price)
        if not sl_ok:
            return False, sl_msg
        
        margin_ok, margin_msg = self.check_margin_sufficient(symbol, order_type, lot, price)
        if not margin_ok:
            return False, margin_msg
        
        self.logger.info("风控检查通过")
        return True, None
