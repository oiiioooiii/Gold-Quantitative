"""
黄金量化交易系统 - 企业级WebSocket服务器
Enterprise WebSocket Server for Real-Time Trading
"""

import asyncio
import json
import threading
from datetime import datetime
from typing import Dict, Set, Any
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
    
    def __init__(self, config: Dict[str, Any], strategy_engine, mt5_interface):
        self.config = config
        self.strategy_engine = strategy_engine
        self.mt5_interface = mt5_interface
        self.logger = get_logger()
        self.trading_config = config.get('trading', {})
        
        # WebSocket连接管理器
        self.connection_manager = ConnectionManager()
        
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
                
                with open(config_path, 'w', encoding='utf-8') as f:
                    yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
                
                # 更新当前配置
                if hasattr(self, 'trading_config'):
                    self.trading_config.update(config.get('trading', {}))
                
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
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container-fluid">
            <a class="navbar-brand" href="#">
                <i class="fas fa-chart-line"></i>
                黄金量化交易系统
                <span class="badge bg-warning text-dark ms-2">ENTERPRISE</span>
            </a>
            <div class="navbar-nav ms-auto">
                <span id="connection-status" class="badge bg-danger ms-3">
                    <i class="fas fa-circle"></i> 连接断开
                </span>
                <span id="server-time" class="text-light ms-3"></span>
            </div>
        </div>
    </nav>

    <div class="container-fluid mt-4">
        <div class="row">
            <div class="col-md-2">
                <div class="list-group" id="nav-menu">
                    <a href="#" class="list-group-item list-group-item-action active" data-page="dashboard">
                        <i class="fas fa-tachometer-alt"></i> 仪表板
                    </a>
                    <a href="#" class="list-group-item list-group-item-action" data-page="trade">
                        <i class="fas fa-exchange-alt"></i> 手动交易
                    </a>
                    <a href="#" class="list-group-item list-group-item-action" data-page="signals">
                        <i class="fas fa-broadcast-tower"></i> 信号测试
                    </a>
                    <a href="#" class="list-group-item list-group-item-action" data-page="settings">
                        <i class="fas fa-cog"></i> 系统设置
                    </a>
                </div>
            </div>
            
            <div class="col-md-10">
                <div id="main-content"></div>
            </div>
        </div>
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
    <h2 class="mb-3"><i class="fas fa-tachometer-alt"></i> 企业级仪表板</h2>
    
    <div class="row mb-3">
        <div class="col-md-3">
            <div class="card bg-primary text-white" style="height: 100%;">
                <div class="card-body py-2">
                    <h6 class="card-subtitle mb-1">账户余额</h6>
                    <h4 class="card-title" id="account-balance">$0.00</h4>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card bg-success text-white" style="height: 100%;">
                <div class="card-body py-2">
                    <h6 class="card-subtitle mb-1">账户净值</h6>
                    <h4 class="card-title" id="account-equity">$0.00</h4>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card bg-warning text-dark" style="height: 100%;">
                <div class="card-body py-2">
                    <h6 class="card-subtitle mb-1">浮动盈亏</h6>
                    <h4 class="card-title" id="account-profit">$0.00</h4>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card bg-info text-white" style="height: 100%;">
                <div class="card-body py-2">
                    <h6 class="card-subtitle mb-1">持仓数量</h6>
                    <h4 class="card-title" id="positions-count">0</h4>
                </div>
            </div>
        </div>
    </div>
    
    <div class="row mb-3">
        <div class="col-md-12">
            <div class="card">
                <div class="card-header bg-dark text-white py-2 d-flex justify-content-between align-items-center">
                    <h6 class="mb-0"><i class="fas fa-chart-bar"></i> K线图</h6>
                    <div class="d-flex gap-2">
                        <select class="form-select form-select-sm" id="timeframe-select" onchange="wsClient.changeTimeframe(this.value)" style="width: 100px;">
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
                        <button class="btn btn-secondary btn-sm" onclick="loadCandlesForChart()">
                            <i class="fas fa-sync-alt"></i> 刷新
                        </button>
                    </div>
                </div>
                <div class="card-body p-1">
                    <div id="kline-chart" style="width: 100%; height: 280px;"></div>
                    <!-- 成交量图表 -->
                    <div id="volume-chart" style="width: 100%; height: 90px; margin-top: 5px;"></div>
                </div>
            </div>
            
            <!-- K线浮动提示 -->
            <div id="kline-tooltip" style="position: fixed; z-index: 10000; background: rgba(0, 0, 0, 0.95); border: 1px solid #444; border-radius: 8px; padding: 12px; color: white; font-size: 12px; display: none; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5); min-width: 200px;">
                <table style="width: 100%;">
                    <tr><td style="color: #888; padding: 2px 4px;">开盘:</td><td id="tt-open" style="padding: 2px 4px;">-</td></tr>
                    <tr><td style="color: #888; padding: 2px 4px;">最高:</td><td id="tt-high" style="padding: 2px 4px;">-</td></tr>
                    <tr><td style="color: #888; padding: 2px 4px;">最低:</td><td id="tt-low" style="padding: 2px 4px;">-</td></tr>
                    <tr><td style="color: #888; padding: 2px 4px;">收盘:</td><td id="tt-close" style="padding: 2px 4px;">-</td></tr>
                    <tr><td style="color: #888; padding: 2px 4px;">涨跌:</td><td id="tt-change" style="padding: 2px 4px;">-</td></tr>
                    <tr><td style="color: #888; padding: 2px 4px;">涨幅:</td><td id="tt-change-percent" style="padding: 2px 4px;">-</td></tr>
                    <tr><td style="color: #888; padding: 2px 4px;">振幅:</td><td id="tt-amplitude" style="padding: 2px 4px;">-</td></tr>
                    <tr><td style="color: #888; padding: 2px 4px;">成交量:</td><td id="tt-volume" style="padding: 2px 4px;">-</td></tr>
                </table>
            </div>
            
            <!-- 指标图区域 - 更紧凑的布局 -->
            <div class="row mt-2 g-2">
                <div class="col-md-4">
                    <div class="card h-100">
                        <div class="card-header bg-dark text-white py-1 px-2">
                            <h6 class="mb-0 small"><i class="fas fa-chart-line"></i> MACD</h6>
                        </div>
                        <div class="card-body p-1">
                            <div id="macd-chart" style="width: 100%; height: 110px;"></div>
                        </div>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="card h-100">
                        <div class="card-header bg-dark text-white py-1 px-2">
                            <h6 class="mb-0 small"><i class="fas fa-chart-area"></i> RSI</h6>
                        </div>
                        <div class="card-body p-1">
                            <div id="rsi-chart" style="width: 100%; height: 110px;"></div>
                        </div>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="card h-100">
                        <div class="card-header bg-dark text-white py-1 px-2">
                            <h6 class="mb-0 small"><i class="fas fa-chart-bar"></i> KDJ</h6>
                        </div>
                        <div class="card-body p-1">
                            <div id="kdj-chart" style="width: 100%; height: 110px;"></div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <div class="row mb-3">
        <div class="col-md-5">
            <div class="card">
                <div class="card-header bg-dark text-white py-2">
                    <h6 class="mb-0"><i class="fas fa-tags"></i> 实时价格</h6>
                </div>
                <div class="card-body py-2 text-center">
                    <h5 id="price-symbol">XAUUSD</h5>
                    <h3 id="price-value">--</h3>
                    <div class="row mt-2">
                        <div class="col-6">
                            <p class="mb-1 text-danger">买价 (Bid)</p>
                            <h5 id="price-bid">--</h5>
                        </div>
                        <div class="col-6">
                            <p class="mb-1 text-success">卖价 (Ask)</p>
                            <h5 id="price-ask">--</h5>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        <div class="col-md-7">
            <div class="card">
                <div class="card-header bg-dark text-white py-2">
                    <h6 class="mb-0"><i class="fas fa-chart-area"></i> OHLC数据</h6>
                </div>
                <div class="card-body py-2">
                    <div class="row">
                        <div class="col-3 mb-2">
                            <div class="card bg-light border-secondary">
                                <div class="card-body py-2">
                                    <h6 class="text-muted mb-1">开盘</h6>
                                    <h6 id="ohlc-open" class="text-dark mb-0">--</h6>
                                </div>
                            </div>
                        </div>
                        <div class="col-3 mb-2">
                            <div class="card bg-light border-danger">
                                <div class="card-body py-2">
                                    <h6 class="text-muted mb-1">最高</h6>
                                    <h6 id="ohlc-high" class="text-danger mb-0">--</h6>
                                </div>
                            </div>
                        </div>
                        <div class="col-3 mb-2">
                            <div class="card bg-light border-success">
                                <div class="card-body py-2">
                                    <h6 class="text-muted mb-1">最低</h6>
                                    <h6 id="ohlc-low" class="text-success mb-0">--</h6>
                                </div>
                            </div>
                        </div>
                        <div class="col-3 mb-2">
                            <div class="card bg-light border-info">
                                <div class="card-body py-2">
                                    <h6 class="text-muted mb-1">收盘</h6>
                                    <h6 id="ohlc-close" class="text-info mb-0">--</h6>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="row">
                        <div class="col-12">
                            <div class="card bg-light">
                                <div class="card-body py-2">
                                    <h6 class="text-muted mb-1">成交量 (Volume)</h6>
                                    <h6 id="ohlc-volume" class="text-secondary mb-0">--</h6>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <div class="row mb-3">
        <div class="col-md-12">
            <div class="card">
                <div class="card-header bg-dark text-white py-2 d-flex justify-content-between">
                    <h6 class="mb-0"><i class="fas fa-bolt"></i> 快速交易</h6>
                </div>
                <div class="card-body py-2">
                    <div class="row">
                        <div class="col-md-3 mb-2">
                            <label class="mb-1">手数</label>
                            <input type="number" class="form-control form-control-sm" id="quick-lot" value="0.1" step="0.01">
                        </div>
                        <div class="col-md-2 mb-2">
                            <label class="mb-1">止损</label>
                            <input type="number" class="form-control form-control-sm" id="quick-sl" value="50">
                        </div>
                        <div class="col-md-2 mb-2">
                            <label class="mb-1">止盈</label>
                            <input type="number" class="form-control form-control-sm" id="quick-tp" value="100">
                        </div>
                        <div class="col-md-5 mb-2">
                            <label class="mb-1">操作</label>
                            <div class="row">
                                <div class="col-6">
                                    <button class="btn btn-success btn-sm w-100" onclick="quickTrade('buy')">
                                        <i class="fas fa-arrow-up"></i> 做多
                                    </button>
                                </div>
                                <div class="col-6">
                                    <button class="btn btn-danger btn-sm w-100" onclick="quickTrade('sell')">
                                        <i class="fas fa-arrow-down"></i> 做空
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <div class="row">
        <div class="col-md-12">
            <div class="card">
                <div class="card-header bg-dark text-white py-2 d-flex justify-content-between">
                    <h6 class="mb-0"><i class="fas fa-list"></i> 当前持仓</h6>
                    <button class="btn btn-danger btn-sm" onclick="closeAllPositions()">
                        <i class="fas fa-times-circle"></i> 全部平仓
                    </button>
                </div>
                <div class="card-body p-0">
                    <table class="table table-striped table-hover mb-0 table-sm">
                        <thead class="table-dark">
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
        
        return f"""
<div id="page-settings" class="page-content">
    <h2 class="mb-4"><i class="fas fa-cog"></i> 系统设置</h2>
    
    <div class="card">
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
            <button class="btn btn-primary btn-lg w-100" onclick="saveSettings()">
                <i class="fas fa-save"></i> 保存设置
            </button>
        </div>
    </div>
</div>
"""
