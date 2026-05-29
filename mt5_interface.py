# MT5 接口模块
import MetaTrader5 as mt5
import time
from typing import Optional, Tuple, List, Dict, Any
from utils.logger import get_logger
from utils.helpers import retry_on_failure


class MT5Interface:
    """MT5 接口封装类"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化 MT5 接口
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.logger = get_logger()
        self.mt5_config = config.get('mt5', {})
        self.connected = False
    
    def initialize(self) -> bool:
        """
        初始化并连接到 MT5 终端
        
        Returns:
            是否成功初始化
        """
        self.logger.info("正在初始化 MT5 连接...")
        
        # 首先尝试不指定路径，直接连接到已运行的 MT5 终端
        self.logger.info("尝试连接到已运行的 MT5 终端...")
        if mt5.initialize():
            self.connected = True
            self.logger.info("成功连接到已运行的 MT5 终端!")
            
            # 获取账户信息
            account_info = mt5.account_info()
            if account_info:
                self.logger.info(f"账户信息: 登录={account_info.login}, 余额={account_info.balance:.2f}")
            else:
                self.logger.warning("无法获取账户信息，请确保 MT5 已登录账户")
            
            return True
        
        # 如果失败，尝试使用配置文件中的参数
        self.logger.info("无法连接到已运行的 MT5，尝试使用配置参数启动...")
        
        mt5_path = self.mt5_config.get('path')
        login = self.mt5_config.get('login')
        password = self.mt5_config.get('password')
        server = self.mt5_config.get('server')
        
        self.logger.info(f"MT5 路径: {mt5_path}")
        self.logger.info(f"服务器: {server}")
        self.logger.info(f"账户: {login}")
        
        # 尝试初始化 MT5
        if not mt5.initialize(
            path=mt5_path,
            login=login,
            password=password,
            server=server,
            timeout=30000,  # 减少超时时间
            portable=False
        ):
            error_code = mt5.last_error()
            self.logger.error(f"MT5 初始化失败! 错误代码: {error_code}")
            self.logger.error("解决方案: 1) 请先手动打开 MT5 终端并登录账户 2) 检查配置文件中的路径和账户信息是否正确")
            return False
        
        self.connected = True
        self.logger.info("MT5 连接成功!")
        
        # 获取账户信息
        account_info = mt5.account_info()
        if account_info:
            self.logger.info(f"账户信息: 登录={account_info.login}, 余额={account_info.balance:.2f}")
        
        return True
    
    def shutdown(self):
        """关闭 MT5 连接"""
        if self.connected:
            mt5.shutdown()
            self.connected = False
            self.logger.info("MT5 连接已关闭")
    
    def check_connection(self) -> bool:
        """
        检查 MT5 连接状态
        
        Returns:
            是否连接
        """
        if not self.connected:
            return False
        
        try:
            terminal_info = mt5.terminal_info()
            if terminal_info is None:
                self.logger.warning("MT5 终端未连接")
                self.connected = False
                return False
            return True
        except Exception as e:
            self.logger.error(f"检查 MT5 连接时出错: {e}")
            self.connected = False
            return False
    
    @retry_on_failure(max_retries=3, delay=2.0)
    def ensure_connection(self) -> bool:
        """
        确保连接，如果断开则尝试重连
        
        Returns:
            是否连接成功
        """
        if self.check_connection():
            return True
        
        self.logger.warning("MT5 连接断开，尝试重新连接...")
        return self.initialize()
    
    def get_current_price(self, symbol: str) -> Optional[Tuple[float, float]]:
        """
        获取当前买价和卖价
        
        Args:
            symbol: 交易品种
            
        Returns:
            (bid, ask) 元组，失败返回 None
        """
        if not self.ensure_connection():
            return None
        
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            self.logger.error(f"获取 {symbol} 价格失败! 错误: {mt5.last_error()}")
            return None
        
        return (tick.bid, tick.ask)
    
    def get_symbol_info(self, symbol: str) -> Optional[Any]:
        """
        获取品种信息
        
        Args:
            symbol: 交易品种
            
        Returns:
            品种信息对象，失败返回 None
        """
        if not self.ensure_connection():
            return None
        
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            self.logger.error(f"获取 {symbol} 信息失败! 错误: {mt5.last_error()}")
            return None
        
        return symbol_info
    
    def get_positions(self, symbol: Optional[str] = None) -> List[Any]:
        """
        获取当前持仓
        
        Args:
            symbol: 可选，按品种过滤，None表示获取所有持仓
            
        Returns:
            持仓列表
        """
        if not self.ensure_connection():
            return []
        
        try:
            if symbol:
                # 如果指定了品种，按品种过滤
                positions = mt5.positions_get(symbol=symbol)
            else:
                # 如果没有指定品种，获取所有持仓
                positions = mt5.positions_get()
            
            if positions is None:
                error_code = mt5.last_error()
                if error_code[0] == 1:  # RES_S_OK，只是没有持仓
                    return []
                self.logger.error(f"获取持仓失败! 错误: {error_code}")
                return []
            
            return list(positions)
        except Exception as e:
            self.logger.error(f"获取持仓异常: {e}")
            return []
    
    def get_account_info(self) -> Optional[Any]:
        """
        获取账户信息
        
        Returns:
            账户信息对象，失败返回 None
        """
        if not self.ensure_connection():
            return None
        
        return mt5.account_info()
    
    def calculate_margin_required(self, symbol: str, order_type: int, lot: float, price: float) -> Optional[float]:
        """
        计算所需保证金
        
        Args:
            symbol: 交易品种
            order_type: 订单类型
            lot: 手数
            price: 价格
            
        Returns:
            所需保证金，失败返回 None
        """
        if not self.ensure_connection():
            return None
        
        margin = mt5.order_calc_margin(order_type, symbol, lot, price)
        if margin is None:
            self.logger.error(f"计算保证金失败! 错误: {mt5.last_error()}")
            return None
        
        return margin
    
    def place_market_order(
        self,
        symbol: str,
        order_type: int,
        lot: float,
        sl_price: Optional[float] = None,
        tp_price: Optional[float] = None,
        comment: str = "auto"
    ) -> Optional[Any]:
        """
        下市价单
        
        Args:
            symbol: 交易品种
            order_type: 订单类型 (mt5.ORDER_TYPE_BUY 或 mt5.ORDER_TYPE_SELL)
            lot: 手数
            sl_price: 止损价格
            tp_price: 止盈价格
            comment: 订单注释
            
        Returns:
            订单执行结果，失败返回 None
        """
        if not self.ensure_connection():
            return None
        
        # 获取当前价格
        price_info = self.get_current_price(symbol)
        if price_info is None:
            return None
        
        bid, ask = price_info
        
        # 确定订单价格
        if order_type == mt5.ORDER_TYPE_BUY:
            price = ask
        else:
            price = bid
        
        # 获取品种信息以获取点值
        symbol_info = self.get_symbol_info(symbol)
        if symbol_info is None:
            return None
        
        point = symbol_info.point
        digits = symbol_info.digits
        
        # 准备订单请求
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot,
            "type": order_type,
            "price": price,
            "deviation": 20,  # 允许的价格偏差（点）
            "magic": 123456,  # 魔术数字，用于识别策略订单
            "comment": comment,
            "type_filling": mt5.ORDER_FILLING_IOC,  # 即时成交或取消
            "type_time": mt5.ORDER_TIME_GTC,  # 一直有效直到取消
        }
        
        # 添加止损止盈
        if sl_price is not None:
            request["sl"] = round(sl_price, digits)
        if tp_price is not None:
            request["tp"] = round(tp_price, digits)
        
        # 发送订单
        self.logger.info(f"发送订单: {symbol}, 类型={order_type}, 手数={lot}, 价格={price:.{digits}f}")
        result = mt5.order_send(request)
        
        if result is None:
            self.logger.error(f"订单发送失败! 错误: {mt5.last_error()}")
            return None
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            self.logger.error(f"订单执行失败! 返回码: {result.retcode}, 描述: {result.comment}")
            return None
        
        self.logger.info(f"订单执行成功! 订单号: {result.order}")
        return result
    
    def close_position(self, position_ticket: int, lot: Optional[float] = None) -> Optional[Any]:
        """
        平仓指定仓位
        
        Args:
            position_ticket: 仓位订单号
            lot: 平仓手数，None 表示全部平仓
            
        Returns:
            订单执行结果，失败返回 None
        """
        if not self.ensure_connection():
            return None
        
        # 获取持仓信息
        positions = mt5.positions_get(ticket=position_ticket)
        if positions is None or len(positions) == 0:
            self.logger.error(f"未找到仓位: {position_ticket}")
            return None
        
        position = positions[0]
        
        # 确定平仓手数
        close_lot = lot if lot is not None else position.volume
        
        # 确定平仓类型和价格
        if position.type == mt5.POSITION_TYPE_BUY:
            close_type = mt5.ORDER_TYPE_SELL
            price = position.price_current  # 使用 bid 价平仓多单
        else:
            close_type = mt5.ORDER_TYPE_BUY
            price = position.price_current  # 使用 ask 价平仓空单
        
        # 准备平仓请求
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": close_lot,
            "type": close_type,
            "position": position_ticket,
            "price": price,
            "deviation": 20,
            "magic": 123456,
            "comment": "close",
            "type_filling": mt5.ORDER_FILLING_IOC,
            "type_time": mt5.ORDER_TIME_GTC,
        }
        
        # 发送平仓订单
        self.logger.info(f"平仓: 仓位={position_ticket}, 手数={close_lot}")
        result = mt5.order_send(request)
        
        if result is None:
            self.logger.error(f"平仓失败! 错误: {mt5.last_error()}")
            return None
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            self.logger.error(f"平仓执行失败! 返回码: {result.retcode}, 描述: {result.comment}")
            return None
        
        self.logger.info(f"平仓成功! 订单号: {result.order}")
        return result
    
    def close_all_positions(self, symbol: Optional[str] = None) -> int:
        """
        平掉所有仓位
        
        Args:
            symbol: 可选，只平掉指定品种的仓位
            
        Returns:
            成功平仓的数量
        """
        positions = self.get_positions(symbol)
        closed_count = 0
        
        for position in positions:
            if self.close_position(position.ticket) is not None:
                closed_count += 1
                time.sleep(0.1)  # 避免请求过快
        
        self.logger.info(f"平仓完成: 共平掉 {closed_count} 个仓位")
        return closed_count
    
    def get_candles(self, symbol: str, timeframe: int, count: int = 100) -> Optional[List[Any]]:
        """
        获取 K 线数据
        
        Args:
            symbol: 交易品种
            timeframe: 时间周期 (mt5.TIMEFRAME_M1, mt5.TIMEFRAME_H1 等)
            count: K 线数量
            
        Returns:
            K 线数据列表，失败返回 None
        """
        self.logger.info(f"get_candles 调用: symbol={symbol}, timeframe={timeframe}, count={count}")
        
        if not self.ensure_connection():
            self.logger.error("MT5 连接失败")
            return None
        
        # 确保品种可用
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            self.logger.warning(f"品种 {symbol} 不可用，尝试选择品种...")
            if not mt5.symbol_select(symbol, True):
                self.logger.error(f"无法选择品种 {symbol}")
                return None
        
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
        if rates is None:
            error = mt5.last_error()
            self.logger.error(f"获取 K 线失败! 错误代码: {error[0]}, 描述: {error[1]}")
            return None
        
        self.logger.info(f"成功获取 K 线，数量: {len(rates)}, 类型: {type(rates)}")
        
        # 检查是否是 NumPy 数组，如果是，转换为列表
        import numpy as np
        if isinstance(rates, np.ndarray):
            self.logger.info(f"NumPy 数组形状: {rates.shape}, dtype: {rates.dtype}")
            # 返回 NumPy 数组本身，让调用者处理
            return rates
        
        return list(rates)
