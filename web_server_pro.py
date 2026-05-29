"""
黄金量化交易系统 - 专业版 Web 服务器
Gold Trading Bot - Professional Edition Web Server
"""

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from typing import Dict, Any, List, Optional
import os
import json
from datetime import datetime

from utils.logger import get_logger
from strategy_engine import StrategyEngine


class WebServerPro:
    """专业版 Web 服务器"""
    
    def __init__(self, config: Dict[str, Any], strategy_engine: StrategyEngine, mt5_interface):
        self.config = config
        self.strategy_engine = strategy_engine
        self.mt5_interface = mt5_interface
        self.logger = get_logger()
        self.trading_config = config.get('trading', {})
        
        # 支持的交易品种
        self.supported_symbols = [
            'XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY',
            'AUDUSD', 'USDCAD', 'USDCHF', 'BTCUSD'
        ]
        
        # 创建 FastAPI 应用
        self.app = FastAPI(title="黄金量化交易系统 - 专业版", version="2.0.0")
        
        # 挂载静态文件
        static_dir = os.path.join(os.path.dirname(__file__), "static")
        if os.path.exists(static_dir):
            self.app.mount("/static", StaticFiles(directory=static_dir), name="static")
        
        # 注册路由
        self._register_routes()
    
    def _register_routes(self):
        """注册所有路由"""
        
        @self.app.get("/", response_class=HTMLResponse)
        async def root():
            """主页 - 专业仪表板"""
            return self._render_main_page()
        
        @self.app.get("/health")
        async def health_check():
            """健康检查"""
            return {"status": "healthy", "service": "gold-trading-bot-pro"}
        
        # ========== 系统状态 API ==========
        
        @self.app.get("/api/status")
        async def get_system_status():
            """获取系统状态"""
            mt5_connected = self.mt5_interface.check_connection() if self.mt5_interface else False
            return {
                "mt5_connected": mt5_connected,
                "timestamp": datetime.now().isoformat()
            }
        
        # ========== 行情 API ==========
        
        @self.app.get("/api/price/{symbol}")
        @self.app.get("/api/price")
        async def get_price(symbol: str = None):
            """获取价格"""
            target_symbol = symbol or self.trading_config.get('symbol', 'XAUUSD')
            price_info = self.mt5_interface.get_current_price(target_symbol) if self.mt5_interface else None
            
            if price_info:
                bid, ask = price_info
                return {
                    "symbol": target_symbol,
                    "bid": bid,
                    "ask": ask,
                    "spread": round(ask - bid, 2) if bid and ask else None,
                    "timestamp": datetime.now().isoformat()
                }
            return JSONResponse(status_code=400, content={"error": "无法获取价格"})
        
        @self.app.get("/api/symbols")
        async def get_supported_symbols():
            """获取支持的品种列表"""
            return {"symbols": self.supported_symbols}
        
        # ========== 账户 API ==========
        
        @self.app.get("/api/account")
        async def get_account_info():
            """获取账户信息"""
            account_info = self.mt5_interface.get_account_info() if self.mt5_interface else None
            if account_info:
                return {
                    "login": account_info.login,
                    "balance": round(account_info.balance, 2),
                    "equity": round(account_info.equity, 2),
                    "profit": round(account_info.profit, 2),
                    "margin": round(account_info.margin, 2),
                    "margin_free": round(account_info.margin_free, 2),
                    "leverage": account_info.leverage,
                    "company": account_info.company
                }
            return JSONResponse(status_code=400, content={"error": "无法获取账户信息"})
        
        # ========== 持仓 API ==========
        
        @self.app.get("/api/positions")
        @self.app.get("/api/positions/{symbol}")
        async def get_positions(symbol: str = None):
            """获取持仓列表"""
            target_symbol = symbol or self.trading_config.get('symbol')
            positions = self.mt5_interface.get_positions(target_symbol) if self.mt5_interface else []
            
            result = []
            for pos in positions:
                result.append({
                    "ticket": pos.ticket,
                    "symbol": pos.symbol,
                    "type": "long" if pos.type == 0 else "short",
                    "type_code": pos.type,
                    "volume": pos.volume,
                    "open_price": round(pos.price_open, 2),
                    "current_price": round(pos.price_current, 2),
                    "profit": round(pos.profit, 2),
                    "sl": round(pos.sl, 2) if pos.sl else None,
                    "tp": round(pos.tp, 2) if pos.tp else None,
                    "swaps": round(pos.swap, 2),
                    "time": datetime.fromtimestamp(pos.time).isoformat()
                })
            
            return {
                "positions": result,
                "count": len(result),
                "total_profit": round(sum(p["profit"] for p in result), 2)
            }
        
        # ========== 交易 API ==========
        
        @self.app.post("/api/trade")
        async def execute_trade(request: Request):
            """执行交易 - 支持市价单和限价单"""
            try:
                data = await request.json()
                self.logger.info(f"收到交易请求: {data}")
                
                # 构建信号
                signal = {
                    "strategy": data.get("strategy", "manual"),
                    "action": data.get("action"),
                    "symbol": data.get("symbol", self.trading_config.get('symbol', 'XAUUSD')),
                    "lot": float(data.get("lot", self.trading_config.get('lot_size', 0.1))),
                    "sl_points": int(data.get("sl_points")) if data.get("sl_points") else None,
                    "tp_points": int(data.get("tp_points")) if data.get("tp_points") else None,
                    "comment": data.get("comment", "Manual Trade"),
                    "order_type": data.get("order_type", "market")
                }
                
                # 限价单支持
                if data.get("order_type") == "limit":
                    signal["limit_price"] = data.get("limit_price")
                
                # 处理信号
                success, message, result = self.strategy_engine.process_signal(signal)
                
                if success:
                    return JSONResponse(status_code=200, content={
                        "success": True,
                        "message": message,
                        "result": result
                    })
                else:
                    return JSONResponse(status_code=400, content={
                        "success": False,
                        "message": message
                    })
                    
            except Exception as e:
                self.logger.error(f"执行交易失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/position/{ticket}/close")
        async def close_position(ticket: int):
            """平掉指定持仓"""
            try:
                result = self.mt5_interface.close_position(ticket) if self.mt5_interface else None
                if result:
                    return {"success": True, "message": "平仓成功", "result": str(result)}
                else:
                    return JSONResponse(status_code=400, content={
                        "success": False, "message": "平仓失败"
                    })
            except Exception as e:
                self.logger.error(f"平仓失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/positions/close-all")
        async def close_all_positions(request: Request = None):
            """平掉所有持仓"""
            try:
                symbol = None
                if request:
                    try:
                        data = await request.json()
                        symbol = data.get("symbol")
                    except:
                        pass
                
                count = self.mt5_interface.close_all_positions(symbol) if self.mt5_interface else 0
                return {
                    "success": True,
                    "message": f"平掉 {count} 个持仓",
                    "count": count
                }
            except Exception as e:
                self.logger.error(f"全部平仓失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        # ========== 挂单 API ==========
        
        @self.app.get("/api/orders")
        async def get_pending_orders():
            """获取挂单列表"""
            import MetaTrader5 as mt5
            orders = mt5.orders_get() if mt5 else []
            result = []
            
            if orders:
                for order in orders:
                    result.append({
                        "ticket": order.ticket,
                        "symbol": order.symbol,
                        "type": "buy_limit" if order.type == 1 else "sell_limit",
                        "volume": order.volume_initial,
                        "price": round(order.price_open, 2),
                        "sl": round(order.sl, 2) if order.sl else None,
                        "tp": round(order.tp, 2) if order.tp else None,
                        "time_setup": datetime.fromtimestamp(order.time_setup).isoformat(),
                        "comment": order.comment
                    })
            
            return {"orders": result, "count": len(result)}
        
        @self.app.delete("/api/order/{ticket}")
        async def cancel_pending_order(ticket: int):
            """取消挂单"""
            import MetaTrader5 as mt5
            try:
                request = {
                    "action": mt5.TRADE_ACTION_REMOVE,
                    "order": ticket,
                }
                
                result = mt5.order_send(request)
                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    return {"success": True, "message": "挂单已取消"}
                else:
                    return JSONResponse(status_code=400, content={
                        "success": False, "message": f"取消失败: {result.comment if result else '未知错误'}"
                    })
            except Exception as e:
                self.logger.error(f"取消挂单失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        # ========== Webhook API ==========
        
        @self.app.post("/webhook")
        async def webhook(request: Request):
            """接收 TradingView Webhook - 支持多品种和 TP/SL"""
            try:
                signal = await request.json()
                self.logger.info(f"收到 Webhook: {signal}")
                
                # 支持 Pine Script 携带的 TP/SL
                if "tpPrice" in signal:
                    signal["tp_price"] = signal["tpPrice"]
                if "slPrice" in signal:
                    signal["sl_price"] = signal["slPrice"]
                
                success, message, result = self.strategy_engine.process_signal(signal)
                
                if success:
                    return JSONResponse(status_code=200, content={
                        "success": True,
                        "message": message,
                        "result": result
                    })
                else:
                    return JSONResponse(status_code=400, content={
                        "success": False,
                        "message": message
                    })
                    
            except Exception as e:
                self.logger.error(f"处理 Webhook 失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        # ========== 配置 API ==========
        
        @self.app.get("/api/config")
        async def get_config():
            """获取当前配置"""
            return {
                "trading": self.trading_config,
                "risk": self.config.get('risk', {})
            }
        
        @self.app.post("/api/config")
        async def update_config(request: Request):
            """更新配置"""
            try:
                data = await request.json()
                if "trading" in data:
                    self.trading_config.update(data["trading"])
                return {"success": True, "message": "配置已更新"}
            except Exception as e:
                self.logger.error(f"更新配置失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        # ========== 页面路由 ==========
        
        @self.app.get("/api/page/{page_name}")
        async def get_page_content(page_name: str):
            """获取页面内容"""
            pages = {
                "dashboard": self._dashboard_page(),
                "trade": self._trade_page(),
                "signals": self._signals_page(),
                "settings": self._settings_page()
            }
            return HTMLResponse(content=pages.get(page_name, self._dashboard_page()))
    
    def _render_main_page(self):
        """渲染主页面"""
        return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>黄金量化交易系统 - 专业版</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <link href="/static/css/style.css" rel="stylesheet">
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark">
        <div class="container-fluid px-4">
            <a class="navbar-brand" href="#">
                <i class="fas fa-chart-area"></i>
                黄金量化交易系统
                <span class="badge text-dark ms-2" style="background: linear-gradient(135deg, #f7931a, #ffc107);">PRO</span>
            </a>
            <div class="navbar-nav ms-auto">
                <span id="system-status" class="status-indicator offline">
                    <span class="pulse"></span>
                    连接中...
                </span>
            </div>
        </div>
    </nav>

    <div class="main-container">
        <div class="row g-4">
            <div class="col-xl-2 col-lg-3">
                <div class="card sidebar-card">
                    <div class="card-body p-2">
                        <nav class="nav flex-column">
                            <a class="nav-link active" href="#" data-page="dashboard">
                                <i class="fas fa-tachometer-alt"></i> 仪表板
                            </a>
                            <a class="nav-link" href="#" data-page="trade">
                                <i class="fas fa-exchange-alt"></i> 手动交易
                            </a>
                            <a class="nav-link" href="#" data-page="signals">
                                <i class="fas fa-broadcast-tower"></i> 信号测试
                            </a>
                            <a class="nav-link" href="#" data-page="settings">
                                <i class="fas fa-cog"></i> 系统设置
                            </a>
                        </nav>
                    </div>
                </div>
            </div>
            
            <div class="col-xl-10 col-lg-9">
                <div id="main-content" class="fade-in">
                    <!-- 页面内容将通过 JavaScript 加载 -->
                </div>
            </div>
        </div>
    </div>

    <div id="toast-container" class="toast-container"></div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script src="/static/js/app_pro.js"></script>
</body>
</html>
"""
    
    def _dashboard_page(self):
        """仪表板页面"""
        return """
<div class="fade-in">
    <div class="row mb-4">
        <div class="col-md-3 mb-3 mb-md-0">
            <div class="stat-card info">
                <div class="stat-content">
                    <div class="stat-icon"><i class="fas fa-wallet"></i></div>
                    <div class="stat-value" id="account-balance">$0.00</div>
                    <div class="stat-label">账户余额</div>
                </div>
            </div>
        </div>
        <div class="col-md-3 mb-3 mb-md-0">
            <div class="stat-card success">
                <div class="stat-content">
                    <div class="stat-icon"><i class="fas fa-coins"></i></div>
                    <div class="stat-value" id="account-equity">$0.00</div>
                    <div class="stat-label">账户净值</div>
                </div>
            </div>
        </div>
        <div class="col-md-3 mb-3 mb-md-0">
            <div class="stat-card warning">
                <div class="stat-content">
                    <div class="stat-icon"><i class="fas fa-chart-pie"></i></div>
                    <div class="stat-value" id="account-profit">$0.00</div>
                    <div class="stat-label">浮动盈亏</div>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="stat-card success">
                <div class="stat-content">
                    <div class="stat-icon"><i class="fas fa-layer-group"></i></div>
                    <div class="stat-value" id="positions-count">0</div>
                    <div class="stat-label">持仓数量</div>
                </div>
            </div>
        </div>
    </div>
    
    <div class="row g-4 mb-4">
        <div class="col-xl-4 col-lg-5">
            <div class="card">
                <div class="card-header">
                    <h5 class="card-title mb-0"><i class="fas fa-tags"></i> 实时价格</h5>
                </div>
                <div class="card-body">
                    <div class="symbol-tags" id="symbol-selector">
                        <span class="symbol-tag active" data-symbol="XAUUSD">XAUUSD</span>
                        <span class="symbol-tag" data-symbol="EURUSD">EURUSD</span>
                        <span class="symbol-tag" data-symbol="GBPUSD">GBPUSD</span>
                        <span class="symbol-tag" data-symbol="USDJPY">USDJPY</span>
                        <span class="symbol-tag" data-symbol="BTCUSD">BTCUSD</span>
                    </div>
                    <div class="price-display">
                        <div class="symbol" id="current-symbol">XAUUSD</div>
                        <div class="price" id="current-price">--</div>
                        <div class="spread">
                            <div class="spread-item">
                                <span class="spread-label">买价</span>
                                <span class="spread-value bid" id="bid-price">--</span>
                            </div>
                            <div class="spread-item">
                                <span class="spread-label">卖价</span>
                                <span class="spread-value ask" id="ask-price">--</span>
                            </div>
                        </div>
                    </div>
                    
                    <div class="row g-2">
                        <div class="col-6">
                            <button class="btn btn-success w-100 btn-lg" onclick="quickTrade('buy')">
                                <i class="fas fa-arrow-up"></i> 做多
                            </button>
                        </div>
                        <div class="col-6">
                            <button class="btn btn-danger w-100 btn-lg" onclick="quickTrade('sell')">
                                <i class="fas fa-arrow-down"></i> 做空
                            </button>
                        </div>
                    </div>
                    <div class="row mt-3">
                        <div class="col-md-6">
                            <label class="form-label">手数</label>
                            <input type="number" class="form-control" id="quick-lot" value="0.1" step="0.01" min="0.01">
                        </div>
                        <div class="col-md-3">
                            <label class="form-label">止损点</label>
                            <input type="number" class="form-control" id="quick-sl" value="50">
                        </div>
                        <div class="col-md-3">
                            <label class="form-label">止盈点</label>
                            <input type="number" class="form-control" id="quick-tp" value="100">
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="col-xl-8 col-lg-7">
            <div class="card h-100">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <h5 class="card-title mb-0"><i class="fas fa-list"></i> 当前持仓</h5>
                    <button class="btn btn-danger btn-sm" onclick="closeAllPositions()">
                        <i class="fas fa-times-circle"></i> 全部平仓
                    </button>
                </div>
                <div class="card-body p-0">
                    <div class="table-responsive">
                        <table class="table table-hover mb-0">
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
                            <tbody id="positions-tbody">
                                <tr>
                                    <td colspan="9" class="text-center py-4 text-muted">
                                        <i class="fas fa-inbox fa-2x mb-2 d-block"></i>
                                        当前无持仓
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <div class="row g-4">
        <div class="col-lg-6">
            <div class="card">
                <div class="card-header">
                    <h5 class="card-title mb-0"><i class="fas fa-tasks"></i> 挂单列表</h5>
                </div>
                <div class="card-body p-0">
                    <div class="table-responsive">
                        <table class="table table-hover mb-0">
                            <thead>
                                <tr>
                                    <th>品种</th>
                                    <th>类型</th>
                                    <th>价格</th>
                                    <th>手数</th>
                                    <th>操作</th>
                                </tr>
                            </thead>
                            <tbody id="orders-tbody">
                                <tr>
                                    <td colspan="5" class="text-center py-4 text-muted">
                                        <i class="fas fa-inbox fa-2x mb-2 d-block"></i>
                                        当前无挂单
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
        <div class="col-lg-6">
            <div class="card">
                <div class="card-header">
                    <h5 class="card-title mb-0"><i class="fas fa-info-circle"></i> 系统信息</h5>
                </div>
                <div class="card-body">
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <div class="d-flex justify-content-between">
                                <span class="text-muted">版本</span>
                                <strong>2.0.0 Professional</strong>
                            </div>
                        </div>
                        <div class="col-md-6 mb-3">
                            <div class="d-flex justify-content-between">
                                <span class="text-muted">MT5 状态</span>
                                <strong id="mt5-status-badge">检查中...</strong>
                            </div>
                        </div>
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
<div class="fade-in">
    <h2 class="mb-4"><i class="fas fa-exchange-alt"></i> 手动交易</h2>
    
    <div class="row g-4">
        <div class="col-lg-6">
            <div class="card">
                <div class="card-header">
                    <h5 class="card-title mb-0"><i class="fas fa-chart-bar"></i> 市场信息</h5>
                </div>
                <div class="card-body">
                    <div class="mb-4">
                        <label class="form-label">选择品种</label>
                        <div class="symbol-tags" id="trade-symbol-selector">
                            <span class="symbol-tag active" data-symbol="XAUUSD">XAUUSD</span>
                            <span class="symbol-tag" data-symbol="EURUSD">EURUSD</span>
                            <span class="symbol-tag" data-symbol="GBPUSD">GBPUSD</span>
                            <span class="symbol-tag" data-symbol="USDJPY">USDJPY</span>
                            <span class="symbol-tag" data-symbol="BTCUSD">BTCUSD</span>
                        </div>
                    </div>
                    <div class="price-display">
                        <div class="symbol" id="trade-current-symbol">XAUUSD</div>
                        <div class="price" id="trade-current-price">--</div>
                        <div class="spread">
                            <div class="spread-item">
                                <span class="spread-label">买价</span>
                                <span class="spread-value bid" id="trade-bid">--</span>
                            </div>
                            <div class="spread-item">
                                <span class="spread-label">卖价</span>
                                <span class="spread-value ask" id="trade-ask">--</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="col-lg-6">
            <div class="card">
                <div class="card-header">
                    <h5 class="card-title mb-0"><i class="fas fa-sliders-h"></i> 交易设置</h5>
                </div>
                <div class="card-body">
                    <div class="order-type-selector mb-4">
                        <button class="btn active" id="btn-market" onclick="setOrderType('market')">
                            <i class="fas fa-bolt"></i> 市价单
                        </button>
                        <button class="btn" id="btn-limit" onclick="setOrderType('limit')">
                            <i class="fas fa-clock"></i> 限价单
                        </button>
                    </div>
                    
                    <div class="mb-3" id="limit-price-group" style="display: none;">
                        <label class="form-label">限价价格</label>
                        <input type="number" class="form-control" id="limit-price" step="0.01">
                    </div>
                    
                    <div class="mb-3">
                        <label class="form-label">交易手数</label>
                        <input type="number" class="form-control" id="trade-lot" value="0.1" step="0.01" min="0.01">
                    </div>
                    
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label">止损点数</label>
                            <input type="number" class="form-control" id="trade-sl" value="50">
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">止盈点数</label>
                            <input type="number" class="form-control" id="trade-tp" value="100">
                        </div>
                    </div>
                    
                    <div class="mb-3">
                        <label class="form-label">备注 (可选)</label>
                        <input type="text" class="form-control" id="trade-comment" placeholder="交易备注">
                    </div>
                    
                    <div class="row g-2">
                        <div class="col-md-6">
                            <button class="btn btn-success w-100 btn-lg" onclick="openPosition('buy')">
                                <i class="fas fa-arrow-up"></i> 做多 (Buy)
                            </button>
                        </div>
                        <div class="col-md-6">
                            <button class="btn btn-danger w-100 btn-lg" onclick="openPosition('sell')">
                                <i class="fas fa-arrow-down"></i> 做空 (Sell)
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
        """信号测试页面"""
        return """
<div class="fade-in">
    <h2 class="mb-4"><i class="fas fa-broadcast-tower"></i> 信号测试</h2>
    
    <div class="row g-4">
        <div class="col-lg-6">
            <div class="card">
                <div class="card-header">
                    <h5 class="card-title mb-0"><i class="fas fa-cube"></i> 发送测试信号</h5>
                </div>
                <div class="card-body">
                    <div class="mb-3">
                        <label class="form-label">策略名称</label>
                        <input type="text" class="form-control" id="signal-strategy" value="test_strategy">
                    </div>
                    <div class="mb-3">
                        <label class="form-label">操作方向</label>
                        <select class="form-select" id="signal-action">
                            <option value="buy">做多 (Buy)</option>
                            <option value="sell">做空 (Sell)</option>
                            <option value="close">平仓</option>
                            <option value="close_all">全部平仓</option>
                        </select>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">交易品种</label>
                        <select class="form-select" id="signal-symbol">
                            <option value="XAUUSD">XAUUSD (黄金)</option>
                            <option value="EURUSD">EURUSD</option>
                            <option value="GBPUSD">GBPUSD</option>
                            <option value="USDJPY">USDJPY</option>
                            <option value="BTCUSD">BTCUSD</option>
                        </select>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">手数</label>
                        <input type="number" class="form-control" id="signal-lot" value="0.1" step="0.01">
                    </div>
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label">止损点数</label>
                            <input type="number" class="form-control" id="signal-sl" value="50">
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">止盈点数</label>
                            <input type="number" class="form-control" id="signal-tp" value="100">
                        </div>
                    </div>
                    <button class="btn btn-primary w-100" onclick="sendTestSignal()">
                        <i class="fas fa-paper-plane"></i> 发送测试信号
                    </button>
                </div>
            </div>
        </div>
        
        <div class="col-lg-6">
            <div class="card">
                <div class="card-header">
                    <h5 class="card-title mb-0"><i class="fas fa-terminal"></i> 响应结果</h5>
                </div>
                <div class="card-body">
                    <div id="signal-result">
                        <div class="alert alert-info">
                            发送信号后，响应结果将显示在这里
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
"""
    
    def _settings_page(self):
        """设置页面"""
        return """
<div class="fade-in">
    <h2 class="mb-4"><i class="fas fa-cog"></i> 系统设置</h2>
    
    <div class="card mb-4">
        <div class="card-header">
            <h5 class="card-title mb-0"><i class="fas fa-sliders-h"></i> 交易参数</h5>
        </div>
        <div class="card-body">
            <div class="row">
                <div class="col-md-6 mb-3">
                    <label class="form-label">默认品种</label>
                    <select class="form-select" id="config-symbol">
                        <option value="XAUUSD">XAUUSD (黄金)</option>
                        <option value="EURUSD">EURUSD</option>
                        <option value="GBPUSD">GBPUSD</option>
                        <option value="USDJPY">USDJPY</option>
                        <option value="BTCUSD">BTCUSD</option>
                    </select>
                </div>
                <div class="col-md-6 mb-3">
                    <label class="form-label">默认手数</label>
                    <input type="number" class="form-control" id="config-lot" value="0.1" step="0.01">
                </div>
            </div>
            <div class="row">
                <div class="col-md-6 mb-3">
                    <label class="form-label">最大手数</label>
                    <input type="number" class="form-control" id="config-max-lot" value="1.0" step="0.1">
                </div>
                <div class="col-md-6 mb-3">
                    <label class="form-label">默认止损点数</label>
                    <input type="number" class="form-control" id="config-sl" value="50">
                </div>
            </div>
            <div class="row">
                <div class="col-md-6 mb-3">
                    <label class="form-label">默认止盈点数</label>
                    <input type="number" class="form-control" id="config-tp" value="100">
                </div>
                <div class="col-md-6 mb-3">
                    <div class="form-check mt-4">
                        <input class="form-check-input" type="checkbox" id="config-reverse" checked>
                        <label class="form-check-label">允许反向开仓 (自动平掉反向持仓)</label>
                    </div>
                </div>
            </div>
            <button class="btn btn-primary" onclick="saveConfig()">
                <i class="fas fa-save"></i> 保存设置
            </button>
        </div>
    </div>
    
    <div class="card">
        <div class="card-header">
            <h5 class="card-title mb-0"><i class="fas fa-info-circle"></i> 系统信息</h5>
        </div>
        <div class="card-body">
            <div class="row">
                <div class="col-md-6">
                    <div class="mb-2">
                        <strong>版本:</strong>
                        <span class="float-end">2.0.0 Professional</span>
                    </div>
                    <div class="mb-2">
                        <strong>框架:</strong>
                        <span class="float-end">FastAPI</span>
                    </div>
                    <div class="mb-2">
                        <strong>语言:</strong>
                        <span class="float-end">Python</span>
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="mb-2">
                        <strong>MT5 接口:</strong>
                        <span class="float-end">MetaTrader5 Python API</span>
                    </div>
                    <div class="mb-2">
                        <strong>Webhook:</strong>
                        <span class="float-end">/webhook (POST)</span>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
"""
