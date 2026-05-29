
// ============================================
// 黄金量化交易系统 - 专业版 JavaScript
// ============================================

let currentPage = 'dashboard';
let currentSymbol = 'XAUUSD';
let lastPrice = null;
let orderType = 'market';

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    initNavigation();
    loadPage('dashboard');
    startPriceUpdates();
    startStatusUpdates();
});

// ============================================
// 导航和页面加载
// ============================================

function initNavigation() {
    const navLinks = document.querySelectorAll('.nav-link');
    navLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const page = this.getAttribute('data-page');
            loadPage(page);
            navLinks.forEach(l => l.classList.remove('active'));
            this.classList.add('active');
        });
    });
}

async function loadPage(page) {
    currentPage = page;
    
    try {
        const response = await fetch(`/api/page/${page}`);
        if (response.ok) {
            const html = await response.text();
            document.getElementById('main-content').innerHTML = html;
            
            if (page === 'dashboard') {
                initDashboard();
            } else if (page === 'trade') {
                initTradePage();
            } else if (page === 'signals') {
                // 无需特殊初始化
            } else if (page === 'settings') {
                loadConfig();
            }
        }
    } catch (error) {
        console.error('加载页面失败:', error);
        showNotification('加载页面失败', 'danger');
    }
}

// ============================================
// 仪表板功能
// ============================================

async function initDashboard() {
    initSymbolSelector();
    await loadAccountInfo();
    await loadPositions();
    await loadOrders();
    await updateSystemStatus();
}

function initSymbolSelector() {
    const selector = document.getElementById('symbol-selector');
    if (selector) {
        selector.querySelectorAll('.symbol-tag').forEach(tag => {
            tag.addEventListener('click', function() {
                const symbol = this.getAttribute('data-symbol');
                setCurrentSymbol(symbol, this);
            });
        });
    }
}

function setCurrentSymbol(symbol, element) {
    currentSymbol = symbol;
    
    // 更新标签状态
    document.querySelectorAll('#symbol-selector .symbol-tag, #trade-symbol-selector .symbol-tag').forEach(tag => {
        tag.classList.remove('active');
        if (tag.getAttribute('data-symbol') === symbol) {
            tag.classList.add('active');
        }
    });
    
    // 更新显示的品种
    const symbolDisplay = document.getElementById('current-symbol');
    if (symbolDisplay) symbolDisplay.textContent = symbol;
    
    const tradeSymbolDisplay = document.getElementById('trade-current-symbol');
    if (tradeSymbolDisplay) tradeSymbolDisplay.textContent = symbol;
    
    // 更新价格
    updatePrice();
}

async function loadAccountInfo() {
    try {
        const response = await fetch('/api/account');
        if (response.ok) {
            const data = await response.json();
            updateAccountDisplay(data);
        }
    } catch (error) {
        console.error('获取账户信息失败:', error);
    }
}

function updateAccountDisplay(data) {
    const balanceEl = document.getElementById('account-balance');
    const equityEl = document.getElementById('account-equity');
    const profitEl = document.getElementById('account-profit');
    
    if (balanceEl) {
        balanceEl.textContent = '$' + formatNumber(data.balance);
    }
    if (equityEl) {
        equityEl.textContent = '$' + formatNumber(data.equity);
    }
    if (profitEl) {
        const profitClass = data.profit >= 0 ? 'success' : 'danger';
        profitEl.textContent = (data.profit >= 0 ? '+' : '') + '$' + formatNumber(data.profit);
    }
}

async function loadPositions() {
    try {
        const response = await fetch('/api/positions');
        if (response.ok) {
            const data = await response.json();
            updatePositionsTable(data.positions);
            
            const countEl = document.getElementById('positions-count');
            if (countEl) countEl.textContent = data.count;
        }
    } catch (error) {
        console.error('获取持仓失败:', error);
    }
}

function updatePositionsTable(positions) {
    const tbody = document.getElementById('positions-tbody');
    if (!tbody) return;
    
    if (positions.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="9" class="text-center py-4 text-muted">
                    <i class="fas fa-inbox fa-2x mb-2 d-block"></i>
                    当前无持仓
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = positions.map(pos => `
        <tr>
            <td><strong>${pos.symbol}</strong></td>
            <td>
                <span class="position-badge ${pos.type}">
                    <i class="fas fa-${pos.type === 'long' ? 'arrow-up' : 'arrow-down'}"></i>
                    ${pos.type === 'long' ? '做多' : '做空'}
                </span>
            </td>
            <td>${pos.volume}</td>
            <td>${pos.open_price}</td>
            <td>${pos.current_price}</td>
            <td class="${pos.profit >= 0 ? 'profit-positive' : 'profit-negative'}">
                <strong>${pos.profit >= 0 ? '+' : ''}$${formatNumber(pos.profit)}</strong>
            </td>
            <td>${pos.sl || '-'}</td>
            <td>${pos.tp || '-'}</td>
            <td>
                <button class="btn btn-sm btn-danger" onclick="closePosition(${pos.ticket})">
                    <i class="fas fa-times"></i> 平仓
                </button>
            </td>
        </tr>
    `).join('');
}

async function loadOrders() {
    try {
        const response = await fetch('/api/orders');
        if (response.ok) {
            const data = await response.json();
            updateOrdersTable(data.orders);
        }
    } catch (error) {
        console.error('获取挂单失败:', error);
    }
}

function updateOrdersTable(orders) {
    const tbody = document.getElementById('orders-tbody');
    if (!tbody) return;
    
    if (orders.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" class="text-center py-4 text-muted">
                    <i class="fas fa-inbox fa-2x mb-2 d-block"></i>
                    当前无挂单
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = orders.map(order => `
        <tr>
            <td><strong>${order.symbol}</strong></td>
            <td>
                <span class="position-badge ${order.type === 'buy_limit' ? 'long' : 'short'}">
                    ${order.type === 'buy_limit' ? '限价买' : '限价卖'}
                </span>
            </td>
            <td>${order.price}</td>
            <td>${order.volume}</td>
            <td>
                <button class="btn btn-sm btn-danger" onclick="cancelOrder(${order.ticket})">
                    <i class="fas fa-times"></i> 取消
                </button>
            </td>
        </tr>
    `).join('');
}

// ============================================
// 交易页面
// ============================================

function initTradePage() {
    initTradeSymbolSelector();
    updatePrice();
}

function initTradeSymbolSelector() {
    const selector = document.getElementById('trade-symbol-selector');
    if (selector) {
        selector.querySelectorAll('.symbol-tag').forEach(tag => {
            tag.addEventListener('click', function() {
                const symbol = this.getAttribute('data-symbol');
                setCurrentSymbol(symbol, this);
            });
        });
    }
}

function setOrderType(type) {
    orderType = type;
    
    document.getElementById('btn-market').classList.toggle('active', type === 'market');
    document.getElementById('btn-limit').classList.toggle('active', type === 'limit');
    
    document.getElementById('limit-price-group').style.display = type === 'limit' ? 'block' : 'none';
}

// ============================================
// 价格更新
// ============================================

function startPriceUpdates() {
    updatePrice();
    setInterval(updatePrice, 2000);
}

async function updatePrice() {
    try {
        const response = await fetch(`/api/price/${currentSymbol}`);
        if (response.ok) {
            const data = await response.json();
            updatePriceDisplay(data);
        }
    } catch (error) {
        console.error('获取价格失败:', error);
    }
}

function updatePriceDisplay(data) {
    const priceEl = document.getElementById('current-price');
    const tradePriceEl = document.getElementById('trade-current-price');
    const bidEl = document.getElementById('bid-price');
    const askEl = document.getElementById('ask-price');
    const tradeBidEl = document.getElementById('trade-bid');
    const tradeAskEl = document.getElementById('trade-ask');
    
    if (priceEl && data.ask) {
        const newPrice = data.ask.toFixed(2);
        priceEl.textContent = newPrice;
        
        if (lastPrice !== null && lastPrice !== newPrice) {
            const direction = parseFloat(newPrice) > lastPrice ? 'up' : 'down';
            priceEl.classList.remove('price-up', 'price-down');
            priceEl.classList.add('price-' + direction);
            setTimeout(() => priceEl.classList.remove('price-up', 'price-down'), 500);
        }
        lastPrice = parseFloat(newPrice);
    }
    
    if (tradePriceEl && data.ask) {
        tradePriceEl.textContent = data.ask.toFixed(2);
    }
    
    if (bidEl) bidEl.textContent = data.bid ? data.bid.toFixed(2) : '--';
    if (askEl) askEl.textContent = data.ask ? data.ask.toFixed(2) : '--';
    if (tradeBidEl) tradeBidEl.textContent = data.bid ? data.bid.toFixed(2) : '--';
    if (tradeAskEl) tradeAskEl.textContent = data.ask ? data.ask.toFixed(2) : '--';
}

// ============================================
// 状态更新
// ============================================

function startStatusUpdates() {
    updateSystemStatus();
    setInterval(updateSystemStatus, 5000);
}

async function updateSystemStatus() {
    try {
        const response = await fetch('/api/status');
        if (response.ok) {
            const data = await response.json();
            updateStatusDisplay(data);
        }
    } catch (error) {
        console.error('获取状态失败:', error);
    }
}

function updateStatusDisplay(data) {
    const statusEl = document.getElementById('system-status');
    const statusBadge = document.getElementById('mt5-status-badge');
    
    const isConnected = data.mt5_connected;
    
    if (statusEl) {
        statusEl.className = `status-indicator ${isConnected ? 'online' : 'offline'}`;
        statusEl.innerHTML = `
            <span class="pulse"></span>
            ${isConnected ? 'MT5 已连接' : 'MT5 未连接'}
        `;
    }
    
    if (statusBadge) {
        statusBadge.textContent = isConnected ? '已连接' : '未连接';
        statusBadge.style.color = isConnected ? '#10b981' : '#ef4444';
    }
}

// ============================================
// 交易操作
// ============================================

async function quickTrade(action) {
    const lotEl = document.getElementById('quick-lot');
    const slEl = document.getElementById('quick-sl');
    const tpEl = document.getElementById('quick-tp');
    
    const lot = lotEl ? parseFloat(lotEl.value) : 0.1;
    const sl = slEl ? parseInt(slEl.value) : 50;
    const tp = tpEl ? parseInt(tpEl.value) : 100;
    
    await executeTrade(action, lot, sl, tp, 'Quick Trade');
}

async function openPosition(action) {
    const lotEl = document.getElementById('trade-lot');
    const slEl = document.getElementById('trade-sl');
    const tpEl = document.getElementById('trade-tp');
    const commentEl = document.getElementById('trade-comment');
    const limitPriceEl = document.getElementById('limit-price');
    
    const lot = lotEl ? parseFloat(lotEl.value) : 0.1;
    const sl = slEl ? parseInt(slEl.value) : 50;
    const tp = tpEl ? parseInt(tpEl.value) : 100;
    const comment = commentEl ? commentEl.value : 'Manual Trade';
    
    await executeTrade(action, lot, sl, tp, comment, limitPriceEl);
}

async function executeTrade(action, lot, sl, tp, comment, limitPriceEl) {
    try {
        const signal = {
            strategy: 'manual',
            action: action,
            symbol: currentSymbol,
            lot: lot,
            sl_points: sl,
            tp_points: tp,
            comment: comment,
            order_type: orderType
        };
        
        if (orderType === 'limit' && limitPriceEl && limitPriceEl.value) {
            signal.limit_price = parseFloat(limitPriceEl.value);
        }
        
        const response = await fetch('/api/trade', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(signal)
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showNotification('订单执行成功!', 'success');
            await loadPositions();
            await loadAccountInfo();
            await loadOrders();
        } else {
            showNotification(result.message || '订单执行失败', 'danger');
        }
    } catch (error) {
        console.error('交易失败:', error);
        showNotification('交易失败', 'danger');
    }
}

async function closePosition(ticket) {
    if (!confirm('确定要平掉这个持仓吗?')) return;
    
    try {
        const response = await fetch(`/api/position/${ticket}/close`, {
            method: 'POST'
        });
        
        if (response.ok) {
            showNotification('平仓成功', 'success');
            await loadPositions();
            await loadAccountInfo();
        } else {
            const error = await response.json();
            showNotification(error.message || '平仓失败', 'danger');
        }
    } catch (error) {
        console.error('平仓失败:', error);
        showNotification('平仓失败', 'danger');
    }
}

async function closeAllPositions() {
    if (!confirm('确定要平掉所有持仓吗?')) return;
    
    try {
        const response = await fetch('/api/positions/close-all', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ symbol: currentSymbol })
        });
        
        if (response.ok) {
            showNotification('全部平仓成功', 'success');
            await loadPositions();
            await loadAccountInfo();
        }
    } catch (error) {
        console.error('平仓失败:', error);
        showNotification('平仓失败', 'danger');
    }
}

async function cancelOrder(ticket) {
    if (!confirm('确定要取消这个挂单吗?')) return;
    
    try {
        const response = await fetch(`/api/order/${ticket}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showNotification('挂单已取消', 'success');
            await loadOrders();
        } else {
            const error = await response.json();
            showNotification(error.message || '取消失败', 'danger');
        }
    } catch (error) {
        console.error('取消挂单失败:', error);
        showNotification('取消挂单失败', 'danger');
    }
}

// ============================================
// 信号测试
// ============================================

async function sendTestSignal() {
    const signal = {
        strategy: document.getElementById('signal-strategy').value,
        action: document.getElementById('signal-action').value,
        symbol: document.getElementById('signal-symbol').value,
        lot: parseFloat(document.getElementById('signal-lot').value),
        sl_points: parseInt(document.getElementById('signal-sl').value),
        tp_points: parseInt(document.getElementById('signal-tp').value)
    };
    
    try {
        const response = await fetch('/webhook', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(signal)
        });
        
        const result = await response.json();
        
        const resultEl = document.getElementById('signal-result');
        resultEl.innerHTML = `
            <div class="alert alert-${response.ok ? 'success' : 'danger'}">
                <h5><i class="fas fa-${response.ok ? 'check-circle' : 'exclamation-circle'}"></i> ${response.ok ? '成功' : '失败'}</h5>
                <hr>
                <p>${result.message || ''}</p>
                <details>
                    <summary>查看详细信息</summary>
                    <pre class="mt-2">${JSON.stringify(result, null, 2)}</pre>
                </details>
            </div>
        `;
        
        if (response.ok) {
            await loadPositions();
            await loadAccountInfo();
        }
    } catch (error) {
        console.error('发送信号失败:', error);
        showNotification('发送信号失败', 'danger');
    }
}

// ============================================
// 配置功能
// ============================================

async function loadConfig() {
    try {
        const response = await fetch('/api/config');
        if (response.ok) {
            const config = await response.json();
            const trading = config.trading || {};
            
            const symbolEl = document.getElementById('config-symbol');
            const lotEl = document.getElementById('config-lot');
            const maxLotEl = document.getElementById('config-max-lot');
            const slEl = document.getElementById('config-sl');
            const tpEl = document.getElementById('config-tp');
            const reverseEl = document.getElementById('config-reverse');
            
            if (symbolEl) symbolEl.value = trading.symbol || 'XAUUSD';
            if (lotEl) lotEl.value = trading.lot_size || 0.1;
            if (maxLotEl) maxLotEl.value = trading.max_lot || 1.0;
            if (slEl) slEl.value = trading.sl_points || 50;
            if (tpEl) tpEl.value = trading.tp_points || 100;
            if (reverseEl) reverseEl.checked = trading.allow_reverse !== false;
        }
    } catch (error) {
        console.error('加载配置失败:', error);
    }
}

async function saveConfig() {
    const config = {
        trading: {
            symbol: document.getElementById('config-symbol').value,
            lot_size: parseFloat(document.getElementById('config-lot').value),
            max_lot: parseFloat(document.getElementById('config-max-lot').value),
            sl_points: parseInt(document.getElementById('config-sl').value),
            tp_points: parseInt(document.getElementById('config-tp').value),
            allow_reverse: document.getElementById('config-reverse').checked
        }
    };
    
    try {
        const response = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        
        if (response.ok) {
            showNotification('配置保存成功!', 'success');
        }
    } catch (error) {
        console.error('保存配置失败:', error);
        showNotification('保存配置失败', 'danger');
    }
}

// ============================================
// 工具函数
// ============================================

function formatNumber(num) {
    return num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function showNotification(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    
    const icons = {
        success: 'check-circle',
        danger: 'exclamation-circle',
        warning: 'exclamation-triangle',
        info: 'info-circle'
    };
    
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <div class="d-flex align-items-center">
            <i class="fas fa-${icons[type]} me-3" style="font-size: 1.25rem;"></i>
            <div class="flex-grow-1">
                <strong>${type.charAt(0).toUpperCase() + type.slice(1)}</strong>
                <div>${message}</div>
            </div>
            <button type="button" class="btn-close ms-2" onclick="this.closest('.toast').remove()"></button>
        </div>
    `;
    
    container.appendChild(toast);
    
    setTimeout(() => {
        if (toast.parentNode) {
            toast.remove();
        }
    }, 5000);
}
