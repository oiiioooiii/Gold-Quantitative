# 通知模块
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional
from utils.logger import get_logger


class Notifier:
    """通知管理器"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化通知管理器
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.logger = get_logger()
        self.notification_config = config.get('notification', {})
        
        # Telegram 配置
        self.telegram_enabled = self.notification_config.get('telegram', {}).get('enabled', False)
        self.telegram_token = self.notification_config.get('telegram', {}).get('token', '')
        self.telegram_chat_id = self.notification_config.get('telegram', {}).get('chat_id', '')
        
        # 邮件配置
        self.email_enabled = self.notification_config.get('email', {}).get('enabled', False)
        self.email_smtp_server = self.notification_config.get('email', {}).get('smtp_server', '')
        self.email_smtp_port = self.notification_config.get('email', {}).get('smtp_port', 587)
        self.email_username = self.notification_config.get('email', {}).get('username', '')
        self.email_password = self.notification_config.get('email', {}).get('password', '')
        self.email_recipient = self.notification_config.get('email', {}).get('recipient', '')
    
    def send_telegram_message(self, message: str) -> bool:
        """
        发送 Telegram 消息
        
        Args:
            message: 消息内容
            
        Returns:
            是否发送成功
        """
        if not self.telegram_enabled:
            return False
        
        if not self.telegram_token or not self.telegram_chat_id:
            self.logger.warning("Telegram 配置不完整")
            return False
        
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            data = {
                "chat_id": self.telegram_chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }
            
            response = requests.post(url, data=data, timeout=10)
            response.raise_for_status()
            
            self.logger.debug("Telegram 消息发送成功")
            return True
        except Exception as e:
            self.logger.error(f"发送 Telegram 消息失败: {e}")
            return False
    
    def send_email(self, subject: str, message: str) -> bool:
        """
        发送邮件
        
        Args:
            subject: 邮件主题
            message: 邮件内容
            
        Returns:
            是否发送成功
        """
        if not self.email_enabled:
            return False
        
        if not all([
            self.email_smtp_server,
            self.email_username,
            self.email_password,
            self.email_recipient
        ]):
            self.logger.warning("邮件配置不完整")
            return False
        
        try:
            # 创建邮件
            msg = MIMEMultipart()
            msg['From'] = self.email_username
            msg['To'] = self.email_recipient
            msg['Subject'] = subject
            
            # 添加正文
            msg.attach(MIMEText(message, 'plain', 'utf-8'))
            
            # 发送邮件
            with smtplib.SMTP(self.email_smtp_server, self.email_smtp_port) as server:
                server.starttls()
                server.login(self.email_username, self.email_password)
                server.send_message(msg)
            
            self.logger.debug("邮件发送成功")
            return True
        except Exception as e:
            self.logger.error(f"发送邮件失败: {e}")
            return False
    
    def notify_order_opened(
        self,
        symbol: str,
        order_type: str,
        lot: float,
        price: float,
        sl_price: Optional[float] = None,
        tp_price: Optional[float] = None,
        comment: str = ""
    ):
        """
        通知订单开仓
        
        Args:
            symbol: 交易品种
            order_type: 订单类型 ('BUY' 或 'SELL')
            lot: 手数
            price: 价格
            sl_price: 止损价格
            tp_price: 止盈价格
            comment: 备注
        """
        emoji = "🟢" if order_type == "BUY" else "🔴"
        message = (
            f"{emoji} *订单开仓*\n"
            f"品种: {symbol}\n"
            f"类型: {order_type}\n"
            f"手数: {lot}\n"
            f"价格: {price:.2f}\n"
        )
        if sl_price:
            message += f"止损: {sl_price:.2f}\n"
        if tp_price:
            message += f"止盈: {tp_price:.2f}\n"
        if comment:
            message += f"备注: {comment}\n"
        
        self.logger.info(message)
        self.send_telegram_message(message)
        self.send_email(f"订单开仓 - {symbol}", message)
    
    def notify_order_closed(
        self,
        symbol: str,
        order_type: str,
        lot: float,
        close_price: float,
        profit: Optional[float] = None,
        comment: str = ""
    ):
        """
        通知订单平仓
        
        Args:
            symbol: 交易品种
            order_type: 订单类型 ('BUY' 或 'SELL')
            lot: 手数
            close_price: 平仓价格
            profit: 盈亏
            comment: 备注
        """
        emoji = "✅"
        profit_emoji = "💰" if profit and profit > 0 else "💸"
        
        message = (
            f"{emoji} *订单平仓*\n"
            f"品种: {symbol}\n"
            f"类型: {order_type}\n"
            f"手数: {lot}\n"
            f"平仓价格: {close_price:.2f}\n"
        )
        if profit is not None:
            message += f"{profit_emoji} 盈亏: {profit:.2f}\n"
        if comment:
            message += f"备注: {comment}\n"
        
        self.logger.info(message)
        self.send_telegram_message(message)
        self.send_email(f"订单平仓 - {symbol}", message)
    
    def notify_error(
        self,
        error_message: str,
        error_details: Optional[str] = None
    ):
        """
        通知错误
        
        Args:
            error_message: 错误消息
            error_details: 错误详情
        """
        emoji = "⚠️"
        message = f"{emoji} *错误告警*\n{error_message}\n"
        if error_details:
            message += f"\n详情:\n{error_details}\n"
        
        self.logger.error(message)
        self.send_telegram_message(message)
        self.send_email("交易系统错误告警", message)
    
    def notify_warning(
        self,
        warning_message: str
    ):
        """
        通知警告
        
        Args:
            warning_message: 警告消息
        """
        emoji = "⚡"
        message = f"{emoji} *警告*\n{warning_message}\n"
        
        self.logger.warning(message)
        self.send_telegram_message(message)
    
    def notify_system_start(self):
        """通知系统启动"""
        emoji = "🚀"
        message = f"{emoji} *黄金量化交易系统已启动*\n"
        
        self.logger.info(message)
        self.send_telegram_message(message)
    
    def notify_system_stop(self):
        """通知系统停止"""
        emoji = "🛑"
        message = f"{emoji} *黄金量化交易系统已停止*\n"
        
        self.logger.info(message)
        self.send_telegram_message(message)
