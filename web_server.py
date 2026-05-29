# Web 服务器模块 - 包含可视化界面
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from typing import Dict, Any
import os
import MetaTrader5 as mt5

from utils.logger import get_logger
from strategy_engine import StrategyEngine


class WebServer:
    """Web 服务器类 - 包含可视化界面"""
    
    def __init__(self, config: Dict[str, Any], strategy_engine: StrategyEngine, mt5_interface):
        """
        初始化 Web 服务器
        
        Args:
            config: 配置字典
            strategy_engine: 策略引擎实例
            mt5_interface: MT5 接口实例
        """
        self.config = config
        self.strategy_engine = strategy_engine
        self.mt5_interface = mt5_interface
        self.logger = get_logger()
        self.webhook_config = config.get('webhook', {})
        self.trading_config = config.get('trading', {})
        
        # 创建 FastAPI 应用
        self.app = FastAPI(title="黄金量化交易系统", version="2.0.0")
        
        # 挂载静态文件
        static_dir = os.path.join(os.path.dirname(__file__), "static")
        if os.path.exists(static_dir):
            self.app.mount("/static", StaticFiles(directory=static_dir), name="static")
        
        # 注册路由
        self._register_routes()
    
    def _register_routes(self):
        """注册所有路由"""
        
        @self.app.get("/", response_class=HTMLResponse)
        async def index(request: Request):
            """主页 - 仪表板"""
            return self._render_html("index.html")
        
        @self.app.get("/health")
        async def health_check():
            """健康检查"""
            return {"status": "healthy", "service": "gold-trading-bot"}
        
        # ========== API 路由 ==========
        
        @self.app.get("/api/status")
        async def get_status():
            """获取系统状态"""
            return {
                "mt5_connected": self.mt5_interface.check_connection() if self.mt5_interface else False
            }
        
        @self.app.get("/api/price")
        async def get_price():
            """获取当前价格"""
            symbol = self.trading_config.get('symbol', 'XAUUSD')
            price_info = self.mt5_interface.get_current_price(symbol) if self.mt5_interface else None
            if price_info:
                return {"bid": price_info[0], "ask": price_info[1]}
            return {"bid": None, "ask": None}
        
        @self.app.get("/api/account")
        async def get_account():
            """获取账户信息"""
            account_info = self.mt5_interface.get_account_info() if self.mt5_interface else None
            if account_info:
                return {
                    "balance": account_info.balance,
                    "equity": account_info.equity,
                    "profit": account_info.profit,
                    "margin": account_info.margin,
                    "margin_free": account_info.margin_free
                }
            return {"balance": 0, "equity": 0, "profit": 0}
        
        @self.app.get("/api/positions")
        async def get_positions():
            """获取当前持仓"""
            symbol = self.trading_config.get('symbol', 'XAUUSD')
            positions = self.mt5_interface.get_positions(symbol) if self.mt5_interface else []
            
            # 格式化持仓信息
            formatted_positions = []
            for pos in positions:
                formatted_positions.append({
                    "ticket": pos.ticket,
                    "symbol": pos.symbol,
                    "type": pos.type,
                    "volume": pos.volume,
                    "openPrice": pos.price_open,
                    "currentPrice": pos.price_current,
                    "profit": pos.profit,
                    "sl": pos.sl,
                    "tp": pos.tp
                })
            return formatted_positions
        
        @self.app.post("/api/trade")
        async def manual_trade(request: Request):
            """手动交易"""
            try:
                signal = await request.json()
                success, message, result = self.strategy_engine.process_signal(signal)
                
                if success:
                    return JSONResponse(
                        status_code=status.HTTP_200_OK,
                        content={"success": True, "message": message, "result": result}
                    )
                else:
                    return JSONResponse(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        content={"success": False, "message": message}
                    )
            except Exception as e:
                self.logger.error(f"手动交易出错: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/position/{ticket}/close")
        async def close_single_position(ticket: int):
            """平掉指定持仓"""
            try:
                result = self.mt5_interface.close_position(ticket) if self.mt5_interface else None
                if result:
                    return {"success": True, "message": "平仓成功"}
                else:
                    return JSONResponse(
                        status_code=400,
                        content={"success": False, "message": "平仓失败"}
                    )
            except Exception as e:
                self.logger.error(f"平仓出错: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/positions/close-all")
        async def close_all_positions_api():
            """平掉所有持仓"""
            try:
                symbol = self.trading_config.get('symbol')
                count = self.mt5_interface.close_all_positions(symbol) if self.mt5_interface else 0
                return {"success": True, "message": f"平掉 {count} 个持仓", "count": count}
            except Exception as e:
                self.logger.error(f"全部平仓出错: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/config")
        async def get_config():
            """获取当前配置"""
            return {
                "trading": self.trading_config
            }
        
        @self.app.post("/api/config")
        async def update_config(request: Request):
            """更新配置（内存中）"""
            try:
                new_config = await request.json()
                if 'trading' in new_config:
                    self.trading_config.update(new_config['trading'])
                return {"success": True, "message": "配置已更新"}
            except Exception as e:
                self.logger.error(f"更新配置出错: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/page/{page_name}")
        async def get_page_content(page_name: str):
            """获取页面内容"""
            return HTMLResponse(content=self._get_page_template(page_name))
        
        # ========== Webhook 路由 ==========
        
        @self.app.post("/webhook")
        async def webhook(request: Request):
            """处理 TradingView Webhook 信号"""
            try:
                signal = await request.json()
                self.logger.info(f"收到 Webhook 请求: {signal}")
                
                success, message, result = self.strategy_engine.process_signal(signal)
                
                if success:
                    return JSONResponse(
                        status_code=status.HTTP_200_OK,
                        content={"success": True, "message": message, "result": result}
                    )
                else:
                    return JSONResponse(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        content={"success": False, "message": message}
                    )
            except Exception as e:
                self.logger.error(f"处理 Webhook 出错: {e}")
                raise HTTPException(status_code=500, detail=str(e))
    
    def _render_html(self, template_name: str) -> str:
        """渲染主 HTML 页面"""
        return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>黄金量化交易系统</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <link href="/static/css/style.css" rel="stylesheet">
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark">
        <div class="container-fluid">
            <a class="navbar-brand" href="#">
                <i class="fas fa-chart-line"></i>
                黄金量化交易系统
            </a>
            <div class="navbar-nav ms-auto">
                <span id="system-status" class="status-indicator offline mx-3">
                    <span class="pulse"></span> 正在连接...
                </span>
            </div>
        </div>
    </nav>

    <div class="main-container">
        <div class="row">
            <div class="col-md-2 mb-4">
                <div class="card">
                    <div class="card-body p-0">
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
            
            <div class="col-md-10">
                <div id="main-content" class="fade-in">
                    <!-- 页面内容将通过 JavaScript 加载 -->
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script src="/static/js/app.js"></script>
</body>
</html>
"""
    
    def _get_page_template(self, page_name: str) -> str:
        """获取页面模板"""
        
        pages = {
            'dashboard': self._dashboard_template(),
            'trade': self._trade_template(),
            'signals': self._signals_template(),
            'settings': self._settings_template()
        }
        
        return pages.get(page_name, self._dashboard_template())
    
    def _dashboard_template(self) -> str:
        """仪表板页面"""
        return """
<div class="fade-in">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <h2><i class="fas fa-tachometer-alt"></i> 仪表板</h2>
    </div>
    
    <div class="row mb-4">
        <div class="col-md-3 mb-3">
            <div class="stat-card info">
                <div class="stat-icon"><i class="fas fa-wallet"></i></div>
                <div class="stat-value" id="account-balance">$0.00</div>
                <div class="stat-label">账户余额</div>
            </div>
        </div>
        <div class="col-md-3 mb-3">
            <div class="stat-card success">
                <div class="stat-icon"><i class="fas fa-coins"></i></div>
                <div class="stat-value" id="account-equity">$0.00</div>
                <div class="stat-label">净值</div>
            </div>
        </div>
        <div class="col-md-3 mb-3">
            <div class="stat-card warning">
                <div class="stat-icon"><i class="fas fa-chart-pie"></i></div>
                <div class="stat-value" id="account-profit">$0.00</div>
                <div class="stat-label">浮动盈亏</div>
            </div>
        </div>
        <div class="col-md-3 mb-3">
            <div class="stat-card success">
                <div class="stat-icon"><i class="fas fa-layer-group"></i></div>
                <div class="stat-value" id="positions-count">0</div>
                <div class="stat-label">持仓数量</div>
            </div>
        </div>
    </div>
    
    <div class="card mb-4">
        <div class="card-header d-flex justify-content-between align-items-center">
            <h5 class="mb-0"><i class="fas fa-list"></i> 当前持仓</h5>
            <button class="btn btn-sm btn-danger" onclick="closeAllPositions()">
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
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    
    <div class="row">
        <div class="col-md-6">
            <div class="card">
                <div class="card-header">
                    <h5 class="mb-0"><i class="fas fa-tags"></i> 当前价格</h5>
                </div>
                <div class="card-body">
                    <div class="price-display">
                        <div class="symbol">XAUUSD</div>
                        <div class="price" id="current-price">--</div>
                        <div class="spread">
                            买价: <span id="bid-price">--</span> | 卖价: <span id="ask-price">--</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        <div class="col-md-6">
            <div class="card">
                <div class="card-header">
                    <h5 class="mb-0"><i class="fas fa-bolt"></i> 快速交易</h5>
                </div>
                <div class="card-body">
                    <div class="row g-2">
                        <div class="col-md-6">
                            <button class="btn btn-success w-100 btn-lg" onclick="openPosition('buy')">
                                <i class="fas fa-arrow-up"></i> 做多
                            </button>
                        </div>
                        <div class="col-md-6">
                            <button class="btn btn-danger w-100 btn-lg" onclick="openPosition('sell')">
                                <i class="fas fa-arrow-down"></i> 做空
                            </button>
                        </div>
                    </div>
                    <div class="row mt-3">
                        <div class="col-md-4">
                            <label class="form-label">手数</label>
                            <input type="number" class="form-control" id="quick-lot" value="0.1" step="0.01" min="0.01">
                        </div>
                        <div class="col-md-4">
                            <label class="form-label">止损点数</label>
                            <input type="number" class="form-control" id="quick-sl" value="50" step="10">
                        </div>
                        <div class="col-md-4">
                            <label class="form-label">止盈点数</label>
                            <input type="number" class="form-control" id="quick-tp" value="100" step="10">
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
"""
    
    def _trade_template(self) -> str:
        """手动交易页面"""
        return """
<div class="fade-in">
    <h2 class="mb-4"><i class="fas fa-exchange-alt"></i> 手动交易</h2>
    
    <div class="row">
        <div class="col-md-6">
            <div class="card">
                <div class="card-header">
                    <h5 class="mb-0"><i class="fas fa-chart-bar"></i> 市场信息</h5>
                </div>
                <div class="card-body">
                    <div class="price-display mb-4">
                        <div class="symbol">XAUUSD</div>
                        <div class="price" id="current-price">--</div>
                        <div class="spread">
                            买价: <span id="bid-price">--</span> | 卖价: <span id="ask-price">--</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="col-md-6">
            <div class="card">
                <div class="card-header">
                    <h5 class="mb-0"><i class="fas fa-sliders-h"></i> 交易设置</h5>
                </div>
                <div class="card-body">
                    <div class="mb-3">
                        <label class="form-label">交易品种</label>
                        <select class="form-select" id="trade-symbol">
                            <option value="XAUUSD">XAUUSD (黄金)</option>
                        </select>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">手数</label>
                        <input type="number" class="form-control" id="trade-lot" value="0.1" step="0.01" min="0.01">
                    </div>
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label">止损点数</label>
                            <input type="number" class="form-control" id="trade-sl" value="50" step="10">
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">止盈点数</label>
                            <input type="number" class="form-control" id="trade-tp" value="100" step="10">
                        </div>
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
    
    def _signals_template(self) -> str:
        """信号测试页面"""
        return """
<div class="fade-in">
    <h2 class="mb-4"><i class="fas fa-broadcast-tower"></i> 信号测试</h2>
    
    <div class="row">
        <div class="col-md-6">
            <div class="card">
                <div class="card-header">
                    <h5 class="mb-0"><i class="fas fa-cube"></i> 发送测试信号</h5>
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
                        <label class="form-label">品种</label>
                        <input type="text" class="form-control" id="signal-symbol" value="XAUUSD">
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
        
        <div class="col-md-6">
            <div class="card">
                <div class="card-header">
                    <h5 class="mb-0"><i class="fas fa-terminal"></i> 响应结果</h5>
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
    
    def _settings_template(self) -> str:
        """设置页面"""
        return """
<div class="fade-in">
    <h2 class="mb-4"><i class="fas fa-cog"></i> 系统设置</h2>
    
    <div class="card mb-4">
        <div class="card-header">
            <h5 class="mb-0"><i class="fas fa-sliders-h"></i> 交易参数</h5>
        </div>
        <div class="card-body">
            <div class="row">
                <div class="col-md-6 mb-3">
                    <label class="form-label">默认交易品种</label>
                    <input type="text" class="form-control" id="config-symbol" value="XAUUSD">
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
                    <input type="number" class="form-control" id="config-sl" value="50" step="10">
                </div>
            </div>
            <div class="row">
                <div class="col-md-6 mb-3">
                    <label class="form-label">默认止盈点数</label>
                    <input type="number" class="form-control" id="config-tp" value="100" step="10">
                </div>
                <div class="col-md-6 mb-3">
                    <div class="form-check mt-4">
                        <input class="form-check-input" type="checkbox" id="config-reverse" checked>
                        <label class="form-check-label">允许反向开仓（自动平掉反向持仓）</label>
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
            <h5 class="mb-0"><i class="fas fa-info-circle"></i> 系统信息</h5>
        </div>
        <div class="card-body">
            <div class="row">
                <div class="col-md-6">
                    <p><strong>版本:</strong> 2.0.0</p>
                    <p><strong>框架:</strong> FastAPI</p>
                </div>
                <div class="col-md-6">
                    <p><strong>编程语言:</strong> Python</p>
                    <p><strong>MT5 接口:</strong> MetaTrader5 Python API</p>
                </div>
            </div>
        </div>
    </div>
</div>
"""
