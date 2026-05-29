# 策略引擎模块
import threading
import time
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
        
        # AI功能配置（始终启用，因为我们只使用LLM）
        self.ai_config = config.get('ai', {})
        self.ai_enabled = True
        self.ai_auto_trade = self.ai_config.get('auto_trade', False)
        self.logger.info(f"AI功能初始化: enabled={self.ai_enabled}, auto_trade={self.ai_auto_trade}")
        
        # 后台自动分析线程
        self.auto_analysis_enabled = True
        self.auto_analysis_thread = None
        self.analysis_interval = 30  # 30秒分析一次
        self.last_analysis_time = 0
    
    def get_ai_analysis(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        获取AI分析结果（仅LLM深度分析）
        
        Args:
            symbol: 交易品种
            
        Returns:
            AI分析结果字典
        """
        if not self.ai_model_manager or not self.data_collector:
            self.logger.error("AI功能未初始化: ai_model_manager 或 data_collector 为空")
            return {"enabled": False, "error": "AI功能未初始化"}
        
        try:
            symbol = symbol or self.trading_config.get('symbol', 'XAUUSD')
            
            # 0. 检查是否有持仓
            positions = self.mt5.get_positions(symbol) if self.mt5 else []
            has_positions = len(positions) > 0
            
            # 1. 获取AI特征
            features = self.data_collector.get_ai_features(symbol)
            
            # 2. 检查 LLM 配置
            llm_analysis = None
            llm_enabled = False
            
            # 调试日志
            self.logger.info(f"AI 模型管理器中的模型: {list(self.ai_model_manager.models.keys())}")
            self.logger.info(f"AI 模型管理器激活的模型: {list(self.ai_model_manager.active_models)}")
            self.logger.info(f"当前是否有持仓: {has_positions}")
            
            if 'llm' in self.ai_model_manager.models:
                llm_model = self.ai_model_manager.models['llm']
                self.logger.info(f"LLM 模型 enabled: {llm_model.enabled}")
                self.logger.info(f"LLM 模型 API 密钥是否设置: {'是' if llm_model.config.get('api_key') else '否'}")
                
                llm_configured = llm_model.enabled and llm_model.config.get('api_key')
                llm_enabled = llm_configured
                
                if llm_configured:
                    if has_positions:
                        # 有持仓时才进行深度分析
                        try:
                            llm_result = llm_model.predict(features)
                            llm_analysis = llm_result.get('analysis', '')
                            self.logger.info("LLM 深度分析成功")
                        except Exception as e:
                            self.logger.error(f"LLM 分析失败: {e}")
                            llm_analysis = "LLM 分析暂不可用"
                    else:
                        # 无持仓时给出明确提示
                        llm_analysis = "当前无持仓，LLM 深度分析将在您开仓后自动启动，为您的持仓提供风险评估和止损建议。"
                        self.logger.info("无持仓，返回提示信息而非LLM分析")
            else:
                self.logger.warning("AI 模型管理器中没有找到 LLM 模型")
            
            # 安全的类型转换
            def safe_convert(obj):
                import numpy as np
                if isinstance(obj, dict):
                    return {key: safe_convert(value) for key, value in obj.items()}
                elif isinstance(obj, list):
                    return [safe_convert(item) for item in obj]
                elif isinstance(obj, bool):
                    return obj  # 明确保留布尔值
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
                "symbol": symbol,
                "has_positions": has_positions,  # 新增字段，告知前端是否有持仓
                "llm_enabled": bool(llm_enabled),  # 确保是布尔值
                "llm_analysis": llm_analysis
            }
            
            self.logger.info(f"返回 LLM 分析结果: llm_enabled={llm_enabled}, has_positions={has_positions}, 类型={type(llm_enabled)}")
            result_safe = safe_convert(result)
            self.logger.info(f"转换后的结果: llm_enabled={result_safe['llm_enabled']}, 类型={type(result_safe['llm_enabled'])}")
            return result_safe
            
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
    
    def get_dynamic_stop_loss(self, symbol: Optional[str] = None, auto_execute: bool = False) -> Dict[str, Any]:
        """
        获取动态止损建议
        
        Args:
            symbol: 交易品种
            auto_execute: 是否自动执行平仓
            
        Returns:
            止损建议字典
        """
        symbol = symbol or self.trading_config.get('symbol', 'XAUUSD')
        
        try:
            # 1. 获取当前持仓
            positions = self.mt5.get_positions(symbol)
            
            if not positions:
                return {
                    "has_position": False,
                    "advice": "当前无持仓",
                    "llm_used": False
                }
            
            # 2. 获取市场特征
            features = self.data_collector.get_ai_features(symbol) if self.data_collector else {}
            
            # 3. 检查 LLM
            if not self.ai_model_manager or 'llm' not in self.ai_model_manager.models:
                return {
                    "has_position": True,
                    "positions": self._format_positions(positions),
                    "advice": "LLM 未配置",
                    "llm_used": False
                }
            
            llm_model = self.ai_model_manager.models['llm']
            if not llm_model.enabled or not llm_model.config.get('api_key'):
                return {
                    "has_position": True,
                    "positions": self._format_positions(positions),
                    "advice": "LLM 未启用或未配置 API Key",
                    "llm_used": False
                }
            
            # 4. 为每个持仓获取止损建议
            stop_loss_results = []
            closed_positions = []
            
            for position in positions:
                position_info = {
                    "ticket": position.ticket,
                    "symbol": position.symbol,
                    "type": "BUY" if position.type == 0 else "SELL",
                    "volume": position.volume,
                    "open_price": position.price_open,
                    "current_price": position.price_current,
                    "profit": position.profit,
                    "sl": position.sl,
                    "tp": position.tp
                }
                
                # 获取 LLM 止损建议
                stop_loss_advice = llm_model.get_stop_loss_advice(features, position_info)
                stop_loss_advice["position_info"] = position_info
                stop_loss_results.append(stop_loss_advice)
                
                # 如果需要自动执行且 LLM 建议平仓
                if auto_execute and stop_loss_advice.get("should_close"):
                    self.logger.info(f"LLM 建议平仓，执行自动平仓: {position.ticket}")
                    result = self.mt5.close_position(position.ticket)
                    if result:
                        closed_positions.append({
                            "ticket": position.ticket,
                            "reason": stop_loss_advice.get("reason", "LLM 建议平仓")
                        })
                        self.notifier.notify_order_closed(
                            symbol, 
                            "LLM_AUTO_CLOSE", 
                            position.volume, 
                            position.profit, 
                            None, 
                            f"LLM 自动平仓: {stop_loss_advice.get('reason', '')}"
                        )
            
            return {
                "has_position": True,
                "positions": self._format_positions(positions),
                "stop_loss_advice": stop_loss_results,
                "closed_positions": closed_positions,
                "auto_executed": auto_execute,
                "llm_used": True
            }
            
        except Exception as e:
            self.logger.error(f"获取动态止损失败: {e}")
            import traceback
            self.logger.error(f"堆栈: {traceback.format_exc()}")
            return {
                "has_position": False,
                "advice": f"获取动态止损失败: {str(e)}",
                "llm_used": False,
                "error": str(e)
            }
    
    def _format_positions(self, positions) -> List[Dict[str, Any]]:
        """格式化持仓信息"""
        result = []
        for pos in positions:
            result.append({
                "ticket": pos.ticket,
                "symbol": pos.symbol,
                "type": "BUY" if pos.type == 0 else "SELL",
                "volume": pos.volume,
                "open_price": pos.price_open,
                "current_price": pos.price_current,
                "profit": pos.profit,
                "sl": pos.sl,
                "tp": pos.tp
            })
        return result
    
    def start_auto_analysis(self):
        """启动后台自动分析线程"""
        if self.auto_analysis_thread and self.auto_analysis_thread.is_alive():
            self.logger.info("后台分析线程已在运行")
            return
        
        self.auto_analysis_enabled = True
        self.auto_analysis_thread = threading.Thread(target=self._auto_analysis_loop, daemon=True)
        self.auto_analysis_thread.start()
        self.logger.info("后台自动分析线程已启动")
    
    def stop_auto_analysis(self):
        """停止后台自动分析线程"""
        self.auto_analysis_enabled = False
        if self.auto_analysis_thread:
            self.auto_analysis_thread.join(timeout=5)
            self.logger.info("后台自动分析线程已停止")
    
    def _auto_analysis_loop(self):
        """后台分析循环"""
        self.logger.info("后台分析循环开始")
        
        while self.auto_analysis_enabled:
            try:
                # 检查是否到了分析时间
                current_time = time.time()
                if current_time - self.last_analysis_time < self.analysis_interval:
                    time.sleep(1)
                    continue
                
                self.last_analysis_time = current_time
                
                # 执行分析
                self._perform_auto_analysis()
                
            except Exception as e:
                self.logger.error(f"后台分析出错: {e}")
                import traceback
                self.logger.error(f"堆栈: {traceback.format_exc()}")
                time.sleep(5)
        
        self.logger.info("后台分析循环结束")
    
    def _perform_auto_analysis(self):
        """执行自动分析"""
        symbol = self.trading_config.get('symbol', 'XAUUSD')
        
        # 1. 检查是否有持仓
        positions = self.mt5.get_positions(symbol)
        if not positions:
            self.logger.debug("无持仓，跳过分析")
            return
        
        self.logger.info(f"开始自动分析 {len(positions)} 个持仓")
        
        # 2. 获取市场特征
        if not self.data_collector:
            self.logger.warning("data_collector 未初始化")
            return
        
        features = self.data_collector.get_ai_features(symbol)
        
        # 3. 检查 LLM 配置
        if not self.ai_model_manager or 'llm' not in self.ai_model_manager.models:
            self.logger.warning("LLM 未配置")
            return
        
        llm_model = self.ai_model_manager.models['llm']
        if not llm_model.enabled or not llm_model.config.get('api_key'):
            self.logger.debug("LLM 未启用或未配置")
            return
        
        # 4. 为每个持仓分析
        closed_count = 0
        for position in positions:
            position_info = {
                "ticket": position.ticket,
                "symbol": position.symbol,
                "type": "BUY" if position.type == 0 else "SELL",
                "volume": position.volume,
                "open_price": position.price_open,
                "current_price": position.price_current,
                "profit": position.profit,
                "sl": position.sl,
                "tp": position.tp
            }
            
            try:
                # 获取 LLM 建议
                advice = llm_model.get_stop_loss_advice(features, position_info)
                
                # 检查是否需要平仓
                if advice.get('should_close', False):
                    self.logger.warning(f"LLM 建议平仓: ticket={position.ticket}, reason={advice.get('reason', '')}")
                    
                    # 执行平仓
                    result = self.mt5.close_position(position.ticket)
                    if result:
                        closed_count += 1
                        self.logger.info(f"自动平仓成功: ticket={position.ticket}, profit={position.profit}")
                        
                        # 发送通知
                        self.notifier.send_notification(
                            "LLM 自动平仓",
                            f"已平仓 {position_info['type']} {position.volume} 手，盈亏: {position.profit:.2f}\n原因: {advice.get('reason', '')}",
                            "warning"
                        )
                    
            except Exception as e:
                self.logger.error(f"分析持仓 {position.ticket} 失败: {e}")
        
        if closed_count > 0:
            self.logger.info(f"自动分析完成，平仓 {closed_count} 个")
        else:
            self.logger.debug("自动分析完成，无需平仓")
