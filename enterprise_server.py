"""
黄金量化交易系统 - 企业级WebSocket服务器
Enterprise WebSocket Server for Real-Time Trading
"""

import asyncio
import json
import threading
from datetime import datetime
from typing import Dict, Set, Any
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from functools import partial
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import os
import time
import MetaTrader5 as mt5

from utils.logger import get_logger


class ConnectionManager:
    """WebSocket连接管理器"""
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.lock = threading.Lock()
    
    async def connect(self, websocket: WebSocket):
        """连接新客户端"""
        await websocket.accept()
        with self.lock:
            self.active_connections.add(websocket)
        logger = get_logger()
        logger.info(f"客户端连接: {websocket.client}, 当前连接数: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        """断开客户端连接"""
        with self.lock:
            self.active_connections.discard(websocket)
        logger = get_logger()
        logger.info(f"客户端断开: {websocket.client}, 当前连接数: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict):
        """广播消息给所有客户端"""
        disconnected = set()
        
        with self.lock:
            connections = self.active_connections.copy()
        
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger = get_logger()
                logger.warning(f"发送消息失败: {e}")
                disconnected.add(connection)
        
        # 清理断开的连接
        for conn in disconnected:
            self.disconnect(conn)


class EnterpriseWebServer:
    """企业级Web服务器 - 支持WebSocket实时通讯"""
    
    def __init__(self, config: Dict[str, Any], strategy_engine, mt5_interface, ai_model_manager=None, data_collector=None):
        self.config = config
        self.strategy_engine = strategy_engine
        self.mt5_interface = mt5_interface
        self.ai_model_manager = ai_model_manager
        self.data_collector = data_collector
        self.logger = get_logger()
        self.trading_config = config.get('trading', {})
        
        # WebSocket连接管理器
        self.connection_manager = ConnectionManager()
        
        # 创建线程池用于执行同步任务
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        # 创建FastAPI应用
        self.app = FastAPI(title="黄金量化交易系统 - 企业版", version="3.0.0")
        
        # 挂载静态文件
        static_dir = f"{os.path.dirname(__file__)}/static"
        if os.path.exists(static_dir):
            self.app.mount("/static", StaticFiles(directory=static_dir), name="static")
        
        # 注册路由
        self._register_routes()
        
        # 启动实时数据推送
        self.push_thread = None
        self.push_running = False
    
    def _register_routes(self):
        """注册所有路由"""
        
        # 主页面
        @self.app.get("/", response_class=HTMLResponse)
        async def root():
            return self._render_enterprise_page()
        
        # 健康检查
        @self.app.get("/health")
        async def health_check():
            return {"status": "healthy", "service": "gold-trading-bot-enterprise"}
        
        # WebSocket路由
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket实时通讯"""
            await self.connection_manager.connect(websocket)
            try:
                # 发送初始数据
                await websocket.send_json({
                    "type": "connected",
                    "message": "已连接到交易服务器",
                    "timestamp": datetime.now().isoformat()
                })
                
                # 持续监听消息
                while True:
                    try:
                        data = await websocket.receive_json()
                        await self.handle_websocket_message(websocket, data)
                    except WebSocketDisconnect:
                        break
                    except Exception as e:
                        self.logger.error(f"WebSocket消息处理错误: {e}")
                        
            finally:
                self.connection_manager.disconnect(websocket)
        
        # 获取K线数据
        @self.app.get("/api/candles/{symbol}/{timeframe}")
        @self.app.get("/api/candles/{symbol}")
        async def get_candles(symbol: str, timeframe: str = "H1", count: int = 1):
            """获取K线数据"""
            import MetaTrader5 as mt5
            import traceback
            
            self.logger.info(f"请求 K 线数据: symbol={symbol}, timeframe={timeframe}, count={count}")
            
            # 时间周期映射
            timeframe_map = {
                "M1": mt5.TIMEFRAME_M1,
                "M5": mt5.TIMEFRAME_M5,
                "M15": mt5.TIMEFRAME_M15,
                "M30": mt5.TIMEFRAME_M30,
                "H1": mt5.TIMEFRAME_H1,
                "H4": mt5.TIMEFRAME_H4,
                "D1": mt5.TIMEFRAME_D1,
                "W1": mt5.TIMEFRAME_W1,
                "MN1": mt5.TIMEFRAME_MN1
            }
            
            mt5_timeframe = timeframe_map.get(timeframe.upper(), mt5.TIMEFRAME_H1)
            
            try:
                # 确保 MT5 连接
                if not self.mt5_interface.check_connection():
                    self.logger.warning("MT5 未连接，尝试重连...")
                    if not self.mt5_interface.initialize():
                        return {"success": False, "message": "MT5 连接失败"}
                
                # 检查品种是否可用
                symbol_info = mt5.symbol_info(symbol)
                if symbol_info is None:
                    self.logger.warning(f"品种 {symbol} 不可用，尝试选择品种...")
                    if not mt5.symbol_select(symbol, True):
                        return {"success": False, "message": f"品种 {symbol} 不可用"}
                
                candles = self.mt5_interface.get_candles(symbol, mt5_timeframe, count)
                self.logger.info(f"获取到的 K 线数据类型: {type(candles)}, 长度: {len(candles) if candles is not None else 0}")
                
                if candles is not None and len(candles) > 0:
                    import numpy as np
                    candle_data = []
                    
                    # 检查数据类型
                    is_numpy = isinstance(candles, np.ndarray)
                    self.logger.info(f"是否为 NumPy 数组: {is_numpy}")
                    
                    if is_numpy:
                        # 处理 NumPy 结构化数组
                        self.logger.info(f"NumPy 数组字段: {candles.dtype.names}")
                        
                        for i in range(len(candles)):
                            try:
                                candle_dict = {
                                    "time": datetime.fromtimestamp(int(candles[i]['time'])).isoformat(),
                                    "open": float(candles[i]['open']),
                                    "high": float(candles[i]['high']),
                                    "low": float(candles[i]['low']),
                                    "close": float(candles[i]['close']),
                                    "volume": int(candles[i]['tick_volume']) if 'tick_volume' in candles.dtype.names else 0
                                }
                                candle_data.append(candle_dict)
                            except Exception as e:
                                self.logger.error(f"解析第 {i} 根 NumPy K 线失败: {e}")
                                continue
                    else:
                        # 处理列表形式
                        first_candle = candles[0]
                        self.logger.info(f"第一根 K 线类型: {type(first_candle)}, 内容: {first_candle}")
                        
                        for i, candle in enumerate(candles):
                            try:
                                # 尝试多种方式获取数据
                                candle_dict = {}
                                
                                # 方式1: 尝试属性访问
                                try:
                                    if hasattr(candle, 'time'):
                                        candle_dict = {
                                            "time": datetime.fromtimestamp(candle.time).isoformat(),
                                            "open": candle.open,
                                            "high": candle.high,
                                            "low": candle.low,
                                            "close": candle.close,
                                            "volume": candle.tick_volume if hasattr(candle, 'tick_volume') else 0
                                        }
                                except:
                                    pass
                                
                                # 方式2: 如果属性访问失败，尝试索引访问
                                if not candle_dict:
                                    candle_dict = {
                                        "time": datetime.fromtimestamp(candle[0]).isoformat(),
                                        "open": candle[1],
                                        "high": candle[2],
                                        "low": candle[3],
                                        "close": candle[4],
                                        "volume": candle[7] if len(candle) > 7 else 0
                                    }
                                
                                candle_data.append(candle_dict)
                            except Exception as e:
                                self.logger.error(f"解析第 {i} 根 K 线失败: {e}")
                                continue
                    
                    if candle_data:
                        return {
                            "success": True,
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "candles": candle_data
                        }
                    else:
                        return {"success": False, "message": "K 线数据解析失败"}
                
                return {"success": False, "message": f"获取K线数据失败，返回值: {candles}"}
            except Exception as e:
                self.logger.error(f"获取K线数据异常: {e}")
                self.logger.error(f"堆栈信息: {traceback.format_exc()}")
                return {"success": False, "message": str(e)}
        
        # 获取K线和技术指标
        @self.app.get("/api/indicators/{symbol}/{timeframe}")
        async def get_indicators(symbol: str, timeframe: str = "H1", count: int = 200):
            """获取K线数据和技术指标"""
            import traceback
            
            try:
                # 先获取K线
                candles_response = await get_candles(symbol, timeframe, count)
                if not candles_response.get("success"):
                    return candles_response
                
                candle_data = candles_response.get("candles", [])
                
                if len(candle_data) < 2:
                    return {"success": False, "message": "K线数据不足"}
                
                # 提取价格数据
                close_prices = [c["close"] for c in candle_data]
                high_prices = [c["high"] for c in candle_data]
                low_prices = [c["low"] for c in candle_data]
                
                # 计算技术指标
                from indicators import (
                    calculate_sma, calculate_ema, calculate_macd, 
                    calculate_rsi, calculate_kdj, calculate_bollinger_bands
                )
                
                # 均线
                ma5 = calculate_sma(close_prices, 5)
                ma10 = calculate_sma(close_prices, 10)
                ma20 = calculate_sma(close_prices, 20)
                
                # MACD
                macd = calculate_macd(close_prices)
                
                # RSI
                rsi = calculate_rsi(close_prices)
                
                # KDJ
                kdj = calculate_kdj(high_prices, low_prices, close_prices)
                
                # 布林带
                bollinger = calculate_bollinger_bands(close_prices)
                
                return {
                    "success": True,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "candles": candle_data,
                    "indicators": {
                        "ma5": ma5,
                        "ma10": ma10,
                        "ma20": ma20,
                        "macd": macd,
                        "rsi": rsi,
                        "kdj": kdj,
                        "bollinger": bollinger
                    }
                }
            except Exception as e:
                self.logger.error(f"获取技术指标异常: {e}")
                self.logger.error(f"堆栈信息: {traceback.format_exc()}")
                return {"success": False, "message": str(e)}
        
        # ========== REST API ==========
        
        # 系统状态
        @self.app.get("/api/status")
        async def get_system_status():
            return {
                "mt5_connected": self.mt5_interface.check_connection() if self.mt5_interface else False,
                "websocket_clients": len(self.connection_manager.active_connections),
                "timestamp": datetime.now().isoformat()
            }
        
        # 账户信息
        @self.app.get("/api/account")
        async def get_account():
            account = self.mt5_interface.get_account_info() if self.mt5_interface else None
            if account:
                return {
                    "login": account.login,
                    "balance": round(account.balance, 2),
                    "equity": round(account.equity, 2),
                    "profit": round(account.profit, 2),
                    "margin": round(account.margin, 2),
                    "margin_free": round(account.margin_free, 2),
                    "leverage": account.leverage
                }
            return {"error": "无法获取账户信息"}
        
        # 持仓列表
        @self.app.get("/api/positions")
        async def get_positions():
            """获取持仓列表"""
            symbol = self.trading_config.get('symbol', 'XAUUSD')
            positions = self.mt5_interface.get_positions(symbol) if self.mt5_interface else []
            return {
                "positions": [{
                    "ticket": p.ticket,
                    "symbol": p.symbol,
                    "type": "long" if p.type == 0 else "short",
                    "volume": p.volume,
                    "open_price": round(p.price_open, 2),
                    "current_price": round(p.price_current, 2),
                    "profit": round(p.profit, 2),
                    "sl": round(p.sl, 2) if p.sl else None,
                    "tp": round(p.tp, 2) if p.tp else None
                } for p in positions],
                "count": len(positions),
                "total_profit": round(sum(p.profit for p in positions), 2)
            }
        
        # 价格数据
        @self.app.get("/api/price/{symbol}")
        @self.app.get("/api/price")
        async def get_price(symbol: str = "XAUUSD"):
            price_info = self.mt5_interface.get_current_price(symbol) if self.mt5_interface else None
            if price_info:
                bid, ask = price_info
                return {
                    "symbol": symbol,
                    "bid": bid,
                    "ask": ask,
                    "spread": round(ask - bid, 2),
                    "timestamp": datetime.now().isoformat()
                }
            return {"error": "无法获取价格"}
        
        # 挂单列表
        @self.app.get("/api/orders")
        async def get_pending_orders():
            orders = mt5.orders_get() if mt5 else []
            return {
                "orders": [{
                    "ticket": o.ticket,
                    "symbol": o.symbol,
                    "type": "buy_limit" if o.type == 1 else "sell_limit",
                    "volume": o.volume_initial,
                    "price": round(o.price_open, 2)
                } for o in orders],
                "count": len(orders)
            }
        
        # ========== LLM 历史记录 API ==========
        
        @self.app.get("/api/llm/history/analysis")
        async def get_llm_analysis_history(symbol: Optional[str] = None, limit: int = 50):
            """获取 LLM 持仓分析历史记录"""
            try:
                from llm_database import get_llm_database
                db = get_llm_database()
                analysis_list = db.get_all_position_analysis(symbol, limit)
                return {
                    "success": True,
                    "data": analysis_list,
                    "count": len(analysis_list)
                }
            except Exception as e:
                self.logger.error(f"获取 LLM 分析历史失败: {e}")
                return {
                    "success": False,
                    "message": str(e)
                }
        
        @self.app.get("/api/llm/history/conversations")
        async def get_llm_conversations(symbol: Optional[str] = None, limit: int = 50):
            """获取 LLM 对话历史记录"""
            try:
                from llm_database import get_llm_database
                db = get_llm_database()
                conversations = db.get_all_conversations(symbol, limit)
                return {
                    "success": True,
                    "data": conversations,
                    "count": len(conversations)
                }
            except Exception as e:
                self.logger.error(f"获取 LLM 对话历史失败: {e}")
                return {
                    "success": False,
                    "message": str(e)
                }
        
        @self.app.get("/api/llm/conversation/{conversation_id}")
        async def get_conversation_detail(conversation_id: int):
            """获取特定对话的详细内容"""
            try:
                from llm_database import get_llm_database
                db = get_llm_database()
                messages = db.get_conversation_history(conversation_id, limit=100)
                return {
                    "success": True,
                    "conversation_id": conversation_id,
                    "data": messages
                }
            except Exception as e:
                self.logger.error(f"获取对话详情失败: {e}")
                return {
                    "success": False,
                    "message": str(e)
                }

        # ========== AI功能API ==========

        def safe_json_serialize(obj):
            """安全地将对象转换为JSON可序列化格式"""
            import numpy as np
            
            if isinstance(obj, dict):
                return {key: safe_json_serialize(value) for key, value in obj.items()}
            elif isinstance(obj, list):
                return [safe_json_serialize(item) for item in obj]
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
        
        # 获取AI分析
        @self.app.get("/api/ai/analysis")
        async def get_ai_analysis(symbol: str = "XAUUSD"):
            """获取AI分析结果（带超时控制）"""
            if not self.strategy_engine:
                return {"enabled": False, "error": "策略引擎未初始化"}
            
            try:
                # 在线程池中执行同步任务，避免阻塞事件循环
                loop = asyncio.get_event_loop()
                
                # 设置超时时间为 30 秒
                task = loop.run_in_executor(
                    self.executor,
                    partial(self.strategy_engine.get_ai_analysis, symbol)
                )
                
                # 等待任务完成，超时 30 秒
                try:
                    result = await asyncio.wait_for(task, timeout=30.0)
                except asyncio.TimeoutError:
                    self.logger.error("AI分析超时")
                    return {
                        "enabled": True,
                        "llm_enabled": False,
                        "llm_analysis": "⚠️ 分析超时，请稍后重试。建议：检查网络连接或调整API设置。",
                        "error": "timeout"
                    }
                
                # 确保所有类型安全
                return safe_json_serialize(result)
                
            except Exception as e:
                self.logger.error(f"获取AI分析失败: {e}")
                import traceback
                self.logger.error(f"堆栈跟踪: {traceback.format_exc()}")
                return {
                    "enabled": True,
                    "llm_enabled": False,
                    "llm_analysis": f"⚠️ 分析失败：{str(e)}",
                    "error": str(e)
                }
        
        # 获取动态止损建议
        @self.app.get("/api/ai/stop-loss")
        async def get_dynamic_stop_loss(symbol: str = "XAUUSD", auto_execute: bool = False):
            """获取动态止损建议"""
            try:
                if not self.strategy_engine:
                    return {"success": False, "message": "策略引擎未初始化"}
                
                # 在线程池中执行同步任务
                loop = asyncio.get_event_loop()
                
                task = loop.run_in_executor(
                    self.executor,
                    partial(self.strategy_engine.get_dynamic_stop_loss, symbol, auto_execute)
                )
                
                # 等待任务完成，超时 30 秒（简化提示词后应该更快）
                try:
                    result = await asyncio.wait_for(task, timeout=30.0)
                    return {"success": True, "data": result}
                except asyncio.TimeoutError:
                    self.logger.error("动态止损分析超时")
                    return {"success": False, "message": "分析超时，请稍后重试"}
                
            except Exception as e:
                self.logger.error(f"获取动态止损失败: {e}")
                import traceback
                self.logger.error(f"堆栈跟踪: {traceback.format_exc()}")
                return {"success": False, "message": str(e)}
        
        # 获取AI信号
        @self.app.get("/api/ai/signal")
        async def get_ai_signal(symbol: str = "XAUUSD"):
            """获取AI交易信号"""
            try:
                if not self.ai_model_manager or not self.data_collector:
                    return {"success": False, "message": "AI组件未初始化"}
                
                features = self.data_collector.get_ai_features(symbol)
                combined_signal = self.ai_model_manager.get_combined_signal(features)
                
                if combined_signal:
                    return {
                        "success": True,
                        "signal": combined_signal.to_dict()
                    }
                else:
                    return {"success": False, "message": "无法生成信号"}
            except Exception as e:
                self.logger.error(f"获取AI信号失败: {e}")
                return {"success": False, "error": str(e)}
        
        # 执行AI指导的交易
        @self.app.post("/api/ai/trade")
        async def ai_trade(request: Request):
            """执行AI指导的交易"""
            try:
                data = await request.json()
                symbol = data.get('symbol', 'XAUUSD')
                action = data.get('action', '').upper()
                
                if action not in ['BUY', 'SELL']:
                    return {"success": False, "message": "无效的操作类型"}
                
                # 获取AI分析
                if self.strategy_engine:
                    ai_analysis = self.strategy_engine.get_ai_analysis(symbol)
                    
                    # 构建信号
                    signal = {
                        'symbol': symbol,
                        'action': action,
                        'strategy': 'AI_Trading',
                        'use_ai': True
                    }
                    
                    # 如果AI分析有风险参数，应用它们
                    if ai_analysis.get('enabled') and ai_analysis.get('risk_params'):
                        risk_params = ai_analysis['risk_params']
                        signal['lot'] = risk_params.get('lot')
                        signal['sl_points'] = risk_params.get('sl_points')
                        signal['tp_points'] = risk_params.get('tp_points')
                        signal['confidence'] = ai_analysis.get('combined_signal', {}).get('confidence', 0.5)
                    
                    # 处理信号
                    success, message, result = self.strategy_engine.process_signal(signal)
                    return {"success": success, "message": message, "result": result}
                else:
                    return {"success": False, "message": "策略引擎未初始化"}
            except Exception as e:
                self.logger.error(f"AI交易执行失败: {e}")
                return {"success": False, "error": str(e)}
        
        # ========== 交易API ==========
        
        # 执行交易
        @self.app.post("/api/trade")
        async def execute_trade(request: Request):
            try:
                data = await request.json()
                self.logger.info(f"收到交易请求: {data}")
                
                signal = {
                    "strategy": data.get("strategy", "manual"),
                    "action": data.get("action"),
                    "symbol": data.get("symbol", self.trading_config.get('symbol', 'XAUUSD')),
                    "lot": float(data.get("lot", self.trading_config.get('lot_size', 0.1))),
                    "sl_points": data.get("sl_points"),
                    "tp_points": data.get("tp_points"),
                    "comment": data.get("comment", "Manual Trade"),
                    "order_type": data.get("order_type", "market")
                }
                
                if data.get("order_type") == "limit":
                    signal["limit_price"] = data.get("limit_price")
                
                success, message, result = self.strategy_engine.process_signal(signal)
                
                if success:
                    # 广播更新
                    await self.broadcast_update()
                    return {"success": True, "message": message, "result": result}
                else:
                    return {"success": False, "message": message}
                    
            except Exception as e:
                self.logger.error(f"交易执行失败: {e}")
                return {"success": False, "message": str(e)}
        
        # 平仓
        @self.app.post("/api/position/{ticket}/close")
        async def close_position(ticket: int):
            try:
                result = self.mt5_interface.close_position(ticket) if self.mt5_interface else None
                if result:
                    await self.broadcast_update()
                    return {"success": True, "message": "平仓成功"}
                return {"success": False, "message": "平仓失败"}
            except Exception as e:
                self.logger.error(f"平仓失败: {e}")
                return {"success": False, "message": str(e)}
        
        # 全部平仓
        @self.app.post("/api/positions/close-all")
        async def close_all_positions():
            try:
                symbol = self.trading_config.get('symbol', 'XAUUSD')
                count = self.mt5_interface.close_all_positions(symbol) if self.mt5_interface else 0
                await self.broadcast_update()
                return {"success": True, "message": f"平掉 {count} 个持仓", "count": count}
            except Exception as e:
                self.logger.error(f"全部平仓失败: {e}")
                return {"success": False, "message": str(e)}
        
        # 修改持仓（止损/止盈）
        @self.app.post("/api/position/modify")
        async def modify_position(request: Request):
            try:
                data = await request.json()
                ticket = data.get('ticket')
                sl = data.get('sl')
                tp = data.get('tp')
                
                if not ticket:
                    return {"success": False, "message": "持仓单号不能为空"}
                
                self.logger.info(f"修改持仓 {ticket}: sl={sl}, tp={tp}")
                
                # 调用 mt5_interface 修改持仓
                if self.mt5_interface:
                    # 先获取持仓信息
                    positions = self.mt5_interface.get_positions()
                    target_position = None
                    for pos in positions:
                        if pos.ticket == ticket:
                            target_position = pos
                            break
                    
                    if target_position:
                        # 使用 modify_position 需要的接口 - 需要查看mt5_interface的实现
                        # 这里我们使用简单的修改方法
                        new_sl = sl if sl is not None else target_position.sl
                        new_tp = tp if tp is not None else target_position.tp
                        
                        # 尝试直接修改
                        import MetaTrader5 as mt5
                        
                        request = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "symbol": target_position.symbol,
                            "position": ticket,
                            "sl": new_sl,
                            "tp": new_tp,
                        }
                        
                        result = mt5.order_send(request)
                        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                            await self.broadcast_update()
                            return {"success": True, "message": "修改成功"}
                        else:
                            error_msg = result.comment if result else "未知错误"
                            self.logger.error(f"修改持仓失败: {error_msg}")
                            return {"success": False, "message": error_msg}
                    else:
                        return {"success": False, "message": "找不到该持仓"}
                else:
                    return {"success": False, "message": "MT5接口未初始化"}
            except Exception as e:
                self.logger.error(f"修改持仓失败: {e}")
                return {"success": False, "message": str(e)}
        
        # Webhook
        @self.app.post("/webhook")
        async def webhook(request: Request):
            try:
                signal = await request.json()
                self.logger.info(f"收到Webhook: {signal}")
                
                if "tpPrice" in signal:
                    signal["tp_price"] = signal["tpPrice"]
                if "slPrice" in signal:
                    signal["sl_price"] = signal["slPrice"]
                
                success, message, result = self.strategy_engine.process_signal(signal)
                
                if success:
                    await self.broadcast_update()
                    return {"success": True, "message": message}
                return {"success": False, "message": message}
            except Exception as e:
                self.logger.error(f"Webhook处理失败: {e}")
                return {"success": False, "message": str(e)}
        
        # 保存设置
        @self.app.post("/api/save-settings")
        async def save_settings(request: Request):
            try:
                settings = await request.json()
                self.logger.info(f"收到保存设置请求: {settings}")
                
                import yaml
                import os
                
                config_path = "config.yaml"
                if os.path.exists(config_path):
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = yaml.safe_load(f)
                else:
                    config = {}
                
                # 保存交易配置
                if 'trading' not in config:
                    config['trading'] = {}
                
                if 'lot_size' in settings:
                    config['trading']['lot_size'] = settings['lot_size']
                if 'max_lot' in settings:
                    config['trading']['max_lot'] = settings['max_lot']
                if 'sl_points' in settings:
                    config['trading']['sl_points'] = settings['sl_points']
                if 'tp_points' in settings:
                    config['trading']['tp_points'] = settings['tp_points']
                
                # 保存 AI 配置
                if 'ai' not in config:
                    config['ai'] = {}
                
                if 'ai_enabled' in settings:
                    config['ai']['enabled'] = settings['ai_enabled']
                
                if 'tv_analyzer' not in config['ai']:
                    config['ai']['tv_analyzer'] = {}
                
                if 'tv_enabled' in settings:
                    config['ai']['tv_analyzer']['enabled'] = settings['tv_enabled']
                if 'rsi_period' in settings:
                    config['ai']['tv_analyzer']['rsi_period'] = settings['rsi_period']
                if 'rsi_oversold' in settings:
                    config['ai']['tv_analyzer']['rsi_oversold'] = settings['rsi_oversold']
                if 'rsi_overbought' in settings:
                    config['ai']['tv_analyzer']['rsi_overbought'] = settings['rsi_overbought']
                if 'macd_fast' in settings:
                    config['ai']['tv_analyzer']['macd_fast'] = settings['macd_fast']
                if 'macd_slow' in settings:
                    config['ai']['tv_analyzer']['macd_slow'] = settings['macd_slow']
                if 'macd_signal' in settings:
                    config['ai']['tv_analyzer']['macd_signal'] = settings['macd_signal']
                if 'bb_period' in settings:
                    config['ai']['tv_analyzer']['bb_period'] = settings['bb_period']
                if 'bb_std' in settings:
                    config['ai']['tv_analyzer']['bb_std'] = settings['bb_std']
                
                if 'signal_combination' not in config['ai']:
                    config['ai']['signal_combination'] = {}
                
                if 'min_confidence' in settings:
                    config['ai']['signal_combination']['min_confidence'] = settings['min_confidence']
                if 'use_weighted_average' in settings:
                    config['ai']['signal_combination']['use_weighted_average'] = settings['use_weighted_average']
                
                if 'dynamic_risk' not in config['ai']:
                    config['ai']['dynamic_risk'] = {}
                
                if 'dynamic_risk_enabled' in settings:
                    config['ai']['dynamic_risk']['enabled'] = settings['dynamic_risk_enabled']
                
                # 保存 LLM 配置
                if 'llm' not in config['ai']:
                    config['ai']['llm'] = {}
                
                if 'llm_enabled' in settings:
                    config['ai']['llm']['enabled'] = settings['llm_enabled']
                if 'llm_provider' in settings:
                    config['ai']['llm']['provider'] = settings['llm_provider']
                if 'llm_api_key' in settings:
                    config['ai']['llm']['api_key'] = settings['llm_api_key']
                if 'llm_model' in settings:
                    config['ai']['llm']['model'] = settings['llm_model']
                if 'llm_base_url' in settings:
                    config['ai']['llm']['base_url'] = settings['llm_base_url']
                if 'llm_timeout' in settings:
                    config['ai']['llm']['timeout'] = settings['llm_timeout']
                if 'llm_max_tokens' in settings:
                    # 限制 max_tokens 为合理值
                    max_tokens = int(settings['llm_max_tokens'])
                    config['ai']['llm']['max_tokens'] = min(max_tokens, 4096)
                if 'llm_temperature' in settings:
                    config['ai']['llm']['temperature'] = settings['llm_temperature']
                
                if 'use_for' not in config['ai']['llm']:
                    config['ai']['llm']['use_for'] = {}
                
                if 'llm_use_signal' in settings:
                    config['ai']['llm']['use_for']['signal_analysis'] = settings['llm_use_signal']
                if 'llm_use_market' in settings:
                    config['ai']['llm']['use_for']['market_analysis'] = settings['llm_use_market']
                if 'llm_use_trade' in settings:
                    config['ai']['llm']['use_for']['auto_trade'] = settings['llm_use_trade']
                
                with open(config_path, 'w', encoding='utf-8') as f:
                    yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
                
                # 更新当前配置
                if hasattr(self, 'trading_config'):
                    self.trading_config.update(config.get('trading', {}))
                
                # 更新 AI 模型管理器配置
                if self.ai_model_manager:
                    self.ai_model_manager.update_config(config.get('ai', {}))
                
                self.logger.info(f"设置保存成功: {settings}")
                return {"success": True, "message": "设置保存成功"}
                
            except Exception as e:
                self.logger.error(f"保存设置失败: {e}")
                import traceback
                traceback.print_exc()
                return {"success": False, "message": str(e)}
        
        # ========== 页面路由 ==========
        
        @self.app.get("/api/page/{page_name}")
        async def get_page(page_name: str):
            pages = {
                "dashboard": self._dashboard_page(),
                "trade": self._trade_page(),
                "signals": self._signals_page(),
                "llm-history": self._llm_history_page(),
                "settings": self._settings_page()
            }
            return HTMLResponse(content=pages.get(page_name, self._dashboard_page()))
    
    async def handle_websocket_message(self, websocket: WebSocket, data: dict):
        """处理WebSocket消息"""
        msg_type = data.get("type")
        
        if msg_type == "ping":
            await websocket.send_json({"type": "pong", "timestamp": datetime.now().isoformat()})
        
        elif msg_type == "get_data":
            # 客户端请求完整数据
            await websocket.send_json({
                "type": "initial_data",
                "data": await self.get_all_data()
            })
    
    async def get_all_data(self) -> dict:
        """获取所有数据"""
        # 账户信息
        account = self.mt5_interface.get_account_info() if self.mt5_interface else None
        account_data = {
            "balance": round(account.balance, 2) if account else 0,
            "equity": round(account.equity, 2) if account else 0,
            "profit": round(account.profit, 2) if account else 0
        } if account else {"balance": 0, "equity": 0, "profit": 0}
        
        # 持仓
        symbol = self.trading_config.get('symbol', 'XAUUSD')
        positions = self.mt5_interface.get_positions(symbol) if self.mt5_interface else []
        positions_data = [{
            "ticket": p.ticket,
            "symbol": p.symbol,
            "type": "long" if p.type == 0 else "short",
            "volume": p.volume,
            "open_price": round(p.price_open, 2),
            "current_price": round(p.price_current, 2),
            "profit": round(p.profit, 2),
            "sl": round(p.sl, 2) if p.sl else None,
            "tp": round(p.tp, 2) if p.tp else None
        } for p in positions]
        
        # 价格
        price_info = self.mt5_interface.get_current_price(symbol) if self.mt5_interface else None
        price_data = {
            "symbol": symbol,
            "bid": price_info[0] if price_info else None,
            "ask": price_info[1] if price_info else None
        } if price_info else {"symbol": symbol, "bid": None, "ask": None}
        
        # K线和指标数据（默认1小时周期，200根）
        kline_data = None
        indicators_data = None
        try:
            import MetaTrader5 as mt5
            import numpy as np
            candles = self.mt5_interface.get_candles(symbol, mt5.TIMEFRAME_H1, 200)
            if candles is not None and len(candles) > 0:
                # 解析K线数据
                candle_data = []
                if isinstance(candles, np.ndarray):
                    # NumPy 数组
                    for i in range(len(candles)):
                        candle_dict = {
                            "time": datetime.fromtimestamp(int(candles[i]['time'])).isoformat(),
                            "open": float(candles[i]['open']),
                            "high": float(candles[i]['high']),
                            "low": float(candles[i]['low']),
                            "close": float(candles[i]['close']),
                            "volume": int(candles[i]['tick_volume']) if 'tick_volume' in candles.dtype.names else 0
                        }
                        candle_data.append(candle_dict)
                else:
                    # 普通对象
                    for i, candle in enumerate(candles):
                        candle_dict = {}
                        if hasattr(candle, 'time'):
                            candle_dict = {
                                "time": datetime.fromtimestamp(candle.time).isoformat(),
                                "open": candle.open,
                                "high": candle.high,
                                "low": candle.low,
                                "close": candle.close,
                                "volume": candle.tick_volume if hasattr(candle, 'tick_volume') else 0
                            }
                        else:
                            candle_dict = {
                                "time": datetime.fromtimestamp(candle[0]).isoformat(),
                                "open": candle[1],
                                "high": candle[2],
                                "low": candle[3],
                                "close": candle[4],
                                "volume": candle[7] if len(candle) > 7 else 0
                            }
                        candle_data.append(candle_dict)
                
                kline_data = candle_data
                
                # 计算技术指标
                from indicators import (
                    calculate_sma, calculate_ema, calculate_macd, 
                    calculate_rsi, calculate_kdj, calculate_bollinger_bands
                )
                
                close_prices = [c["close"] for c in candle_data]
                high_prices = [c["high"] for c in candle_data]
                low_prices = [c["low"] for c in candle_data]
                
                indicators_data = {
                    "ma5": calculate_sma(close_prices, 5),
                    "ma10": calculate_sma(close_prices, 10),
                    "ma20": calculate_sma(close_prices, 20),
                    "macd": calculate_macd(close_prices),
                    "rsi": calculate_rsi(close_prices),
                    "kdj": calculate_kdj(high_prices, low_prices, close_prices)
                }
        except Exception as e:
            self.logger.warning(f"获取 K线和指标 数据失败: {e}")
        
        return {
            "account": account_data,
            "positions": positions_data,
            "positions_count": len(positions),
            "price": price_data,
            "kline": kline_data,
            "indicators": indicators_data,
            "timestamp": datetime.now().isoformat()
        }
    
    async def broadcast_update(self):
        """广播实时更新"""
        try:
            data = await self.get_all_data()
            await self.connection_manager.broadcast({
                "type": "update",
                "data": data,
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            self.logger.error(f"广播更新失败: {e}")
    
    def start_push_loop(self):
        """启动推送循环"""
        if not self.push_running:
            self.push_running = True
            self.push_thread = threading.Thread(target=self._push_loop, daemon=True)
            self.push_thread.start()
            self.logger.info("实时数据推送已启动")
    
    def _push_loop(self):
        """推送循环 - 在后台线程运行"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        while self.push_running:
            try:
                loop.run_until_complete(self.broadcast_update())
                time.sleep(0.1)  # 每秒推送10次，与MT5实时更新频率一致
            except Exception as e:
                self.logger.error(f"推送循环错误: {e}")
        
        loop.close()
    
    def stop_push_loop(self):
        """停止推送循环"""
        self.push_running = False
        if self.push_thread:
            self.push_thread.join(timeout=2)
    
    def _render_enterprise_page(self):
        """渲染企业级主页"""
        return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>黄金量化交易系统 - 企业版</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <link href="/static/css/enterprise.css" rel="stylesheet">
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark shadow-sm sticky-top">
        <div class="container-fluid">
            <a class="navbar-brand d-flex align-items-center gap-2" href="#">
                <i class="fas fa-chart-line"></i>
                黄金量化交易系统
                <span class="badge bg-warning text-dark ms-2">ENTERPRISE</span>
            </a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#topNavMenu" aria-controls="topNavMenu" aria-expanded="false" aria-label="Toggle navigation">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="topNavMenu">
                <ul class="navbar-nav me-auto mb-2 mb-lg-0">
                    <li class="nav-item">
                        <a href="#" class="nav-link list-group-item list-group-item-action active" data-page="dashboard">
                            <i class="fas fa-tachometer-alt me-1"></i> 仪表板
                        </a>
                    </li>
                    <li class="nav-item">
                        <a href="#" class="nav-link list-group-item list-group-item-action" data-page="trade">
                            <i class="fas fa-exchange-alt me-1"></i> 手动交易
                        </a>
                    </li>
                    <li class="nav-item">
                        <a href="#" class="nav-link list-group-item list-group-item-action" data-page="signals">
                            <i class="fas fa-broadcast-tower me-1"></i> 信号测试
                        </a>
                    </li>
                    <li class="nav-item">
                        <a href="#" class="nav-link list-group-item list-group-item-action" data-page="llm-history">
                            <i class="fas fa-history me-1"></i> LLM 历史记录
                        </a>
                    </li>
                    <li class="nav-item">
                        <a href="#" class="nav-link list-group-item list-group-item-action" data-page="settings">
                            <i class="fas fa-cog me-1"></i> 系统设置
                        </a>
                    </li>
                </ul>
            </div>
            <div class="d-flex align-items-center gap-3">
                <span id="server-time" class="navbar-text text-light"></span>
                <span id="connection-status" class="badge bg-danger d-flex align-items-center gap-2">
                    <i class="fas fa-circle"></i>
                    连接断开
                </span>
            </div>
        </div>
    </nav>

    <div class="container-fluid dashboard-shell mt-4 px-3 px-lg-4">
        <div id="main-content"></div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/lightweight-charts@4.0.0/dist/lightweight-charts.standalone.production.js"></script>
    <script src="/static/js/enterprise.js"></script>
</body>
</html>
"""
    
    def _dashboard_page(self):
        """仪表板"""
        return """
<div id="page-dashboard" class="page-content">
    <div class="dashboard-header mb-4 d-flex flex-column flex-lg-row align-items-start justify-content-between gap-3">
        <div>
            <h2 class="mb-2"><i class="fas fa-tachometer-alt"></i> 企业级仪表板</h2>
            <p class="text-muted mb-0">实时监控行情、持仓与交易执行，支持跨屏自适应展示。</p>
        </div>
        <div class="d-flex flex-wrap gap-2 align-items-center">
            <span class="badge badge-pill badge-secondary px-3 py-2">最新数据</span>
            <span class="badge badge-pill badge-secondary px-3 py-2">K线周期: <strong>1小时</strong></span>
        </div>
    </div>

    <div class="dashboard-grid mb-4">
        <div class="dashboard-column">
            <div class="card card-glass border-0">
                <div class="card-header bg-transparent border-0 py-3">
                    <div>
                        <h5 class="mb-1"><i class="fas fa-tachometer-alt"></i> 账户概览</h5>
                        <small class="text-muted">关键指标实时更新</small>
                    </div>
                </div>
                <div class="card-body">
                    <div class="row row-cols-1 row-cols-sm-2 g-3">
                        <div class="col">
                            <div class="card metric-card shadow-sm h-100">
                                <div class="card-body d-flex align-items-center gap-3">
                                    <div class="metric-icon bg-primary text-white rounded-circle d-flex align-items-center justify-content-center">
                                        <i class="fas fa-wallet"></i>
                                    </div>
                                    <div>
                                        <small class="text-muted text-uppercase">账户余额</small>
                                        <h4 class="mb-0" id="account-balance">$0.00</h4>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="col">
                            <div class="card metric-card shadow-sm h-100">
                                <div class="card-body d-flex align-items-center gap-3">
                                    <div class="metric-icon bg-success text-white rounded-circle d-flex align-items-center justify-content-center">
                                        <i class="fas fa-layer-group"></i>
                                    </div>
                                    <div>
                                        <small class="text-muted text-uppercase">账户净值</small>
                                        <h4 class="mb-0" id="account-equity">$0.00</h4>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="col">
                            <div class="card metric-card shadow-sm h-100">
                                <div class="card-body d-flex align-items-center gap-3">
                                    <div class="metric-icon bg-warning text-dark rounded-circle d-flex align-items-center justify-content-center">
                                        <i class="fas fa-chart-line"></i>
                                    </div>
                                    <div>
                                        <small class="text-muted text-uppercase">浮动盈亏</small>
                                        <h4 class="mb-0" id="account-profit">$0.00</h4>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="col">
                            <div class="card metric-card shadow-sm h-100">
                                <div class="card-body d-flex align-items-center gap-3">
                                    <div class="metric-icon bg-info text-white rounded-circle d-flex align-items-center justify-content-center">
                                        <i class="fas fa-clipboard-list"></i>
                                    </div>
                                    <div>
                                        <small class="text-muted text-uppercase">持仓数量</small>
                                        <h4 class="mb-0" id="positions-count">0</h4>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="card card-glass border-0 equal-panel">
                <div class="card-header bg-transparent d-flex flex-column flex-md-row align-items-start align-items-md-center justify-content-between gap-3 py-3 border-0">
                    <div>
                        <h5 class="mb-1"><i class="fas fa-chart-bar"></i> K线图</h5>
                        <small class="text-muted">支持多周期切换与实时报价同步</small>
                    </div>
                    <div class="d-flex flex-wrap gap-2 align-items-center">
                        <select class="form-select form-select-sm" id="timeframe-select" onchange="wsClient.changeTimeframe(this.value)" style="width: 110px;">
                            <option value="M1">1分钟</option>
                            <option value="M5">5分钟</option>
                            <option value="M15">15分钟</option>
                            <option value="M30">30分钟</option>
                            <option value="H1" selected>1小时</option>
                            <option value="H4">4小时</option>
                            <option value="D1">日线</option>
                            <option value="W1">周线</option>
                            <option value="MN1">月线</option>
                        </select>
                        <button class="btn btn-outline-light btn-sm" onclick="loadCandlesForChart()">
                            <i class="fas fa-sync-alt"></i> 刷新
                        </button>
                    </div>
                </div>
                <div class="card-body p-0">
                    <div id="kline-chart" style="width: 100%; height: 360px;"></div>
                    <div id="volume-chart" style="width: 100%; height: 110px; margin-top: 10px;"></div>
                </div>
            </div>
            <div id="kline-tooltip" class="tooltip-panel shadow-lg">
                <table style="width: 100%;">
                    <tr><td class="text-secondary">开盘:</td><td id="tt-open">-</td></tr>
                    <tr><td class="text-secondary">最高:</td><td id="tt-high">-</td></tr>
                    <tr><td class="text-secondary">最低:</td><td id="tt-low">-</td></tr>
                    <tr><td class="text-secondary">收盘:</td><td id="tt-close">-</td></tr>
                    <tr><td class="text-secondary">涨跌:</td><td id="tt-change">-</td></tr>
                    <tr><td class="text-secondary">涨幅:</td><td id="tt-change-percent">-</td></tr>
                    <tr><td class="text-secondary">振幅:</td><td id="tt-amplitude">-</td></tr>
                    <tr><td class="text-secondary">成交量:</td><td id="tt-volume">-</td></tr>
                </table>
            </div>

            <div class="card card-glass border-0 equal-panel">
                <div class="card-header bg-transparent d-flex justify-content-between align-items-center py-3 border-0">
                    <div>
                        <h5 class="mb-1"><i class="fas fa-list"></i> 当前持仓</h5>
                        <small class="text-muted">持仓明细与平仓操作</small>
                    </div>
                    <button class="btn btn-danger btn-sm" onclick="closeAllPositions()">
                        <i class="fas fa-times-circle me-1"></i> 全部平仓
                    </button>
                </div>
                <div class="card-body p-0 overflow-auto">
                    <table class="table table-dark table-borderless align-middle mb-0">
                        <thead>
                            <tr>
                                <th>品种</th>
                                <th>方向</th>
                                <th>手数</th>
                                <th>开仓价</th>
                                <th>现价</th>
                                <th>盈亏</th>
                                <th>止损</th>
                                <th>止盈</th>
                                <th>操作</th>
                            </tr>
                        </thead>
                        <tbody id="positions-table">
                            <tr>
                                <td colspan="9" class="text-center text-muted py-4">暂无持仓</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        <div class="dashboard-column">
            <div class="card card-glass border-0 equal-panel">
                <div class="card-header bg-transparent border-0 py-3">
                    <div>
                        <h5 class="mb-1"><i class="fas fa-brain"></i> LLM 深度分析</h5>
                        <small class="text-muted">智能分析结果与信号提示</small>
                    </div>
                    <span id="llm-status" class="badge bg-light text-dark small">未配置</span>
                </div>
                <div class="card-body py-4" id="llm-analysis-container">
                    <div id="llm-loading" class="text-center text-muted py-4" style="display: none;">
                        <i class="fas fa-spinner fa-spin fa-2x mb-3"></i>
                        <p>正在获取 LLM 分析...</p>
                    </div>
                    <div id="llm-result" class="llm-analysis text-muted">
                        请先在系统设置中配置 LLM
                    </div>
                </div>
            </div>
            <div class="card card-glass border-0 equal-panel">
                <div class="card-header bg-transparent border-0 py-3">
                    <h5 class="mb-1"><i class="fas fa-tags"></i> 实时价格</h5>
                    <small class="text-muted">市场深度与最新买卖价</small>
                </div>
                <div class="card-body text-center py-4">
                    <h5 class="text-uppercase text-muted" id="price-symbol">XAUUSD</h5>
                    <h1 class="display-5 fw-bold" id="price-value">--</h1>
                    <div class="row mt-4 g-2">
                        <div class="col-6">
                            <div class="price-box bg-dark text-danger rounded-3 p-3">
                                <small class="text-muted">买价</small>
                                <div id="price-bid" class="fs-5">--</div>
                            </div>
                        </div>
                        <div class="col-6">
                            <div class="price-box bg-dark text-success rounded-3 p-3">
                                <small class="text-muted">卖价</small>
                                <div id="price-ask" class="fs-5">--</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            <div class="card card-glass border-0 equal-panel">
                <div class="card-header bg-transparent border-0 py-3">
                    <h5 class="mb-1"><i class="fas fa-bolt"></i> 快速交易</h5>
                    <small class="text-muted">一键做多/做空</small>
                </div>
                <div class="card-body py-3">
                    <div class="mb-3">
                        <label class="form-label">手数</label>
                        <input type="number" class="form-control form-control-sm" id="quick-lot" value="0.1" step="0.01">
                    </div>
                    <div class="row g-2 mb-3">
                        <div class="col-6">
                            <label class="form-label">止损</label>
                            <input type="number" class="form-control form-control-sm" id="quick-sl" value="50">
                        </div>
                        <div class="col-6">
                            <label class="form-label">止盈</label>
                            <input type="number" class="form-control form-control-sm" id="quick-tp" value="100">
                        </div>
                    </div>
                    <div class="d-grid gap-2">
                        <button class="btn btn-success btn-lg" onclick="quickTrade('buy')">
                            <i class="fas fa-arrow-up me-2"></i> 做多
                        </button>
                        <button class="btn btn-danger btn-lg" onclick="quickTrade('sell')">
                            <i class="fas fa-arrow-down me-2"></i> 做空
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
"""

    def _trade_page(self):
        """交易页面"""
        return """
<div id="page-trade" class="page-content">
    <h2 class="mb-4"><i class="fas fa-exchange-alt"></i> 手动交易</h2>
    
    <div class="row">
        <div class="col-md-6">
            <div class="card">
                <div class="card-header bg-dark text-white">
                    <h5><i class="fas fa-chart-bar"></i> 市场信息</h5>
                </div>
                <div class="card-body text-center">
                    <h4 id="trade-symbol">XAUUSD</h4>
                    <h2 class="display-4" id="trade-price">--</h2>
                    <div class="row mt-3">
                        <div class="col-6">
                            <p class="mb-0 text-danger">买价 (Bid)</p>
                            <h4 id="trade-bid">--</h4>
                        </div>
                        <div class="col-6">
                            <p class="mb-0 text-success">卖价 (Ask)</p>
                            <h4 id="trade-ask">--</h4>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="col-md-6">
            <div class="card">
                <div class="card-header bg-dark text-white">
                    <h5><i class="fas fa-sliders-h"></i> 交易参数</h5>
                </div>
                <div class="card-body">
                    <div class="mb-3">
                        <label>订单类型</label>
                        <select class="form-select" id="order-type">
                            <option value="market">市价单</option>
                            <option value="limit">限价单</option>
                        </select>
                    </div>
                    <div class="mb-3" id="limit-price-group" style="display:none;">
                        <label>限价价格</label>
                        <input type="number" class="form-control" id="limit-price">
                    </div>
                    <div class="mb-3">
                        <label>手数</label>
                        <input type="number" class="form-control" id="trade-lot" value="0.1" step="0.01">
                    </div>
                    <div class="row mb-3">
                        <div class="col-6">
                            <label>止损点数</label>
                            <input type="number" class="form-control" id="trade-sl" value="50">
                        </div>
                        <div class="col-6">
                            <label>止盈点数</label>
                            <input type="number" class="form-control" id="trade-tp" value="100">
                        </div>
                    </div>
                    <div class="row">
                        <div class="col-6">
                            <button class="btn btn-success btn-lg w-100" onclick="executeTrade('buy')">
                                <i class="fas fa-arrow-up"></i> 做多
                            </button>
                        </div>
                        <div class="col-6">
                            <button class="btn btn-danger btn-lg w-100" onclick="executeTrade('sell')">
                                <i class="fas fa-arrow-down"></i> 做空
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
"""
    
    def _signals_page(self):
        """信号测试"""
        return """
<div id="page-signals" class="page-content">
    <h2 class="mb-4"><i class="fas fa-broadcast-tower"></i> 信号测试</h2>
    
    <div class="card">
        <div class="card-header bg-dark text-white">
            <h5><i class="fas fa-cube"></i> 发送测试信号</h5>
        </div>
        <div class="card-body">
            <div class="row">
                <div class="col-md-6">
                    <div class="mb-3">
                        <label>策略名称</label>
                        <input type="text" class="form-control" id="signal-strategy" value="test">
                    </div>
                    <div class="mb-3">
                        <label>操作方向</label>
                        <select class="form-select" id="signal-action">
                            <option value="buy">做多</option>
                            <option value="sell">做空</option>
                            <option value="close">平仓</option>
                            <option value="close_all">全部平仓</option>
                        </select>
                    </div>
                    <div class="mb-3">
                        <label>手数</label>
                        <input type="number" class="form-control" id="signal-lot" value="0.1">
                    </div>
                    <div class="row mb-3">
                        <div class="col-6">
                            <label>止损点数</label>
                            <input type="number" class="form-control" id="signal-sl" value="50">
                        </div>
                        <div class="col-6">
                            <label>止盈点数</label>
                            <input type="number" class="form-control" id="signal-tp" value="100">
                        </div>
                    </div>
                    <button class="btn btn-primary w-100" onclick="sendTestSignal()">
                        <i class="fas fa-paper-plane"></i> 发送信号
                    </button>
                </div>
                <div class="col-md-6">
                    <label>响应结果</label>
                    <div id="signal-result" class="alert alert-secondary">
                        等待发送信号...
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
"""
    
    def _settings_page(self):
        """设置"""
        lot_size = self.trading_config.get('lot_size', 0.1)
        max_lot = self.trading_config.get('max_lot', 1.0)
        sl_points = self.trading_config.get('sl_points', 50)
        tp_points = self.trading_config.get('tp_points', 100)
        
        # AI配置
        ai_config = self.config.get('ai', {})
        ai_enabled = ai_config.get('enabled', True)
        tv_enabled = ai_config.get('tv_analyzer', {}).get('enabled', True)
        rsi_period = ai_config.get('tv_analyzer', {}).get('rsi_period', 14)
        rsi_oversold = ai_config.get('tv_analyzer', {}).get('rsi_oversold', 30)
        rsi_overbought = ai_config.get('tv_analyzer', {}).get('rsi_overbought', 70)
        macd_fast = ai_config.get('tv_analyzer', {}).get('macd_fast', 12)
        macd_slow = ai_config.get('tv_analyzer', {}).get('macd_slow', 26)
        macd_signal = ai_config.get('tv_analyzer', {}).get('macd_signal', 9)
        bb_period = ai_config.get('tv_analyzer', {}).get('bb_period', 20)
        bb_std = ai_config.get('tv_analyzer', {}).get('bb_std', 2.0)
        min_confidence = ai_config.get('signal_combination', {}).get('min_confidence', 0.4)
        use_weighted_average = ai_config.get('signal_combination', {}).get('use_weighted_average', True)
        dynamic_risk_enabled = ai_config.get('dynamic_risk', {}).get('enabled', True)
        
        # LLM配置
        llm_config = ai_config.get('llm', {})
        llm_enabled = llm_config.get('enabled', False)
        llm_provider = llm_config.get('provider', 'openai')
        llm_api_key = llm_config.get('api_key', '')
        llm_model = llm_config.get('model', 'gpt-4')
        llm_base_url = llm_config.get('base_url', '')
        llm_timeout = llm_config.get('timeout', 30)
        llm_max_tokens = llm_config.get('max_tokens', 1000)
        llm_temperature = llm_config.get('temperature', 0.7)
        llm_use_signal = llm_config.get('use_for', {}).get('signal_analysis', False)
        llm_use_market = llm_config.get('use_for', {}).get('market_analysis', False)
        llm_use_trade = llm_config.get('use_for', {}).get('auto_trade', False)
        
        return f"""
<div id="page-settings" class="page-content">
    <h2 class="mb-4"><i class="fas fa-cog"></i> 系统设置</h2>
    
    <!-- 交易参数设置 -->
    <div class="card mb-4">
        <div class="card-header bg-dark text-white">
            <h5><i class="fas fa-sliders-h"></i> 交易参数</h5>
        </div>
        <div class="card-body">
            <div class="row">
                <div class="col-md-6">
                    <div class="mb-3">
                        <label>默认手数</label>
                        <input type="number" class="form-control" id="config-lot" value="{lot_size}" step="0.01">
                    </div>
                    <div class="mb-3">
                        <label>最大手数</label>
                        <input type="number" class="form-control" id="config-max-lot" value="{max_lot}" step="0.1">
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="mb-3">
                        <label>默认止损点数</label>
                        <input type="number" class="form-control" id="config-sl" value="{sl_points}">
                    </div>
                    <div class="mb-3">
                        <label>默认止盈点数</label>
                        <input type="number" class="form-control" id="config-tp" value="{tp_points}">
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <!-- LLM 大语言模型设置 -->
    <div class="card mb-4">
        <div class="card-header bg-gradient text-white" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
            <h5><i class="fas fa-brain"></i> 大语言模型(LLM)设置</h5>
        </div>
        <div class="card-body">
            <div class="form-check form-switch mb-4">
                <input class="form-check-input" type="checkbox" id="llm-enabled" {"checked" if llm_enabled else ""}>
                <label class="form-check-label">启用 LLM AI</label>
            </div>
            
            <div class="row">
                <div class="col-md-6">
                    <div class="mb-3">
                        <label><i class="fas fa-robot"></i> AI 提供商</label>
                        <select class="form-select" id="llm-provider">
                            <option value="openai" {"selected" if llm_provider == "openai" else ""}>OpenAI (GPT)</option>
                            <option value="anthropic" {"selected" if llm_provider == "anthropic" else ""}>Anthropic (Claude)</option>
                            <option value="deepseek" {"selected" if llm_provider == "deepseek" else ""}>DeepSeek</option>
                            <option value="siliconflow" {"selected" if llm_provider == "siliconflow" else ""}>硅基流动</option>
                            <option value="tongyi" {"selected" if llm_provider == "tongyi" else ""}>通义千问</option>
                            <option value="custom" {"selected" if llm_provider == "custom" else ""}>自定义</option>
                        </select>
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="mb-3">
                        <label><i class="fas fa-cube"></i> 模型名称</label>
                        <input type="text" class="form-control" id="llm-model" value="{llm_model}" placeholder="gpt-4 / claude-3-opus / deepseek-chat">
                    </div>
                </div>
            </div>
            
            <div class="mb-3">
                <label><i class="fas fa-key"></i> API Key</label>
                <input type="password" class="form-control" id="llm-api-key" value="{llm_api_key}" placeholder="输入您的 API Key">
            </div>
            
            <div class="mb-3">
                <label><i class="fas fa-link"></i> Base URL (可选)</label>
                <input type="text" class="form-control" id="llm-base-url" value="{llm_base_url}" placeholder="https://api.openai.com/v1">
            </div>
            
            <div class="row">
                <div class="col-md-4">
                    <div class="mb-3">
                        <label><i class="fas fa-clock"></i> 超时时间(秒)</label>
                        <input type="number" class="form-control" id="llm-timeout" value="{llm_timeout}" min="5" max="300">
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="mb-3">
                        <label><i class="fas fa-comment"></i> 最大 Token</label>
                        <input type="number" class="form-control" id="llm-max-tokens" value="{llm_max_tokens}" min="100" max="10000">
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="mb-3">
                        <label><i class="fas fa-temperature-high"></i> 温度</label>
                        <input type="number" class="form-control" id="llm-temperature" value="{llm_temperature}" step="0.1" min="0" max="2">
                    </div>
                </div>
            </div>
            
            <hr>
            <h6 class="mb-3"><i class="fas fa-lightbulb"></i> LLM 应用场景</h6>
            
            <div class="row">
                <div class="col-md-4">
                    <div class="form-check mb-2">
                        <input class="form-check-input" type="checkbox" id="llm-use-signal" {"checked" if llm_use_signal else ""}>
                        <label class="form-check-label">信号分析</label>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="form-check mb-2">
                        <input class="form-check-input" type="checkbox" id="llm-use-market" {"checked" if llm_use_market else ""}>
                        <label class="form-check-label">市场分析</label>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="form-check mb-2">
                        <input class="form-check-input" type="checkbox" id="llm-use-trade" {"checked" if llm_use_trade else ""}>
                        <label class="form-check-label">自动交易</label>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <button class="btn btn-primary btn-lg w-100" onclick="saveSettings()">
        <i class="fas fa-save"></i> 保存所有设置
    </button>
</div>
"""
    
    def _llm_history_page(self):
        """LLM 历史记录页面"""
        return """
<div id="page-llm-history" class="page-content">
    <h2 class="mb-4"><i class="fas fa-history"></i> LLM 分析历史记录</h2>
    
    <div class="row mb-3">
        <div class="col-md-3">
            <select class="form-select" id="history-filter-symbol">
                <option value="">全部品种</option>
                <option value="XAUUSD">XAUUSD</option>
            </select>
        </div>
        <div class="col-md-3">
            <select class="form-select" id="history-filter-limit">
                <option value="20">显示最近20条</option>
                <option value="50" selected>显示最近50条</option>
                <option value="100">显示最近100条</option>
            </select>
        </div>
        <div class="col-md-6 text-end">
            <button class="btn btn-primary" onclick="refreshLLMHistory()">
                <i class="fas fa-sync-alt"></i> 刷新记录
            </button>
        </div>
    </div>
    
    <ul class="nav nav-tabs mb-3" id="history-tabs">
        <li class="nav-item">
            <a class="nav-link active" id="tab-analysis" data-tab="analysis" href="#">
                <i class="fas fa-chart-pie"></i> 持仓分析记录
            </a>
        </li>
        <li class="nav-item">
            <a class="nav-link" id="tab-conversations" data-tab="conversations" href="#">
                <i class="fas fa-comments"></i> 对话记录
            </a>
        </li>
    </ul>
    
    <div class="card">
        <div class="card-body p-0">
            <div id="history-content" class="p-3">
                <div id="history-loading" class="text-center text-muted py-4">
                    <i class="fas fa-spinner fa-spin fa-2x mb-3"></i>
                    <p>正在加载历史记录...</p>
                </div>
                <div id="history-data"></div>
            </div>
        </div>
    </div>
    
    <!-- 对话详情模态框 -->
    <div class="modal fade" id="conversationModal" tabindex="-1">
        <div class="modal-dialog modal-lg">
            <div class="modal-content">
                <div class="modal-header bg-dark text-white">
                    <h5 class="modal-title">
                        <i class="fas fa-comments"></i> 对话详情 <span id="modal-conversation-id"></span>
                    </h5>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body" id="modal-conversation-content" style="max-height: 60vh; overflow-y: auto;">
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
                </div>
            </div>
        </div>
    </div>
</div>
"""
