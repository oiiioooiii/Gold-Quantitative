// ============================================
// GOLD TRADING BOT - ENTERPRISE EDITION
// 企业级实时交易系统 JavaScript
// ============================================

class TradingWebSocket {
    constructor() {
        this.ws = null;
        this.reconnectInterval = 5000;
        this.pingInterval = null;
        this.lastPrice = null;
        this.currentSymbol = 'XAUUSD';
        this.klineUpdateInterval = null;
        this.klineChart = null;
        this.currentTimeframe = 'H1';
        this.klineData = [];
        this.crosshairTimer = null;
        
        this.init();
    }
    
    init() {
        this.connect();
        this.initNavigation();
        this.startServerTime();
    }
    
    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;
        
        try {
            this.ws = new WebSocket(wsUrl);
            
            this.ws.onopen = () => {
                console.log('WebSocket连接成功');
                this.updateConnectionStatus(true);
                this.send({ type: 'get_data' });
                this.startPing();
            };
            
            this.ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.handleMessage(data);
            };
            
            this.ws.onclose = () => {
                console.log('WebSocket连接断开');
                this.updateConnectionStatus(false);
                this.stopPing();
                setTimeout(() => this.connect(), this.reconnectInterval);
            };
            
            this.ws.onerror = (error) => {
                console.error('WebSocket错误:', error);
            };
            
        } catch (error) {
            console.error('WebSocket连接失败:', error);
            setTimeout(() => this.connect(), this.reconnectInterval);
        }
    }
    
    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        }
    }
    
    startPing() {
        this.pingInterval = setInterval(() => {
            this.send({ type: 'ping' });
        }, 30000);
    }
    
    stopPing() {
        if (this.pingInterval) {
            clearInterval(this.pingInterval);
            this.pingInterval = null;
        }
    }
    
    updateConnectionStatus(connected) {
        const statusEl = document.getElementById('connection-status');
        if (statusEl) {
            if (connected) {
                statusEl.className = 'badge connected';
                statusEl.innerHTML = '<i class="fas fa-circle"></i> 已连接';
            } else {
                statusEl.className = 'badge bg-danger';
                statusEl.innerHTML = '<i class="fas fa-circle"></i> 连接断开';
            }
        }
    }
    
    handleMessage(data) {
        switch (data.type) {
            case 'connected':
                showToast(data.message, 'success');
                break;
                
            case 'pong':
                // 心跳响应
                break;
                
            case 'initial_data':
                this.updateAllData(data.data);
                break;
                
            case 'update':
                this.updateAllData(data.data);
                break;
        }
    }
    
    updateAllData(data) {
        // 更新账户信息
        this.updateAccount(data.account);
        
        // 更新持仓
        this.updatePositions(data.positions);
        
        // 更新价格
        if (data.price) {
            this.updatePrice(data.price);
        }
        
        if (data.kline && data.indicators) {
            this.updateAllCharts(data.kline, data.indicators);
        }
        
        // 更新持仓数量
        const countEl = document.getElementById('positions-count');
        if (countEl) {
            countEl.textContent = data.positions_count || 0;
        }
    }
    
    updateOHLC(ohlc) {
        const openEl = document.getElementById('ohlc-open');
        const highEl = document.getElementById('ohlc-high');
        const lowEl = document.getElementById('ohlc-low');
        const closeEl = document.getElementById('ohlc-close');
        const volumeEl = document.getElementById('ohlc-volume');
        
        if (openEl) openEl.textContent = ohlc.open ? ohlc.open.toFixed(2) : '--';
        if (highEl) highEl.textContent = ohlc.high ? ohlc.high.toFixed(2) : '--';
        if (lowEl) lowEl.textContent = ohlc.low ? ohlc.low.toFixed(2) : '--';
        
        if (closeEl) {
            closeEl.textContent = ohlc.close ? ohlc.close.toFixed(2) : '--';
            // 根据涨跌设置颜色
            if (ohlc.close !== undefined && ohlc.open !== undefined) {
                closeEl.classList.remove('text-info', 'text-success', 'text-danger');
                if (ohlc.close >= ohlc.open) {
                    closeEl.classList.add('text-success');
                } else {
                    closeEl.classList.add('text-danger');
                }
            }
        }
        
        if (volumeEl) volumeEl.textContent = ohlc.volume ? ohlc.volume.toLocaleString() : '--';
    }
    
    updateAccount(account) {
        const balanceEl = document.getElementById('account-balance');
        const equityEl = document.getElementById('account-equity');
        const profitEl = document.getElementById('account-profit');
        
        if (balanceEl && account.balance !== undefined) {
            balanceEl.textContent = '$' + account.balance.toLocaleString('en-US', {minimumFractionDigits: 2});
        }
        
        if (equityEl && account.equity !== undefined) {
            equityEl.textContent = '$' + account.equity.toLocaleString('en-US', {minimumFractionDigits: 2});
        }
        
        if (profitEl && account.profit !== undefined) {
            const profit = account.profit;
            profitEl.textContent = (profit >= 0 ? '+$' : '-$') + Math.abs(profit).toLocaleString('en-US', {minimumFractionDigits: 2});
            
            if (profit >= 0) {
                profitEl.parentElement.className = 'card-body';
            } else {
                profitEl.parentElement.className = 'card-body';
            }
        }
    }
    
    updatePositions(positions) {
        const tbody = document.getElementById('positions-table');
        if (!tbody) return;
        
        if (!positions || positions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted py-4">暂无持仓</td></tr>';
            return;
        }
        
        tbody.innerHTML = positions.map(pos => `
            <tr>
                <td><strong>${pos.symbol}</strong></td>
                <td>
                    <span class="badge ${pos.type === 'long' ? 'badge-long' : 'badge-short'}">
                        ${pos.type === 'long' ? '做多' : '做空'}
                    </span>
                </td>
                <td>${pos.volume}</td>
                <td>${pos.open_price}</td>
                <td>${pos.current_price}</td>
                <td class="${pos.profit >= 0 ? 'profit-positive' : 'profit-negative'}">
                    ${pos.profit >= 0 ? '+' : ''}$${pos.profit.toFixed(2)}
                </td>
                <td>${pos.sl || '-'}</td>
                <td>${pos.tp || '-'}</td>
                <td>
                    <button class="btn btn-sm btn-danger" onclick="closePosition(${pos.ticket})">
                        平仓
                    </button>
                </td>
            </tr>
        `).join('');
    }
    
    updatePrice(price) {
        if (!price || !price.ask) return;
        
        const priceEl = document.getElementById('price-value');
        const bidEl = document.getElementById('price-bid');
        const askEl = document.getElementById('price-ask');
        const tradePriceEl = document.getElementById('trade-price');
        const tradeBidEl = document.getElementById('trade-bid');
        const tradeAskEl = document.getElementById('trade-ask');
        
        if (priceEl) {
            const newPrice = price.ask.toFixed(2);
            priceEl.textContent = newPrice;
            
            if (this.lastPrice !== null) {
                priceEl.classList.remove('price-up', 'price-down');
                if (parseFloat(newPrice) > this.lastPrice) {
                    priceEl.classList.add('price-up');
                } else if (parseFloat(newPrice) < this.lastPrice) {
                    priceEl.classList.add('price-down');
                }
                setTimeout(() => priceEl.classList.remove('price-up', 'price-down'), 500);
            }
            this.lastPrice = parseFloat(newPrice);
        }
        
        if (bidEl) bidEl.textContent = price.bid ? price.bid.toFixed(2) : '--';
        if (askEl) askEl.textContent = price.ask ? price.ask.toFixed(2) : '--';
        if (tradePriceEl) tradePriceEl.textContent = price.ask ? price.ask.toFixed(2) : '--';
        if (tradeBidEl) tradeBidEl.textContent = price.bid ? price.bid.toFixed(2) : '--';
        if (tradeAskEl) tradeAskEl.textContent = price.ask ? price.ask.toFixed(2) : '--';
    }
    
    initNavigation() {
        document.querySelectorAll('.list-group-item').forEach(item => {
            item.addEventListener('click', (e) => {
                e.preventDefault();
                const page = item.getAttribute('data-page');
                
                document.querySelectorAll('.list-group-item').forEach(i => i.classList.remove('active'));
                item.classList.add('active');
                
                this.loadPage(page);
            });
        });
    }
    
    loadPage(page) {
        fetch(`/api/page/${page}`)
            .then(response => response.text())
            .then(html => {
                // 清理旧图表
                this.cleanupCharts();
                
                document.getElementById('main-content').innerHTML = html;
                
                if (page === 'trade') {
                    this.initTradePage();
                    this.stopKlineUpdate();
                }
                
                if (page === 'dashboard') {
                    // 初始化K线图
                    setTimeout(() => {
                        this.initKlineChart();
                        // 加载初始数据
                        this.loadCandlesForChart();
                    }, 100);
                }
                
                if (page === 'llm-history') {
                    // 初始化历史记录页面
                    setTimeout(() => {
                        initLLMHistoryPage();
                    }, 100);
                }
            })
            .catch(error => {
                console.error('加载页面失败:', error);
                showToast('加载页面失败', 'error');
            });
    }
    
    initKlineChart() {
        const mainChartDom = document.getElementById('kline-chart');
        const volumeChartDom = document.getElementById('volume-chart');
        
        if (!mainChartDom || !volumeChartDom) return;
        
        // 清理旧图表
        this.cleanupCharts();
        
        // 检查库是否加载
        if (typeof LightweightCharts === 'undefined') {
            console.error('LightweightCharts not loaded');
            showToast('图表库加载失败', 'error');
            return;
        }
        
        try {
            // 图表配置
            const chartConfig = {
                layout: {
                    backgroundColor: '#1a1a2e',
                    textColor: '#ddd',
                },
                grid: {
                    vertLines: { color: '#2a2a44' },
                    horzLines: { color: '#2a2a44' },
                },
                rightPriceScale: {
                    borderColor: '#485c7b',
                },
                timeScale: {
                    borderColor: '#485c7b',
                    timeVisible: true,
                    secondsVisible: false,
                },
            };
            
            // ========== 主K线图 ==========
            this.mainChart = LightweightCharts.createChart(mainChartDom, chartConfig);
            
            this.candlestickSeries = this.mainChart.addCandlestickSeries({
                upColor: '#14b8a6',
                downColor: '#f87171',
                borderDownColor: '#f87171',
                borderUpColor: '#14b8a6',
                wickDownColor: '#f87171',
                wickUpColor: '#14b8a6',
            });
            
            // ========== 成交量图 ==========
            this.volumeChart = LightweightCharts.createChart(volumeChartDom, {
                ...chartConfig,
                timeScale: { ...chartConfig.timeScale, timeVisible: false },
            });
            
            this.volumeSeries = this.volumeChart.addHistogramSeries({
                priceFormat: { type: 'volume' },
            });
            
            // MA5
            this.ma5Series = this.mainChart.addLineSeries({
                color: '#FFD700',
                lineWidth: 1,
            });
            
            // MA10
            this.ma10Series = this.mainChart.addLineSeries({
                color: '#FF69B4',
                lineWidth: 1,
            });
            
            // MA20
            this.ma20Series = this.mainChart.addLineSeries({
                color: '#00BFFF',
                lineWidth: 1,
            });
            
            // 响应式调整
            const resizeHandler = () => {
                if (this.mainChart) {
                    this.mainChart.applyOptions({
                        width: mainChartDom.clientWidth,
                        height: mainChartDom.clientHeight
                    });
                }
            };
            
            window.addEventListener('resize', resizeHandler);
            this._resizeHandler = resizeHandler;
            
            // 同步所有图表的时间轴 - 更彻底的同步
            const syncTimeScale = (sourceChart, targetCharts) => {
                sourceChart.timeScale().subscribeVisibleLogicalRangeChange(() => {
                    const logicalRange = sourceChart.timeScale().getVisibleLogicalRange();
                    if (logicalRange) {
                        targetCharts.forEach(chart => {
                            chart.timeScale().setVisibleLogicalRange(logicalRange);
                        });
                    }
                });
            };
            
            // 主图和成交量图双向同步
            syncTimeScale(this.mainChart, [this.volumeChart]);
            
            // 监听十字线移动显示K线详细信息
            this.mainChart.subscribeCrosshairMove((param) => {
                if (this.crosshairTimer) {
                    clearTimeout(this.crosshairTimer);
                }
                
                this.crosshairTimer = setTimeout(() => {
                    if (param.time && this.klineData.length > 0) {
                        this.showKlineInfoByTime(param.time, param.point);
                    } else {
                        this.hideKlineInfo();
                    }
                }, 50);
            });
            
            // 监听鼠标移动更新tooltip位置
            if (mainChartDom) {
                mainChartDom.addEventListener('mousemove', (e) => {
                    this.lastMouseX = e.clientX;
                    this.lastMouseY = e.clientY;
                    this.updateTooltipPosition();
                });
                
                mainChartDom.addEventListener('mouseleave', () => {
                    this.hideKlineInfo();
                });
            }
            
            // 等待WebSocket推送数据，不需要手动加载
            
        } catch (error) {
            console.error('初始化图表失败:', error);
            showToast('图表初始化失败', 'error');
        }
    }
    
    loadIndicatorsForChart() {
        // 不再需要，WebSocket会自动推送数据
    }
    
    updateAllCharts(candles, indicators) {
        if (!this.mainChart || !this.candlestickSeries) return;
        
        this.klineData = candles;
        
        // 转换时间
        const times = candles.map(c => this.convertTime(c.time));
        
        // ========== 更新主K线图 ==========
        const klineData = candles.map((c, i) => ({
            time: times[i],
            open: c.open,
            high: c.high,
            low: c.low,
            close: c.close,
        }));
        
        const volumeData = candles.map((c, i) => ({
            time: times[i],
            value: c.volume || 0,
            color: c.close >= c.open ? '#14b8a6' : '#f87171',
        }));
        
        // MA数据
        const ma5Data = indicators.ma5.map((val, i) => ({
            time: times[i],
            value: val
        })).filter(d => d.value !== null);
        
        const ma10Data = indicators.ma10.map((val, i) => ({
            time: times[i],
            value: val
        })).filter(d => d.value !== null);
        
        const ma20Data = indicators.ma20.map((val, i) => ({
            time: times[i],
            value: val
        })).filter(d => d.value !== null);
        
        this.candlestickSeries.setData(klineData);
        this.ma5Series.setData(ma5Data);
        this.ma10Series.setData(ma10Data);
        this.ma20Series.setData(ma20Data);
        
        // 更新成交量图
        if (this.volumeSeries) {
            this.volumeSeries.setData(volumeData);
        }
        
        // ========== 更新图表时间轴 ==========
        setTimeout(() => {
            // 让主图适应内容
            this.mainChart.timeScale().fitContent();
            
            // 让成交量图也适应内容并同步范围
            const otherCharts = [this.volumeChart];
            
            // 延迟一下再获取可见范围，确保数据已加载
            setTimeout(() => {
                const range = this.mainChart.timeScale().getVisibleRange();
                if (range) {
                    otherCharts.forEach(chart => {
                        if (chart) {
                            chart.timeScale().fitContent();
                            chart.timeScale().setVisibleRange(range);
                        }
                    });
                }
            }, 100);
        }, 50);
    }
    
    convertTime(timeStr) {
        const d = new Date(timeStr);
        return Math.floor(d.getTime() / 1000);
    }
    
    cleanupCharts() {
        if (this._resizeHandler) {
            window.removeEventListener('resize', this._resizeHandler);
            this._resizeHandler = null;
        }
        
        const charts = [
            this.mainChart,
            this.volumeChart,
            this.macdChart,
            this.rsiChart,
            this.kdjChart
        ];
        
        charts.forEach(chart => {
            if (chart) {
                try { chart.remove(); } catch (e) {}
            }
        });
        
        this.mainChart = null;
        this.macdChart = null;
        this.rsiChart = null;
        this.kdjChart = null;
        this.candlestickSeries = null;
        this.volumeSeries = null;
    }
    
    startKlineUpdate() {
        // 不再需要HTTP轮询
    }
    
    stopKlineUpdate() {
        // 不再需要HTTP轮询
    }
    
    initTradePage() {
        const orderTypeSelect = document.getElementById('order-type');
        const limitPriceGroup = document.getElementById('limit-price-group');
        
        if (orderTypeSelect) {
            orderTypeSelect.addEventListener('change', () => {
                if (limitPriceGroup) {
                    limitPriceGroup.style.display = orderTypeSelect.value === 'limit' ? 'block' : 'none';
                }
            });
        }
    }
    
    startServerTime() {
        const timeEl = document.getElementById('server-time');
        if (timeEl) {
            setInterval(() => {
                const now = new Date();
                timeEl.textContent = now.toLocaleTimeString('zh-CN');
            }, 1000);
        }
    }
    
    // 切换K线周期
    async changeTimeframe(timeframe) {
        this.currentTimeframe = timeframe;
        showToast(`正在切换到 ${timeframe} 周期...`, 'info');
        
        try {
            const response = await fetch(`/api/indicators/XAUUSD/${timeframe}?count=200`);
            const result = await response.json();
            
            if (result.success && result.candles) {
                this.updateAllCharts(result.candles, result.indicators);
                showToast(`已切换到 ${timeframe} 周期`, 'success');
            } else {
                showToast('获取数据失败', 'error');
            }
        } catch (error) {
            console.error('切换周期失败:', error);
            showToast('切换周期失败', 'error');
        }
    }

    // 加载K线数据
    async loadCandlesForChart() {
        const timeframe = this.currentTimeframe || 'H1';
        showToast(`正在刷新 ${timeframe} 周期数据...`, 'info');
        
        try {
            const response = await fetch(`/api/indicators/XAUUSD/${timeframe}?count=200`);
            const result = await response.json();
            
            if (result.success && result.candles) {
                this.updateAllCharts(result.candles, result.indicators);
                showToast('数据刷新成功', 'success');
            } else {
                showToast('获取数据失败', 'error');
            }
        } catch (error) {
            console.error('加载数据失败:', error);
            showToast('加载数据失败', 'error');
        }
    }
    
    // 根据时间显示K线详细信息
    showKlineInfoByTime(time, point) {
        const tooltip = document.getElementById('kline-tooltip');
        if (!tooltip || this.klineData.length === 0) return;
        
        // 找到时间匹配或最近的K线
        let targetKline = null;
        let minDiff = Infinity;
        
        for (const kline of this.klineData) {
            const klineTime = this.convertTime(kline.time);
            const diff = Math.abs(klineTime - time);
            if (diff < minDiff) {
                minDiff = diff;
                targetKline = kline;
            }
        }
        
        if (targetKline) {
            if (point) {
                this.lastMouseX = point.x;
                this.lastMouseY = point.y;
            }
            this.showKlineInfo(targetKline);
        }
    }
    
    // 显示K线详细信息
    showKlineInfo(kline) {
        const tooltip = document.getElementById('kline-tooltip');
        if (!tooltip) return;
        
        const openEl = document.getElementById('tt-open');
        const highEl = document.getElementById('tt-high');
        const lowEl = document.getElementById('tt-low');
        const closeEl = document.getElementById('tt-close');
        const changeEl = document.getElementById('tt-change');
        const changePercentEl = document.getElementById('tt-change-percent');
        const amplitudeEl = document.getElementById('tt-amplitude');
        const volumeEl = document.getElementById('tt-volume');
        
        if (!openEl) return;
        
        // 计算数值
        const change = kline.close - kline.open;
        const changePercent = (change / kline.open) * 100;
        const amplitude = ((kline.high - kline.low) / kline.open) * 100;
        
        // 设置数值
        openEl.textContent = kline.open.toFixed(2);
        highEl.textContent = kline.high.toFixed(2);
        lowEl.textContent = kline.low.toFixed(2);
        closeEl.textContent = kline.close.toFixed(2);
        
        // 涨跌颜色
        const isUp = kline.close >= kline.open;
        changeEl.textContent = (change >= 0 ? '+' : '') + change.toFixed(2);
        changeEl.style.color = isUp ? '#14b8a6' : '#f87171';
        
        changePercentEl.textContent = (changePercent >= 0 ? '+' : '') + changePercent.toFixed(2) + '%';
        changePercentEl.style.color = isUp ? '#14b8a6' : '#f87171';
        
        amplitudeEl.textContent = amplitude.toFixed(2) + '%';
        volumeEl.textContent = kline.volume?.toLocaleString() || '0';
        
        tooltip.style.display = 'block';
        this.updateTooltipPosition();
    }
    
    // 更新tooltip位置
    updateTooltipPosition() {
        const tooltip = document.getElementById('kline-tooltip');
        if (!tooltip || tooltip.style.display === 'none' || this.lastMouseX === undefined) return;
        
        // 防止tooltip超出屏幕
        let left = this.lastMouseX + 20;
        let top = this.lastMouseY + 20;
        
        const tooltipRect = tooltip.getBoundingClientRect();
        if (left + tooltipRect.width > window.innerWidth) {
            left = this.lastMouseX - tooltipRect.width - 20;
        }
        if (top + tooltipRect.height > window.innerHeight) {
            top = this.lastMouseY - tooltipRect.height - 20;
        }
        
        tooltip.style.left = left + 'px';
        tooltip.style.top = top + 'px';
    }
    
    // 隐藏K线信息
    hideKlineInfo() {
        const tooltip = document.getElementById('kline-tooltip');
        if (tooltip) {
            tooltip.style.display = 'none';
        }
    }
}

// ========== 交易函数 ==========

let wsClient = null;

// 全局函数，用于刷新图表
function loadCandlesForChart() {
    if (wsClient && wsClient.loadCandlesForChart) {
        wsClient.loadCandlesForChart();
    }
}

document.addEventListener('DOMContentLoaded', () => {
    wsClient = new TradingWebSocket();
    
    // 初始化后加载仪表板
    setTimeout(() => {
        wsClient.loadPage('dashboard');
    }, 100);
});

function quickTrade(action) {
    const lotInput = document.getElementById('quick-lot');
    const slInput = document.getElementById('quick-sl');
    const tpInput = document.getElementById('quick-tp');
    
    const lot = parseFloat(lotInput?.value) || 0.1;
    const sl = parseInt(slInput?.value) || 50;
    const tp = parseInt(tpInput?.value) || 100;
    
    executeTradeRequest(action, lot, sl, tp);
}

function executeTrade(action) {
    const lotInput = document.getElementById('trade-lot');
    const slInput = document.getElementById('trade-sl');
    const tpInput = document.getElementById('trade-tp');
    
    const lot = parseFloat(lotInput?.value) || 0.1;
    const sl = parseInt(slInput?.value) || 50;
    const tp = parseInt(tpInput?.value) || 100;
    const orderType = document.getElementById('order-type')?.value || 'market';
    const limitPrice = document.getElementById('limit-price')?.value;
    
    executeTradeRequest(action, lot, sl, tp, orderType, limitPrice);
}

async function executeTradeRequest(action, lot, sl, tp, orderType = 'market', limitPrice = null) {
    const data = {
        action: action,
        symbol: wsClient?.currentSymbol || 'XAUUSD',
        lot: parseFloat(lot),
        sl_points: parseInt(sl),
        tp_points: parseInt(tp),
        order_type: orderType,
        comment: 'Manual Trade'
    };
    
    if (orderType === 'limit' && limitPrice) {
        data.limit_price = parseFloat(limitPrice);
    }
    
    const actionName = action.toUpperCase() === 'BUY' ? '做多' : '做空';
    const orderTypeName = orderType === 'limit' ? '限价单' : '市价单';
    
    showToast(`正在提交 ${actionName} 订单...`, 'info');
    
    try {
        const response = await fetch('/api/trade', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        
        if (response.ok && result.success) {
            const orderInfo = result.result || {};
            showToast(`${actionName}成功! ${orderTypeName} ${lot}手, 止损${sl}点, 止盈${tp}点`, 'success');
        } else {
            showToast(`${actionName}失败: ${result.message || '未知错误'}`, 'error');
        }
    } catch (error) {
        showToast('网络请求失败，请检查连接', 'error');
    }
}

async function closePosition(ticket) {
    showToast('正在平仓...', 'info');
    
    try {
        const response = await fetch(`/api/position/${ticket}/close`, {
            method: 'POST'
        });
        
        const result = await response.json();
        
        if (response.ok && result.success) {
            showToast('平仓成功!', 'success');
        } else {
            showToast(`平仓失败: ${result.message || '未知错误'}`, 'error');
        }
    } catch (error) {
        showToast('网络请求失败，请检查连接', 'error');
    }
}

async function closeAllPositions() {
    showToast('正在全部平仓...', 'info');
    
    try {
        const response = await fetch('/api/positions/close-all', {
            method: 'POST'
        });
        
        const result = await response.json();
        
        if (response.ok && result.success) {
            const closedCount = result.count || 0;
            showToast(`全部平仓成功! 共平掉 ${closedCount} 个持仓`, 'success');
        } else {
            showToast(`全部平仓失败: ${result.message || '未知错误'}`, 'error');
        }
    } catch (error) {
        showToast('网络请求失败，请检查连接', 'error');
    }
}

async function sendTestSignal() {
    const strategy = document.getElementById('signal-strategy')?.value || 'test';
    const action = document.getElementById('signal-action')?.value || 'buy';
    const lot = document.getElementById('signal-lot')?.value || 0.1;
    const sl = document.getElementById('signal-sl')?.value || 50;
    const tp = document.getElementById('signal-tp')?.value || 100;
    
    const signal = {
        strategy: strategy,
        action: action,
        symbol: 'XAUUSD',
        lot: parseFloat(lot),
        sl_points: parseInt(sl),
        tp_points: parseInt(tp)
    };
    
    const actionName = action.toUpperCase() === 'BUY' ? '做多' : 
                       action.toUpperCase() === 'SELL' ? '做空' : 
                       action.toUpperCase() === 'CLOSE' ? '平仓' : '全部平仓';
    
    showToast(`正在发送测试信号: ${actionName}...`, 'info');
    
    try {
        const response = await fetch('/webhook', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(signal)
        });
        
        const result = await response.json();
        
        const resultEl = document.getElementById('signal-result');
        if (resultEl) {
            if (response.ok && result.success) {
                resultEl.className = 'alert alert-success';
                resultEl.innerHTML = `<strong>成功!</strong><br>${result.message}`;
                showToast(`测试信号发送成功! ${actionName}`, 'success');
            } else {
                resultEl.className = 'alert alert-danger';
                resultEl.innerHTML = `<strong>失败!</strong><br>${result.message}`;
                showToast(`测试信号发送失败: ${result.message || '未知错误'}`, 'error');
            }
        }
    } catch (error) {
        const resultEl = document.getElementById('signal-result');
        if (resultEl) {
            resultEl.className = 'alert alert-danger';
            resultEl.innerHTML = '<strong>失败!</strong><br>网络请求失败，请检查连接';
        }
        showToast('网络请求失败，请检查连接', 'error');
    }
}

function testToast() {
    showToast('这是一条测试提示！', 'success');
}

function showToast(message, type = 'info') {
    const container = getOrCreateToastContainer();
    
    const toast = document.createElement('div');
    toast.style.cssText = `
        position: fixed;
        top: 100px;
        right: 20px;
        background: #1a1a2e;
        border: 2px solid;
        border-left: 6px solid;
        border-radius: 12px;
        padding: 20px 25px;
        box-shadow: 0 10px 40px rgba(0,0,0,0.5);
        z-index: 999999;
        min-width: 300px;
        animation: slideIn 0.4s ease-out;
    `;
    
    const colors = {
        success: '#198754',
        error: '#dc3545',
        warning: '#ffc107',
        info: '#0dcaf0'
    };
    
    const color = colors[type] || colors.info;
    toast.style.borderColor = color;
    toast.style.borderLeftColor = color;
    toast.style.background = `linear-gradient(135deg, ${color}22, #1a1a2e)`;
    
    toast.innerHTML = `
        <div>
            <div style="color: white; font-weight: bold; font-size: 16px; margin-bottom: 4px;">
                ${type === 'success' ? '成功' : type === 'error' ? '失败' : type === 'warning' ? '警告' : '提示'}
            </div>
            <div style="color: #ccc; font-size: 14px;">
                ${message}
            </div>
        </div>
    `;
    
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideIn 0.4s ease-out reverse';
        setTimeout(() => toast.remove(), 400);
    }, 4000);
}

function getOrCreateToastContainer() {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.style.cssText = `
            position: fixed;
            top: 0;
            right: 0;
            z-index: 999999;
            pointer-events: none;
        `;
        document.body.appendChild(container);
    }
    return container;
}

async function saveSettings() {
    showToast('正在保存设置...', 'info');
    
    const settings = {
        lot_size: parseFloat(document.getElementById('config-lot')?.value || 0.1),
        max_lot: parseFloat(document.getElementById('config-max-lot')?.value || 1.0),
        sl_points: parseInt(document.getElementById('config-sl')?.value || 50),
        tp_points: parseInt(document.getElementById('config-tp')?.value || 100),
        ai_enabled: document.getElementById('ai-enabled')?.checked ?? true,
        tv_enabled: document.getElementById('ai-tv-enabled')?.checked ?? true,
        rsi_period: parseInt(document.getElementById('ai-rsi-period')?.value || 14),
        rsi_oversold: parseInt(document.getElementById('ai-rsi-oversold')?.value || 30),
        rsi_overbought: parseInt(document.getElementById('ai-rsi-overbought')?.value || 70),
        macd_fast: parseInt(document.getElementById('ai-macd-fast')?.value || 12),
        macd_slow: parseInt(document.getElementById('ai-macd-slow')?.value || 26),
        macd_signal: parseInt(document.getElementById('ai-macd-signal')?.value || 9),
        bb_period: parseInt(document.getElementById('ai-bb-period')?.value || 20),
        bb_std: parseFloat(document.getElementById('ai-bb-std')?.value || 2.0),
        min_confidence: parseFloat(document.getElementById('ai-min-confidence')?.value || 0.4),
        use_weighted_average: document.getElementById('ai-use-weighted')?.checked ?? true,
        dynamic_risk_enabled: document.getElementById('ai-dynamic-risk')?.checked ?? true,
        llm_enabled: document.getElementById('llm-enabled')?.checked ?? false,
        llm_provider: document.getElementById('llm-provider')?.value ?? 'openai',
        llm_api_key: document.getElementById('llm-api-key')?.value ?? '',
        llm_model: document.getElementById('llm-model')?.value ?? 'gpt-4',
        llm_base_url: document.getElementById('llm-base-url')?.value ?? '',
        llm_timeout: parseInt(document.getElementById('llm-timeout')?.value || 30),
        llm_max_tokens: parseInt(document.getElementById('llm-max-tokens')?.value || 1000),
        llm_temperature: parseFloat(document.getElementById('llm-temperature')?.value || 0.7),
        llm_use_signal: document.getElementById('llm-use-signal')?.checked ?? false,
        llm_use_market: document.getElementById('llm-use-market')?.checked ?? false,
        llm_use_trade: document.getElementById('llm-use-trade')?.checked ?? false
    };
    
    try {
        const response = await fetch('/api/save-settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        
        const result = await response.json();
        
        if (response.ok && result.success) {
            showToast('设置保存成功！', 'success');
        } else {
            showToast(`设置保存失败: ${result.message || '未知错误'}`, 'error');
        }
    } catch (error) {
        showToast('网络请求失败，请检查连接', 'error');
    }
}

async function loadCandles() {
    const timeframeSelect = document.getElementById('timeframe-select');
    if (!timeframeSelect) return;
    
    const timeframe = timeframeSelect.value;
    const symbol = 'XAUUSD';
    
    try {
        const response = await fetch(`/api/candles/${symbol}/${timeframe}?count=1`);
        const result = await response.json();
        
        if (result.success && result.candles && result.candles.length > 0) {
            const candle = result.candles[0];
            
            const openEl = document.getElementById('ohlc-open');
            const highEl = document.getElementById('ohlc-high');
            const lowEl = document.getElementById('ohlc-low');
            const closeEl = document.getElementById('ohlc-close');
            const volumeEl = document.getElementById('ohlc-volume');
            
            if (openEl) openEl.textContent = candle.open.toFixed(2);
            if (highEl) highEl.textContent = candle.high.toFixed(2);
            if (lowEl) lowEl.textContent = candle.low.toFixed(2);
            if (closeEl) closeEl.textContent = candle.close.toFixed(2);
            if (volumeEl) volumeEl.textContent = candle.volume ? candle.volume.toLocaleString() : '0';
            
            // 根据涨跌设置颜色
            if (closeEl && candle.close >= candle.open) {
                closeEl.classList.remove('text-info');
                closeEl.classList.add('text-success');
            } else if (closeEl) {
                closeEl.classList.remove('text-info');
                closeEl.classList.add('text-danger');
            }
        } else {
            showToast('获取 K 线数据失败', 'error');
        }
    } catch (error) {
        console.error('获取 K 线数据失败:', error);
        showToast('获取 K 线数据失败', 'error');
    }
}

// ========== AI相关功能 ==========

let lastAIAnalysis = null;
let aiRefreshInterval = null;

async function refreshAIAnalysis() {
    // 更新 LLM 深度分析
    const llmStatus = document.getElementById('llm-status');
    const llmResult = document.getElementById('llm-result');
    const llmLoading = document.getElementById('llm-loading');
    
    if (!llmStatus || !llmResult) return;
    
    try {
        // 显示加载状态
        llmLoading.style.display = 'block';
        llmResult.style.display = 'none';
        
        // 添加前端超时控制（35秒，比后端超时稍长一点）
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 35000);
        
        try {
            const response = await fetch('/api/ai/analysis', {
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            const result = await response.json();
            
            lastAIAnalysis = result;
            
            if (!result.enabled) {
                llmStatus.className = 'badge bg-secondary text-white small';
                llmStatus.textContent = '未启用';
                llmLoading.style.display = 'none';
                llmResult.style.display = 'block';
                llmResult.innerHTML = '<p class="text-muted text-center">' + (result.error || 'AI功能未启用') + '</p>';
                return;
            }
            
            if (result.error) {
                llmStatus.className = 'badge bg-warning text-white small';
                llmStatus.textContent = '警告';
                llmLoading.style.display = 'none';
                llmResult.style.display = 'block';
                llmResult.innerHTML = `<p class="text-warning text-center">${result.llm_analysis || result.error}</p>`;
                return;
            }
            
            if (result.llm_enabled) {
                llmStatus.className = 'badge bg-success text-white small';
                llmStatus.textContent = '已启用';
                
                if (result.llm_analysis) {
                    llmLoading.style.display = 'none';
                    llmResult.style.display = 'block';
                    llmResult.innerHTML = `<div class="llm-analysis-content">${result.llm_analysis.replace(/\n/g, '<br>')}</div>`;
                } else {
                    llmLoading.style.display = 'none';
                    llmResult.style.display = 'block';
                    llmResult.innerHTML = '<p class="text-muted text-center">暂无 LLM 深度分析</p>';
                }
            } else {
                llmStatus.className = 'badge bg-secondary text-white small';
                llmStatus.textContent = '未配置';
                llmLoading.style.display = 'none';
                llmResult.style.display = 'block';
                llmResult.innerHTML = '<p class="text-muted text-center">请先在系统设置中配置 LLM</p>';
            }
            
        } catch (fetchError) {
            clearTimeout(timeoutId);
            if (fetchError.name === 'AbortError') {
                console.error('LLM分析请求超时');
                llmStatus.className = 'badge bg-warning text-white small';
                llmStatus.textContent = '超时';
                llmLoading.style.display = 'none';
                llmResult.style.display = 'block';
                llmResult.innerHTML = '<p class="text-warning text-center">⚠️ 请求超时，请稍后重试或检查网络连接</p>';
            } else {
                throw fetchError;
            }
        }
        
    } catch (error) {
        console.error('LLM分析刷新失败:', error);
        llmStatus.className = 'badge bg-danger text-white small';
        llmStatus.textContent = '错误';
        llmLoading.style.display = 'none';
        llmResult.style.display = 'block';
        llmResult.innerHTML = '<p class="text-danger text-center">网络错误</p>';
    }
}

async function refreshStopLossAdvice(autoExecute = false) {
    // 更新动态止损建议
    const stopLossResult = document.getElementById('stop-loss-result');
    const stopLossLoading = document.getElementById('stop-loss-loading');
    
    if (!stopLossResult) return;
    
    try {
        // 显示加载状态
        stopLossLoading.style.display = 'block';
        stopLossResult.style.display = 'none';
        
        // 添加前端超时控制（35秒，缩短超时）
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 35000);
        
        try {
            const url = `/api/ai/stop-loss?auto_execute=${autoExecute}`;
            const response = await fetch(url, {
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            const result = await response.json();
            
            if (!result.success) {
                stopLossLoading.style.display = 'none';
                stopLossResult.style.display = 'block';
                stopLossResult.innerHTML = `<p class="text-warning text-center">${result.message}</p>`;
                return;
            }
            
            const data = result.data;
            
            // 显示自动平仓结果
            let closedHtml = '';
            if (data.closed_positions && data.closed_positions.length > 0) {
                closedHtml = `
                    <div class="alert alert-success mb-3">
                        <h6><i class="fas fa-check-circle"></i> 已自动平仓</h6>
                        <ul class="mb-0">
                            ${data.closed_positions.map(p => `<li>订单 ${p.ticket}: ${p.reason}</li>`).join('')}
                        </ul>
                    </div>
                `;
                // 刷新持仓列表
                refreshPositions();
            }
            
            if (!data.has_position) {
                stopLossLoading.style.display = 'none';
                stopLossResult.style.display = 'block';
                stopLossResult.innerHTML = closedHtml + `<p class="text-muted text-center">${data.advice}</p>`;
                return;
            }
            
            // 渲染止损建议
            let html = closedHtml;
            if (data.stop_loss_advice && data.stop_loss_advice.length > 0) {
                for (const advice of data.stop_loss_advice) {
                    const pos = advice.position_info;
                    const riskColor = {
                        '低': 'text-success',
                        '中': 'text-warning',
                        '高': 'text-danger',
                        '未知': 'text-secondary'
                    }[advice.risk_level] || 'text-secondary';
                    
                    const borderColor = advice.should_close ? 'border-danger' : 
                                      advice.risk_level === '高' ? 'border-danger' : 
                                      advice.risk_level === '中' ? 'border-warning' : 'border-success';
                    
                    html += `
                        <div class="card mb-2 ${borderColor}">
                            <div class="card-body py-2">
                                <div class="row align-items-center">
                                    <div class="col-md-2">
                                        <span class="badge ${pos.type === 'BUY' ? 'bg-success' : 'bg-danger'}">${pos.type}</span>
                                        <span class="ms-2">${pos.volume} 手</span>
                                    </div>
                                    <div class="col-md-2">
                                        <small class="text-muted">利润:</small> 
                                        <span class="${pos.profit >= 0 ? 'text-success' : 'text-danger'}">
                                            ${pos.profit >= 0 ? '+' : ''}${pos.profit.toFixed(2)}
                                        </span>
                                    </div>
                                    <div class="col-md-2">
                                        <small class="text-muted">决策:</small> 
                                        <span class="badge ${advice.should_close ? 'bg-danger' : 'bg-success'}">
                                            ${advice.should_close ? '立即平仓' : '继续持有'}
                                        </span>
                                    </div>
                                    <div class="col-md-2">
                                        <small class="text-muted">风险:</small> 
                                        <span class="${riskColor}">${advice.risk_level}</span>
                                    </div>
                                    <div class="col-md-4">
                                        ${advice.should_close ? `
                                            <button class="btn btn-sm btn-danger" onclick="closePosition(${pos.ticket})">
                                                <i class="fas fa-times"></i> 立即平仓
                                            </button>
                                        ` : advice.stop_loss_price ? `
                                            <button class="btn btn-sm btn-outline-primary" onclick="applyStopLoss(${pos.ticket}, ${advice.stop_loss_price})">
                                                <i class="fas fa-shield"></i> 止损: ${advice.stop_loss_price.toFixed(2)}
                                            </button>
                                        ` : ''}
                                    </div>
                                </div>
                                ${advice.reason ? `
                                <div class="mt-2 pt-2 border-top">
                                    <small class="text-muted">LLM分析:</small>
                                    <div class="mt-1 text-sm">${advice.reason}</div>
                                </div>
                                ` : ''}
                            </div>
                        </div>
                    `;
                }
            } else {
                html += `<p class="text-muted text-center">${data.advice}</p>`;
            }
            
            stopLossLoading.style.display = 'none';
            stopLossResult.style.display = 'block';
            stopLossResult.innerHTML = html;
            
        } catch (fetchError) {
            clearTimeout(timeoutId);
            if (fetchError.name === 'AbortError') {
                console.error('动态止损请求超时');
                stopLossLoading.style.display = 'none';
                stopLossResult.style.display = 'block';
                stopLossResult.innerHTML = '<p class="text-warning text-center">⚠️ 请求超时，请稍后重试</p>';
            } else {
                throw fetchError;
            }
        }
        
    } catch (error) {
        console.error('动态止损刷新失败:', error);
        stopLossLoading.style.display = 'none';
        stopLossResult.style.display = 'block';
        stopLossResult.innerHTML = '<p class="text-danger text-center">网络错误</p>';
    }
}

async function applyStopLoss(ticket, newSlPrice) {
    // 应用止损
    if (!confirm(`确定要将订单 ${ticket} 的止损更新为 ${newSlPrice.toFixed(2)} 吗？`)) {
        return;
    }
    
    try {
        showToast('正在更新止损...', 'info');
        
        const response = await fetch('/api/position/modify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ticket: ticket,
                sl: newSlPrice
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            showToast('止损更新成功', 'success');
            // 刷新持仓和止损建议
            refreshPositions();
            refreshStopLossAdvice();
        } else {
            showToast(result.message || '止损更新失败', 'error');
        }
        
    } catch (error) {
        console.error('更新止损失败:', error);
        showToast('更新止损失败', 'error');
    }
}

function updateSignalIndicator(signal, indicatorEl, textEl, confidenceEl) {
    const signalType = signal.signal_type;
    const confidence = signal.confidence || 0;
    const strength = signal.strength || 3;
    
    // 设置指示器颜色
    if (signalType === 'buy') {
        indicatorEl.className = 'display-4 text-success';
        indicatorEl.innerHTML = '<i class="fas fa-arrow-up"></i>';
        textEl.textContent = '做多信号';
    } else if (signalType === 'sell') {
        indicatorEl.className = 'display-4 text-danger';
        indicatorEl.innerHTML = '<i class="fas fa-arrow-down"></i>';
        textEl.textContent = '做空信号';
    } else {
        indicatorEl.className = 'display-4 text-secondary';
        indicatorEl.innerHTML = '<i class="fas fa-pause"></i>';
        textEl.textContent = '观望';
    }
    
    // 显示置信度
    confidenceEl.textContent = `置信度: ${(confidence * 100).toFixed(1)}% | 强度: ${getStrengthText(strength)}`;
}

function updateTradeButtons(signal, buyBtn, sellBtn, riskParams) {
    const signalType = signal.signal_type;
    const confidence = signal.confidence || 0;
    const allowTrade = riskParams?.allow_trade ?? true;
    
    // 只有信号足够强且允许交易时才启用按钮
    const isBuyEnabled = signalType === 'buy' && confidence >= 0.4 && allowTrade;
    const isSellEnabled = signalType === 'sell' && confidence >= 0.4 && allowTrade;
    
    buyBtn.disabled = !isBuyEnabled;
    sellBtn.disabled = !isSellEnabled;
    
    // 添加活跃状态样式
    buyBtn.classList.toggle('btn-success', isBuyEnabled);
    buyBtn.classList.toggle('btn-outline-success', !isBuyEnabled);
    sellBtn.classList.toggle('btn-danger', isSellEnabled);
    sellBtn.classList.toggle('btn-outline-danger', !isSellEnabled);
}

function getStrengthText(strength) {
    const strengthMap = {
        1: '极弱',
        2: '较弱',
        3: '中等',
        4: '较强',
        5: '极强'
    };
    return strengthMap[strength] || '未知';
}

function getRegimeText(regime) {
    const regimeMap = {
        'high_volatility': '高波动',
        'low_volatility': '低波动',
        'trending': '趋势',
        'ranging': '震荡',
        'unknown': '未知'
    };
    return regimeMap[regime] || regime || '--';
}

async function executeAITrade(action) {
    showToast(`正在执行AI指导的${action === 'buy' ? '做多' : '做空'}...`, 'info');
    
    try {
        const response = await fetch('/api/ai/trade', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                symbol: 'XAUUSD',
                action: action.toUpperCase()
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            showToast(`AI指导交易成功: ${result.message}`, 'success');
        } else {
            showToast(`AI指导交易失败: ${result.message}`, 'error');
        }
    } catch (error) {
        console.error('AI交易执行失败:', error);
        showToast('AI指导交易执行失败', 'error');
    }
}

// 自动刷新AI分析（每30秒）
function startAIRefresh() {
    if (aiRefreshInterval) {
        clearInterval(aiRefreshInterval);
    }
    
    // 立即刷新一次
    refreshAIAnalysis();
    
    // 设置定时刷新
    aiRefreshInterval = setInterval(() => {
        refreshAIAnalysis();
    }, 30000);
}

// ========== LLM历史记录功能 ==========

let currentHistoryTab = 'analysis';

function initLLMHistoryPage() {
    // 初始化标签页切换
    const tabs = document.querySelectorAll('#history-tabs .nav-link');
    tabs.forEach(tab => {
        tab.addEventListener('click', (e) => {
            e.preventDefault();
            const newTab = tab.getAttribute('data-tab');
            if (newTab !== currentHistoryTab) {
                switchHistoryTab(newTab);
            }
        });
    });
    
    // 初始化筛选器
    const filterSymbol = document.getElementById('history-filter-symbol');
    const filterLimit = document.getElementById('history-filter-limit');
    if (filterSymbol) {
        filterSymbol.addEventListener('change', refreshLLMHistory);
    }
    if (filterLimit) {
        filterLimit.addEventListener('change', refreshLLMHistory);
    }
    
    // 初始加载
    refreshLLMHistory();
}

function switchHistoryTab(tab) {
    currentHistoryTab = tab;
    
    // 更新标签样式
    const tabs = document.querySelectorAll('#history-tabs .nav-link');
    tabs.forEach(t => {
        t.classList.toggle('active', t.getAttribute('data-tab') === tab);
    });
    
    // 刷新数据
    refreshLLMHistory();
}

async function refreshLLMHistory() {
    const loadingEl = document.getElementById('history-loading');
    const dataEl = document.getElementById('history-data');
    
    if (!loadingEl || !dataEl) return;
    
    loadingEl.style.display = 'block';
    dataEl.innerHTML = '';
    
    try {
        const symbol = document.getElementById('history-filter-symbol')?.value || '';
        const limit = parseInt(document.getElementById('history-filter-limit')?.value || '50');
        
        if (currentHistoryTab === 'analysis') {
            await loadAnalysisHistory(symbol, limit);
        } else {
            await loadConversationHistory(symbol, limit);
        }
        
        loadingEl.style.display = 'none';
    } catch (error) {
        console.error('加载历史记录失败:', error);
        loadingEl.style.display = 'none';
        dataEl.innerHTML = '<p class="text-danger text-center">加载失败</p>';
    }
}

async function loadAnalysisHistory(symbol, limit) {
    const dataEl = document.getElementById('history-data');
    if (!dataEl) return;
    
    let url = `/api/llm/history/analysis?limit=${limit}`;
    if (symbol) {
        url += `&symbol=${symbol}`;
    }
    
    const response = await fetch(url);
    const result = await response.json();
    
    if (!result.success) {
        dataEl.innerHTML = `<p class="text-danger text-center">${result.message}</p>`;
        return;
    }
    
    const analyses = result.data || [];
    if (analyses.length === 0) {
        dataEl.innerHTML = '<p class="text-muted text-center">暂无历史记录</p>';
        return;
    }
    
    let html = '<div class="table-responsive"><table class="table table-striped table-hover">';
    html += '<thead class="table-dark"><tr>';
    html += '<th>时间</th><th>订单</th><th>品种</th><th>方向</th><th>手数</th>';
    html += '<th>开仓价</th><th>现价</th><th>利润</th><th>决策</th><th>止损价</th><th>原因</th>';
    html += '</tr></thead><tbody>';
    
    for (const analysis of analyses) {
        const profitClass = analysis.profit >= 0 ? 'text-success' : 'text-danger';
        const decisionBadge = analysis.decision === 'close' ? 'bg-danger' : 'bg-success';
        const decisionText = analysis.decision === 'close' ? '平仓' : '持有';
        
        html += '<tr>';
        html += `<td>${new Date(analysis.timestamp).toLocaleString('zh-CN')}</td>`;
        html += `<td>${analysis.ticket || '-'}</td>`;
        html += `<td>${analysis.symbol}</td>`;
        html += `<td><span class="badge ${analysis.position_type === 'BUY' ? 'bg-success' : 'bg-danger'}">${analysis.position_type}</span></td>`;
        html += `<td>${analysis.volume}</td>`;
        html += `<td>${analysis.open_price?.toFixed(2) || '-'}</td>`;
        html += `<td>${analysis.current_price?.toFixed(2) || '-'}</td>`;
        html += `<td class="${profitClass}">${analysis.profit >= 0 ? '+' : ''}${analysis.profit?.toFixed(2) || '-'}</td>`;
        html += `<td><span class="badge ${decisionBadge}">${decisionText}</span></td>`;
        html += `<td>${analysis.stop_loss_price?.toFixed(2) || '-'}</td>`;
        html += `<td class="text-truncate" style="max-width: 200px;" title="${analysis.reason || ''}">${analysis.reason || '-'}</td>`;
        html += '</tr>';
    }
    
    html += '</tbody></table></div>';
    dataEl.innerHTML = html;
}

async function loadConversationHistory(symbol, limit) {
    const dataEl = document.getElementById('history-data');
    if (!dataEl) return;
    
    let url = `/api/llm/history/conversations?limit=${limit}`;
    if (symbol) {
        url += `&symbol=${symbol}`;
    }
    
    const response = await fetch(url);
    const result = await response.json();
    
    if (!result.success) {
        dataEl.innerHTML = `<p class="text-danger text-center">${result.message}</p>`;
        return;
    }
    
    const conversations = result.data || [];
    if (conversations.length === 0) {
        dataEl.innerHTML = '<p class="text-muted text-center">暂无对话记录</p>';
        return;
    }
    
    let html = '<div class="list-group">';
    for (const conv of conversations) {
        const statusBadge = conv.status === 'active' ? 'bg-success' : 'bg-secondary';
        html += `
            <a href="#" class="list-group-item list-group-item-action" onclick="showConversationDetail(${conv.id}); return false;">
                <div class="d-flex w-100 justify-content-between align-items-center">
                    <div>
                        <h6 class="mb-1">对话 #${conv.id} - ${conv.symbol}</h6>
                        <small class="text-muted">开始时间: ${new Date(conv.start_time).toLocaleString('zh-CN')}</small>
                    </div>
                    <span class="badge ${statusBadge}">${conv.status === 'active' ? '活跃' : '结束'}</span>
                </div>
            </a>
        `;
    }
    html += '</div>';
    
    dataEl.innerHTML = html;
}

async function showConversationDetail(conversationId) {
    const modal = new bootstrap.Modal(document.getElementById('conversationModal'));
    const modalContent = document.getElementById('modal-conversation-content');
    const modalTitle = document.getElementById('modal-conversation-id');
    
    modalTitle.textContent = `#${conversationId}`;
    modalContent.innerHTML = '<p class="text-center"><i class="fas fa-spinner fa-spin"></i> 加载中...</p>';
    modal.show();
    
    try {
        const response = await fetch(`/api/llm/conversation/${conversationId}`);
        const result = await response.json();
        
        if (!result.success) {
            modalContent.innerHTML = `<p class="text-danger text-center">${result.message}</p>`;
            return;
        }
        
        const messages = result.data || [];
        if (messages.length === 0) {
            modalContent.innerHTML = '<p class="text-muted text-center">暂无对话内容</p>';
            return;
        }
        
        let html = '';
        for (const msg of messages) {
            const isAssistant = msg.role === 'assistant';
            const bgClass = isAssistant ? 'bg-primary' : 'bg-secondary';
            const alignClass = isAssistant ? 'text-end' : 'text-start';
            const roleLabel = isAssistant ? 'AI助手' : '用户';
            
            html += `
                <div class="mb-3 ${alignClass}">
                    <div class="badge ${bgClass} mb-1">${roleLabel}</div>
                    <div class="card">
                        <div class="card-body py-2">
                            <p class="mb-0 small">${msg.content.replace(/\n/g, '<br>')}</p>
                        </div>
                    </div>
                    <small class="text-muted">${new Date(msg.timestamp).toLocaleString('zh-CN')}</small>
                </div>
            `;
        }
        
        modalContent.innerHTML = html;
    } catch (error) {
        console.error('加载对话详情失败:', error);
        modalContent.innerHTML = '<p class="text-danger text-center">加载失败</p>';
    }
}

// 页面加载后启动AI刷新
document.addEventListener('DOMContentLoaded', () => {
    // 延迟启动，等待其他组件初始化
    setTimeout(() => {
        startAIRefresh();
    }, 2000);
});
