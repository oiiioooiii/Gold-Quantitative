# 风控管理模块
import MetaTrader5 as mt5
from typing import Optional, Tuple, Dict, Any
from utils.logger import get_logger
from utils.helpers import calculate_pip_value


class RiskManager:
    """风控管理类"""
    
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
    
    def calculate_lot_size(
        self,
        symbol: str,
        sl_points: float,
        price: float,
        account_balance: Optional[float] = None
    ) -> float:
        """
        计算合适的手数
        
        Args:
            symbol: 交易品种
            sl_points: 止损点数
            price: 当前价格
            account_balance: 账户余额，None 则从 MT5 获取
            
        Returns:
            计算后的手数
        """
        # 如果不使用动态手数，返回固定手数
        if not self.risk_config.get('dynamic_position', False):
            lot = self.trading_config.get('lot_size', 0.1)
            self.logger.debug(f"使用固定手数: {lot}")
            return lot
        
        # 获取账户余额
        if account_balance is None:
            account_info = self.mt5.get_account_info()
            if account_info is None:
                self.logger.warning("无法获取账户信息，使用固定手数")
                return self.trading_config.get('lot_size', 0.1)
            account_balance = account_info.balance
        
        # 计算风险金额
        risk_percent = self.risk_config.get('risk_percent', 1.0)
        risk_amount = account_balance * (risk_percent / 100.0)
        
        # 计算每个点的价值
        pip_value = calculate_pip_value(symbol, price, 1.0)
        
        # 计算手数: 手数 = 风险金额 / (止损点数 * 每点价值)
        if sl_points > 0 and pip_value > 0:
            lot = risk_amount / (sl_points * pip_value)
        else:
            lot = self.trading_config.get('lot_size', 0.1)
        
        self.logger.debug(f"动态手数计算: 余额={account_balance:.2f}, 风险={risk_percent}%, "
                         f"止损点数={sl_points}, 计算手数={lot:.4f}")
        
        return lot
    
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
            sl_points: 止损点数，None 则使用配置
            tp_points: 止盈点数，None 则使用配置
            
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
            # 多单：止损在买价下方，止盈在买价上方
            if sl_points > 0:
                sl_price = ask - sl_points * point
            if tp_points > 0:
                tp_price = ask + tp_points * point
        else:
            # 空单：止损在卖价上方，止盈在卖价下方
            if sl_points > 0:
                sl_price = bid + sl_points * point
            if tp_points > 0:
                tp_price = bid - tp_points * point
        
        return sl_price, tp_price
    
    def check_duplicate_position(self, symbol: str, order_type: int) -> Tuple[bool, Optional[Any]]:
        """
        检查是否已有同方向持仓
        
        Args:
            symbol: 交易品种
            order_type: 订单类型
            
        Returns:
            (是否有同方向持仓, 持仓对象)
        """
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
        """
        检查保证金是否充足
        
        Args:
            symbol: 交易品种
            order_type: 订单类型
            lot: 手数
            price: 价格
            
        Returns:
            (是否充足, 错误信息)
        """
        if not self.risk_config.get('check_margin', True):
            return True, None
        
        # 计算所需保证金
        margin_required = self.mt5.calculate_margin_required(symbol, order_type, lot, price)
        if margin_required is None:
            return False, "无法计算所需保证金"
        
        # 获取账户自由保证金
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
        """
        验证止损距离是否足够
        
        Args:
            symbol: 交易品种
            sl_price: 止损价格
            current_price: 当前价格
            
        Returns:
            (是否有效, 错误信息)
        """
        if sl_price is None:
            return False, "必须设置止损"
        
        min_sl_distance = self.risk_config.get('min_sl_distance', 20)
        
        # 获取品种信息
        symbol_info = self.mt5.get_symbol_info(symbol)
        if symbol_info is None:
            return False, "无法获取品种信息"
        
        point = symbol_info.point
        
        # 计算止损距离
        sl_distance = abs(sl_price - current_price) / point
        
        if sl_distance < min_sl_distance:
            return False, f"止损距离过小: {sl_distance:.1f} 点, 最小要求 {min_sl_distance} 点"
        
        return True, None
    
    def check_position_count(self, symbol: str, target_order_type: Optional[int] = None) -> Tuple[bool, Optional[str]]:
        """
        检查持仓数量是否超限（支持同时持有多单和空单）
        
        Args:
            symbol: 交易品种
            target_order_type: 目标订单类型，None表示只检查总持仓
            
        Returns:
            (是否允许, 错误信息)
        """
        max_positions_per_direction = self.risk_config.get('max_positions_per_direction', 1)
        positions = self.mt5.get_positions(symbol)
        
        # 如果指定了目标方向，检查该方向是否已有持仓
        if target_order_type is not None:
            target_type = mt5.POSITION_TYPE_BUY if target_order_type == mt5.ORDER_TYPE_BUY else mt5.POSITION_TYPE_SELL
            same_direction_count = sum(1 for p in positions if p.type == target_type)
            
            if same_direction_count >= max_positions_per_direction:
                return False, f"同方向持仓数量已达上限: {same_direction_count}/{max_positions_per_direction}"
        
        # 检查总持仓数量
        max_total_positions = self.risk_config.get('max_total_positions', 10)  # 默认最多10个持仓
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
        """
        执行完整的风控检查
        
        Args:
            symbol: 交易品种
            order_type: 订单类型
            lot: 手数
            sl_price: 止损价格
            tp_price: 止盈价格
            price: 当前价格
            
        Returns:
            (是否通过, 错误信息)
        """
        # 1. 检查是否有同方向持仓
        has_dup, _ = self.check_duplicate_position(symbol, order_type)
        if has_dup:
            return False, "已有同方向持仓"
        
        # 2. 检查持仓数量
        pos_ok, pos_msg = self.check_position_count(symbol, order_type)
        if not pos_ok:
            return False, pos_msg
        
        # 3. 检查止损距离
        sl_ok, sl_msg = self.validate_stop_loss_distance(symbol, sl_price, price)
        if not sl_ok:
            return False, sl_msg
        
        # 4. 检查保证金
        margin_ok, margin_msg = self.check_margin_sufficient(symbol, order_type, lot, price)
        if not margin_ok:
            return False, margin_msg
        
        self.logger.info("风控检查通过")
        return True, None
