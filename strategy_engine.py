# 策略引擎模块
import MetaTrader5 as mt5
from typing import Dict, Any, Optional, Tuple
from utils.logger import get_logger
from utils.helpers import validate_signal
from mt5_interface import MT5Interface
from risk_manager import RiskManager
from notification import Notifier


class StrategyEngine:
    """策略引擎类"""
    
    def __init__(
        self,
        config: Dict[str, Any],
        mt5_interface: MT5Interface,
        risk_manager: RiskManager,
        notifier: Notifier
    ):
        """
        初始化策略引擎
        
        Args:
            config: 配置字典
            mt5_interface: MT5 接口实例
            risk_manager: 风控管理器实例
            notifier: 通知管理器实例
        """
        self.config = config
        self.mt5 = mt5_interface
        self.risk_manager = risk_manager
        self.notifier = notifier
        self.logger = get_logger()
        self.trading_config = config.get('trading', {})
    
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
        执行开仓操作
        
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
        
        self.logger.info(f"接收到的手数参数: {lot} (类型: {type(lot)})")
        
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
        
        # 计算手数
        if lot is None:
            sl_points_for_calc = sl_points if sl_points is not None else self.trading_config.get('sl_points', 50)
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
