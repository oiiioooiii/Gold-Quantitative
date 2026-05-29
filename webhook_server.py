# Webhook 服务器模块
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from typing import Dict, Any
from utils.logger import get_logger
from strategy_engine import StrategyEngine


class WebhookServer:
    """Webhook 服务器类"""
    
    def __init__(self, config: Dict[str, Any], strategy_engine: StrategyEngine):
        """
        初始化 Webhook 服务器
        
        Args:
            config: 配置字典
            strategy_engine: 策略引擎实例
        """
        self.config = config
        self.strategy_engine = strategy_engine
        self.logger = get_logger()
        self.webhook_config = config.get('webhook', {})
        self.secret_key = self.webhook_config.get('secret_key', '')
        
        # 创建 FastAPI 应用
        self.app = FastAPI(title="Gold Trading Bot Webhook", version="1.0.0")
        
        # 注册路由
        self._register_routes()
    
    def _register_routes(self):
        """注册路由"""
        
        @self.app.get("/")
        async def root():
            """根路径 - 健康检查"""
            return {"status": "ok", "message": "Gold Trading Bot Webhook is running"}
        
        @self.app.get("/health")
        async def health_check():
            """健康检查"""
            return {"status": "healthy", "service": "gold-trading-bot"}
        
        @self.app.post("/webhook")
        async def webhook(request: Request):
            """
            处理 TradingView Webhook 信号
            
            请求体示例:
            {
                "strategy": "gold_scalper",
                "action": "buy",
                "symbol": "XAUUSD",
                "lot": 0.1,
                "sl_points": 50,
                "tp_points": 100
            }
            """
            try:
                # 解析请求体
                signal = await request.json()
                self.logger.info(f"收到 Webhook 请求: {signal}")
                
                # 如果设置了密钥，验证签名（可选）
                if self.secret_key:
                    # 这里可以实现签名验证逻辑
                    # 例如检查 X-Signature 头部
                    pass
                
                # 处理信号
                success, message, result = self.strategy_engine.process_signal(signal)
                
                if success:
                    return JSONResponse(
                        status_code=status.HTTP_200_OK,
                        content={
                            "success": True,
                            "message": message,
                            "result": result
                        }
                    )
                else:
                    return JSONResponse(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        content={
                            "success": False,
                            "message": message
                        }
                    )
                    
            except Exception as e:
                self.logger.error(f"处理 Webhook 请求时出错: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Internal server error: {str(e)}"
                )
        
        @self.app.post("/webhook/close")
        async def close_position(request: Request):
            """平仓指定持仓"""
            try:
                data = await request.json()
                # 强制设置 action 为 CLOSE
                data['action'] = 'CLOSE'
                success, message, result = self.strategy_engine.process_signal(data)
                
                return JSONResponse(
                    status_code=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST,
                    content={
                        "success": success,
                        "message": message,
                        "result": result
                    }
                )
            except Exception as e:
                self.logger.error(f"平仓请求出错: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Internal server error: {str(e)}"
                )
        
        @self.app.post("/webhook/close-all")
        async def close_all_positions(request: Request):
            """全部平仓"""
            try:
                data = await request.json()
                # 强制设置 action 为 CLOSE_ALL
                data['action'] = 'CLOSE_ALL'
                success, message, result = self.strategy_engine.process_signal(data)
                
                return JSONResponse(
                    status_code=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST,
                    content={
                        "success": success,
                        "message": message,
                        "result": result
                    }
                )
            except Exception as e:
                self.logger.error(f"全部平仓请求出错: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Internal server error: {str(e)}"
                )
