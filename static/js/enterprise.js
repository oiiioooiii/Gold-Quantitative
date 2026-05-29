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
        this.loadPage('dashboard');
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
        
        // 更新K线和指标数据（WebSocket推送）
        if (data.kline && data.indicators) {
            this.updateAllCharts(data.kline, data.indicators);
            // 同时更新OHLC显示（取最后一根K线）
            if (data.kline.length > 0) {
                this.updateOHLC(data.kline[data.kline.length - 1]);
            }
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
                        // 不再需要HTTP轮询，WebSocket会推送数据
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
        const macdChartDom = document.getElementById('macd-chart');
        const rsiChartDom = document.getElementById('rsi-chart');
        const kdjChartDom = document.getElementById('kdj-chart');
        
        if (!mainChartDom || !volumeChartDom || !macdChartDom || !rsiChartDom || !kdjChartDom) return;
        
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
            
            // ========== MACD图 ==========
            this.macdChart = LightweightCharts.createChart(macdChartDom, {
                ...chartConfig,
                timeScale: { ...chartConfig.timeScale, timeVisible: false },
            });
            
            this.macdLineSeries = this.macdChart.addLineSeries({
                color: '#14b8a6',
                lineWidth: 1,
            });
            
            this.macdSignalSeries = this.macdChart.addLineSeries({
                color: '#f87171',
                lineWidth: 1,
            });
            
            this.macdHistSeries = this.macdChart.addHistogramSeries({
                priceScaleId: '',
                scaleMargins: { top: 0.5, bottom: 0.5 },
            });
            
            // ========== RSI图 ==========
            this.rsiChart = LightweightCharts.createChart(rsiChartDom, {
                ...chartConfig,
                timeScale: { ...chartConfig.timeScale, timeVisible: false },
            });
            
            this.rsiSeries = this.rsiChart.addLineSeries({
                color: '#FF6B6B',
                lineWidth: 1,
            });
            
            // RSI超买超卖线
            this.rsiOverbought = this.rsiChart.addLineSeries({
                color: '#444',
                lineWidth: 1,
                lineStyle: 2,
            });
            
            this.rsiOversold = this.rsiChart.addLineSeries({
                color: '#444',
                lineWidth: 1,
                lineStyle: 2,
            });
            
            // ========== KDJ图 ==========
            this.kdjChart = LightweightCharts.createChart(kdjChartDom, {
                ...chartConfig,
                timeScale: { ...chartConfig.timeScale, timeVisible: false },
            });
            
            this.kSeries = this.kdjChart.addLineSeries({
                color: '#FFD700',
                lineWidth: 1,
            });
            
            this.dSeries = this.kdjChart.addLineSeries({
                color: '#14b8a6',
                lineWidth: 1,
            });
            
            this.jSeries = this.kdjChart.addLineSeries({
                color: '#f87171',
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
                if (this.macdChart) {
                    this.macdChart.applyOptions({
                        width: macdChartDom.clientWidth,
                        height: macdChartDom.clientHeight
                    });
                }
                if (this.rsiChart) {
                    this.rsiChart.applyOptions({
                        width: rsiChartDom.clientWidth,
                        height: rsiChartDom.clientHeight
                    });
                }
                if (this.kdjChart) {
                    this.kdjChart.applyOptions({
                        width: kdjChartDom.clientWidth,
                        height: kdjChartDom.clientHeight
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
            syncTimeScale(this.mainChart, [this.volumeChart, this.macdChart, this.rsiChart, this.kdjChart]);
            syncTimeScale(this.volumeChart, [this.mainChart]);
            
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
        
        // 让两个图表都自动适配内容后再同步
        setTimeout(() => {
            this.mainChart.timeScale().fitContent();
            if (this.volumeChart) {
                this.volumeChart.timeScale().fitContent();
                
                // 然后完全对齐到主图的可视范围
                const range = this.mainChart.timeScale().getVisibleRange();
                if (range) {
                    this.volumeChart.timeScale().setVisibleRange(range);
                }
            }
        }, 50);
        
        // ========== 更新MACD图 ==========
        if (this.macdChart) {
            const macdData = indicators.macd.macd.map((val, i) => ({
                time: times[i],
                value: val
            })).filter(d => d.value !== null);
            
            const signalData = indicators.macd.signal.map((val, i) => ({
                time: times[i],
                value: val
            })).filter(d => d.value !== null);
            
            const histData = indicators.macd.histogram.map((val, i) => ({
                time: times[i],
                value: val,
                color: val >= 0 ? '#14b8a6' : '#f87171'
            })).filter(d => d.value !== null);
            
            this.macdLineSeries.setData(macdData);
            this.macdSignalSeries.setData(signalData);
            this.macdHistSeries.setData(histData);
        }
        
        // ========== 更新RSI图 ==========
        if (this.rsiChart) {
            const rsiData = indicators.rsi.map((val, i) => ({
                time: times[i],
                value: val
            })).filter(d => d.value !== null);
            
            // 超买超卖线
            const overboughtLine = times.map(t => ({ time: t, value: 70 }));
            const oversoldLine = times.map(t => ({ time: t, value: 30 }));
            
            this.rsiSeries.setData(rsiData);
            this.rsiOverbought.setData(overboughtLine);
            this.rsiOversold.setData(oversoldLine);
        }
        
        // ========== 更新KDJ图 ==========
        if (this.kdjChart) {
            const kData = indicators.kdj.k.map((val, i) => ({
                time: times[i],
                value: val
            })).filter(d => d.value !== null);
            
            const dData = indicators.kdj.d.map((val, i) => ({
                time: times[i],
                value: val
            })).filter(d => d.value !== null);
            
            const jData = indicators.kdj.j.map((val, i) => ({
                time: times[i],
                value: val
            })).filter(d => d.value !== null);
            
            this.kSeries.setData(kData);
            this.dSeries.setData(dData);
            this.jSeries.setData(jData);
        }
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

document.addEventListener('DOMContentLoaded', () => {
    wsClient = new TradingWebSocket();
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
        tp_points: parseInt(document.getElementById('config-tp')?.value || 100)
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

function loadCandlesForChart() {
    if (wsClient && wsClient.loadCandlesForChart) {
        wsClient.loadCandlesForChart();
    }
}
