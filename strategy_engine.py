# 策略引擎模块
import MetaTrader5 as mt5
from typing import Dict, Any, Optional, Tuple
from utils.logger import get_logger
from utils.helpers import validate_signal
from mt5_interface import MT5Interface
from risk_manager import RiskManager
from notification import Notifier
from ai_model import AIModelManager
from data_collector import DataCollector


class StrategyEngine:
    """策略引擎类 - AI增强版"""
    
    def __init__(
        self,
        config: Dict[str, Any],
        mt5_interface: MT5Interface,
        risk_manager: RiskManager,
        notifier: Notifier,
        ai_model_manager: Optional[AIModelManager] = None,
        data_collector: Optional[DataCollector] = None
    ):
        """
        初始化策略引擎
        
        Args:
            config: 配置字典
            mt5_interface: MT5 接口实例
            risk_manager: 风控管理器实例
            notifier: 通知管理器实例
            ai_model_manager: AI模型管理器实例
            data_collector: 数据采集器实例
        """
        self.config = config
        self.mt5 = mt5_interface
        self.risk_manager = risk_manager
        self.notifier = notifier
        self.ai_model_manager = ai_model_manager
        self.data_collector = data_collector
        self.logger = get_logger()
        self.trading_config = config.get('trading', {})
        
        # AI功能配置
        self.ai_config = config.get('ai', {})
        self.ai_enabled = self.ai_config.get('enabled', False)
        self.ai_auto_trade = self.ai_config.get('auto_trade', False)
        self.logger.info(f"AI功能初始化: enabled={self.ai_enabled}, auto_trade={self.ai_auto_trade}")
    
    def get_ai_analysis(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        获取AI分析结果
        
        Args:
            symbol: 交易品种
            
        Returns:
            AI分析结果字典
        """
        if not self.ai_enabled or not self.ai_model_manager or not self.data_collector:
            return {"enabled": False, "error": "AI功能未启用"}
        
        try:
            symbol = symbol or self.trading_config.get('symbol', 'XAUUSD')
            
            # 1. 获取AI特征
            features = self.data_collector.get_ai_features(symbol)
            
            # 2. 生成AI信号
            signals = self.ai_model_manager.generate_signals(features)
            combined_signal = self.ai_model_manager.get_combined_signal(features)
            
            # 3. 计算风控参数
            risk_params = None
            if combined_signal:
                risk_params = self.risk_manager.calculate_risk_params_with_ai(
                    symbol, features, combined_signal.confidence
                )
            
            # 4. 获取 LLM 分析（如果启用）
            llm_analysis = None
            llm_enabled = False
            if 'llm' in self.ai_model_manager.models:
                llm_model = self.ai_model_manager.models['llm']
                if llm_model.enabled and llm_model.config.get('api_key'):
                    llm_enabled = True
                    try:
                        llm_result = llm_model.predict(features)
                        llm_analysis = llm_result.get('analysis', '')
                        self.logger.info("LLM 分析成功")
                    except Exception as e:
                        self.logger.error(f"LLM 分析失败: {e}")
                        llm_analysis = "LLM 分析暂不可用"
            
            # 安全的类型转换
            def safe_convert(obj):
                import numpy as np
                if isinstance(obj, dict):
                    return {key: safe_convert(value) for key, value in obj.items()}
                elif isinstance(obj, list):
                    return [safe_convert(item) for item in obj]
                elif isinstance(obj, np.integer):
                    return int(obj)
                elif isinstance(obj, np.floating):
                    return float(obj)
                elif isinstance(obj, np.ndarray):
                    return obj.tolist()
                elif isinstance(obj, np.bool_):
                    return bool(obj)
                return obj
            
            result = {
                "enabled": True,
                # 只返回关键特征，不返回全部
                "key_features": {
                    "current_close": features.get('current_close', 0),
                    "rsi": features.get('rsi', 50),
                    "volatility_20": features.get('volatility_20', 0),
                    "price_position_20": features.get('price_position_20', 0.5)
                },
                "signals": [s.to_dict() for s in signals] if signals else [],
                "combined_signal": combined_signal.to_dict() if combined_signal else None,
                "risk_params": safe_convert(risk_params) if risk_params else None,
                "symbol": symbol,
                "llm_enabled": llm_enabled,
                "llm_analysis": llm_analysis
            }
            
            return safe_convert(result)
            
        except Exception as e:
            self.logger.error(f"获取AI分析失败: {e}")
            import traceback
            self.logger.error(f"堆栈: {traceback.format_exc()}")
            return {"enabled": False, "error": str(e)}
    
    def process_signal(self, signal: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        处理交易信号
        
        Args:
            signal: 信号字典
            
        Returns:
            (是否成功, 消息, 结果数据)
        """
        self.logger.info(f"收到信号: {signal}")
        
        # 1. 验证信号
        is_valid, error_msg = validate_signal(signal)
        if not is_valid:
            self.logger.error(f"信号验证失败: {error_msg}")
            return False, error_msg, None
        
        # 2. 检查 MT5 连接
        if not self.mt5.check_connection():
            error_msg = "MT5 未连接"
            self.logger.error(error_msg)
            self.notifier.notify_error(error_msg)
            return False, error_msg, None
        
        # 3. 根据信号类型执行操作
        action = signal.get('action', '').upper()
        
        if action in ['BUY', 'SELL']:
            return self._execute_open(signal)
        elif action == 'CLOSE':
            return self._execute_close(signal)
        elif action == 'CLOSE_ALL':
            return self._execute_close_all(signal)
        else:
            error_msg = f"未知的操作类型: {action}"
            self.logger.error(error_msg)
            return False, error_msg, None
    
    def _execute_open(self, signal: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        执行开仓操作（支持AI增强）
        
        Args:
            signal: 信号字典
            
        Returns:
            (是否成功, 消息, 结果数据)
        """
        symbol = signal.get('symbol', self.trading_config.get('symbol', 'XAUUSD'))
        action = signal.get('action', '').upper()
        strategy = signal.get('strategy', 'unknown')
        
        # 获取信号参数（或使用配置）
        lot = signal.get('lot')
        sl_points = signal.get('sl_points')
        tp_points = signal.get('tp_points')
        comment = signal.get('comment', f"Strategy: {strategy}")
        
        # 确定订单类型
        order_type = mt5.ORDER_TYPE_BUY if action == 'BUY' else mt5.ORDER_TYPE_SELL
        
        # 获取当前价格
        price_info = self.mt5.get_current_price(symbol)
        if price_info is None:
            error_msg = f"无法获取 {symbol} 的价格"
            self.logger.error(error_msg)
            return False, error_msg, None
        
        bid, ask = price_info
        price = ask if order_type == mt5.ORDER_TYPE_BUY else bid
        
        # 检查是否使用AI增强风控
        use_ai_risk = signal.get('use_ai', False) and self.ai_enabled
        
        ai_features = None
        ai_risk_params = None
        if use_ai_risk and self.data_collector and self.ai_model_manager:
            try:
                # 获取AI特征
                ai_features = self.data_collector.get_ai_features(symbol)
                # 获取AI调整的风控参数
                ai_risk_params = self.risk_manager.calculate_risk_params_with_ai(
                    symbol, ai_features, signal.get('confidence', 0.5)
                )
                
                # 检查AI是否允许交易
                if ai_risk_params and not ai_risk_params.get('allow_trade', True):
                    error_msg = f"AI风控阻止交易: {ai_risk_params.get('reason', '风险过高')}"
                    self.logger.warning(error_msg)
                    return False, error_msg, None
                
                # 使用AI调整的参数
                if lot is None and ai_risk_params:
                    lot = ai_risk_params.get('lot')
                if sl_points is None and ai_risk_params:
                    sl_points = ai_risk_params.get('sl_points')
                if tp_points is None and ai_risk_params:
                    tp_points = ai_risk_params.get('tp_points')
                
                self.logger.info(f"AI风控参数已应用: lot={lot}, sl={sl_points}, tp={tp_points}")
                
            except Exception as e:
                self.logger.error(f"AI风控计算失败，使用传统风控: {e}")
        
        # 计算手数（如果还未确定）
        if lot is None:
            sl_points_for_calc = sl_points if sl_points is not None else self.trading_config.get('sl_points', 50)
            if ai_features and self.ai_enabled:
                lot = self.risk_manager.calculate_lot_size(
                    symbol, sl_points_for_calc, price, 
                    features=ai_features, signal_confidence=signal.get('confidence', 0.5)
                )
            else:
                lot = self.risk_manager.calculate_lot_size(symbol, sl_points_for_calc, price)
        
        # 验证手数
        lot_ok, lot, lot_msg = self.risk_manager.validate_lot_size(symbol, lot)
        self.logger.info(f"验证后手数: {lot}, 消息: {lot_msg}")
        if not lot_ok:
            self.logger.error(f"手数验证失败: {lot_msg}")
            return False, lot_msg, None
        
        # 计算止损止盈价格
        sl_price, tp_price = self.risk_manager.calculate_sl_tp_prices(
            symbol, order_type, sl_points, tp_points
        )
        
        # 不再自动平仓反向持仓（允许同时持有多单和空单）
        # allow_reverse = self.trading_config.get('allow_reverse', True)
        # if allow_reverse:
        #     positions = self.mt5.get_positions(symbol)
        #     for position in positions:
        #         if (order_type == mt5.ORDER_TYPE_BUY and position.type == mt5.POSITION_TYPE_SELL) or \
        #            (order_type == mt5.ORDER_TYPE_SELL and position.type == mt5.POSITION_TYPE_BUY):
        #             self.logger.info(f"检测到反向持仓，先平仓: {position.ticket}")
        #             self.mt5.close_position(position.ticket)
        
        # 执行风控检查
        risk_ok, risk_msg = self.risk_manager.perform_risk_check(
            symbol, order_type, lot, sl_price, tp_price, price
        )
        if not risk_ok:
            self.logger.warning(f"风控检查未通过: {risk_msg}")
            return False, risk_msg, None
        
        # 执行开仓
        self.logger.info(f"准备开仓: {symbol} {action} {lot} 手, 价格: {price:.2f}")
        result = self.mt5.place_market_order(
            symbol, order_type, lot, sl_price, tp_price, comment
        )
        
        if result is None:
            error_msg = "订单执行失败"
            self.logger.error(error_msg)
            self.notifier.notify_error(error_msg)
            return False, error_msg, None
        
        # 发送通知
        order_type_str = "BUY" if order_type == mt5.ORDER_TYPE_BUY else "SELL"
        self.notifier.notify_order_opened(
            symbol, order_type_str, lot, price, sl_price, tp_price, comment
        )
        
        return True, "订单执行成功", {
            "order": result.order,
            "symbol": symbol,
            "action": action,
            "lot": lot,
            "price": price,
            "sl_price": sl_price,
            "tp_price": tp_price
        }
    
    def _execute_close(self, signal: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        执行平仓操作
        
        Args:
            signal: 信号字典
            
        Returns:
            (是否成功, 消息, 结果数据)
        """
        symbol = signal.get('symbol', self.trading_config.get('symbol', 'XAUUSD'))
        position_ticket = signal.get('position_ticket')
        lot = signal.get('lot')
        comment = signal.get('comment', 'Close signal')
        
        # 如果指定了仓位号，平仓指定仓位
        if position_ticket:
            result = self.mt5.close_position(position_ticket, lot)
            if result is None:
                error_msg = f"平仓失败: {position_ticket}"
                self.logger.error(error_msg)
                return False, error_msg, None
            
            # 发送通知（简化版）
            self.notifier.notify_order_closed(
                symbol, "CLOSE", lot if lot else 0, 0, None, comment
            )
            return True, "平仓成功", {"order": result.order}
        
        # 否则平掉该品种所有同方向持仓
        action = signal.get('close_direction', '').upper()
        positions = self.mt5.get_positions(symbol)
        closed_count = 0
        
        for position in positions:
            # 如果指定了方向，只平该方向
            if action:
                if action == 'BUY' and position.type != mt5.POSITION_TYPE_BUY:
                    continue
                if action == 'SELL' and position.type != mt5.POSITION_TYPE_SELL:
                    continue
            
            result = self.mt5.close_position(position.ticket, lot)
            if result:
                closed_count += 1
        
        if closed_count == 0:
            msg = "没有可平的持仓"
            self.logger.info(msg)
            return True, msg, None
        
        msg = f"成功平仓 {closed_count} 个持仓"
        self.logger.info(msg)
        return True, msg, {"closed_count": closed_count}
    
    def _execute_close_all(self, signal: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        执行全部平仓操作
        
        Args:
            signal: 信号字典
            
        Returns:
            (是否成功, 消息, 结果数据)
        """
        symbol = signal.get('symbol')
        comment = signal.get('comment', 'Close all signal')
        
        closed_count = self.mt5.close_all_positions(symbol)
        
        msg = f"全部平仓完成，共平掉 {closed_count} 个持仓"
        self.logger.info(msg)
        
        return True, msg, {"closed_count": closed_count}
