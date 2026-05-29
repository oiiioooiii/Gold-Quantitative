# 黄金量化交易系统 - 主程序入口
import os
import sys
import signal
import threading
import uvicorn
from utils.logger import setup_logger, get_logger
from utils.helpers import load_config
from mt5_interface import MT5Interface
from risk_manager import RiskManager
from strategy_engine import StrategyEngine
from notification import Notifier
from enterprise_server import EnterpriseWebServer
from ai_model import AIModelManager
from data_collector import DataCollector


class TradingBot:
    """黄金量化交易机器人"""
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        初始化交易机器人
        
        Args:
            config_path: 配置文件路径
        """
        # 加载配置
        self.config = load_config(config_path)
        
        # 设置日志
        setup_logger(self.config)
        self.logger = get_logger()
        
        # 初始化组件
        self.mt5 = None
        self.risk_manager = None
        self.notifier = None
        self.strategy_engine = None
        self.webhook_server = None
        self.ai_manager = None
        self.data_collector = None
        self.data_collection_thread = None
        self.running = False
        
        # 注册信号处理（Windows兼容）
        if sys.platform == 'win32':
            import threading
            
            # Windows下使用控制台事件处理
            def console_handler(event):
                if event == 2:  # CTRL_C_EVENT
                    self.logger.info("收到中断信号，正在停止...")
                    self.stop()
            
            try:
                import ctypes
                ctypes.windll.kernel32.SetConsoleCtrlHandler(
                    ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)(console_handler), 
                    True
                )
            except Exception as e:
                self.logger.warning(f"无法设置控制台事件处理器: {e}")
        else:
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """信号处理函数 - 优雅退出"""
        self.logger.info(f"收到信号 {signum}，正在停止...")
        self.stop()
        sys.exit(0)
    
    def initialize(self) -> bool:
        """
        初始化所有组件
        
        Returns:
            是否初始化成功
        """
        try:
            self.logger.info("=" * 50)
            self.logger.info("正在初始化黄金量化交易系统...")
            self.logger.info("=" * 50)
            
            # 1. 初始化 MT5 接口
            self.logger.info("正在初始化 MT5 接口...")
            self.mt5 = MT5Interface(self.config)
            if not self.mt5.initialize():
                self.logger.error("MT5 初始化失败！")
                return False
            
            # 2. 初始化通知管理器
            self.logger.info("正在初始化通知管理器...")
            self.notifier = Notifier(self.config)
            
            # 3. 初始化风控管理器
            self.logger.info("正在初始化风控管理器...")
            self.risk_manager = RiskManager(self.config, self.mt5)
            
            # 4. 初始化 AI 模型管理器
            self.logger.info("正在初始化 AI 模型管理器...")
            self.ai_manager = AIModelManager(self.config)
            
            # 5. 初始化策略引擎
            self.logger.info("正在初始化策略引擎...")
            self.strategy_engine = StrategyEngine(
                self.config,
                self.mt5,
                self.risk_manager,
                self.notifier
            )
            
            # 6. 初始化企业级 Web 服务器
            self.logger.info("正在初始化企业级 Web 服务器...")
            self.webhook_server = EnterpriseWebServer(self.config, self.strategy_engine, self.mt5)
            self.webhook_server.start_push_loop()
            
            # 7. 初始化数据采集器
            self.logger.info("正在初始化数据采集器...")
            self.data_collector = DataCollector(self.config, self.mt5)
            
            self.logger.info("=" * 50)
            self.logger.info("系统初始化完成！")
            self.logger.info("=" * 50)
            
            # 发送系统启动通知
            self.notifier.notify_system_start()
            
            return True
            
        except Exception as e:
            self.logger.error(f"初始化系统时出错: {e}")
            return False
    
    def start(self):
        """启动系统"""
        if not self.initialize():
            self.logger.error("系统初始化失败，退出！")
            sys.exit(1)
        
        self.running = True
        
        # 启动数据采集线程（如果启用）
        if self.data_collector and self.data_collector.enabled:
            self.logger.info("启动数据采集线程...")
            self.data_collection_thread = threading.Thread(
                target=self.data_collector.run_collection_loop,
                daemon=True
            )
            self.data_collection_thread.start()
        
        # 启动 Webhook 服务器
        webhook_config = self.config.get('webhook', {})
        host = webhook_config.get('host', '0.0.0.0')
        port = webhook_config.get('port', 8000)
        
        self.logger.info(f"启动 Web 服务器: http://{host}:{port}")
        self.logger.info(f"可视化界面: http://localhost:{port}")
        
        try:
            uvicorn.run(
                self.webhook_server.app,
                host=host,
                port=port,
                log_level="info"
            )
        except KeyboardInterrupt:
            self.logger.info("收到中断信号")
        finally:
            self.stop()
    
    def stop(self):
        """停止系统"""
        if not self.running:
            return
        
        self.logger.info("正在停止系统...")
        self.running = False
        
        # 停止 WebSocket 推送循环
        if self.webhook_server:
            self.webhook_server.stop_push_loop()
        
        # 发送系统停止通知
        if self.notifier:
            try:
                self.notifier.notify_system_stop()
            except Exception as e:
                self.logger.warning(f"发送停止通知失败: {e}")
        
        # 关闭 MT5 连接
        if self.mt5:
            try:
                self.mt5.shutdown()
            except Exception as e:
                self.logger.warning(f"关闭 MT5 连接失败: {e}")
        
        self.logger.info("系统已停止")
        print("\n系统已完全停止。再见！")


def main():
    """主函数"""
    # 获取配置文件路径
    config_path = os.environ.get('CONFIG_PATH', 'config.yaml')
    
    # 创建并启动交易机器人
    bot = TradingBot(config_path)
    bot.start()


if __name__ == "__main__":
    main()
