// 黄金量化交易系统 - 前端 JavaScript
let currentPage = 'dashboard';
let priceUpdateInterval = null;

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    initNavigation();
    loadPage('dashboard');
    startPriceUpdates();
});

// 导航初始化
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

// 加载页面
async function loadPage(page) {
    currentPage = page;
    
    try {
        const response = await fetch(`/api/page/${page}`);
        if (response.ok) {
            const html = await response.text();
            document.getElementById('main-content').innerHTML = html;
            
            // 页面特定初始化
            if (page === 'dashboard') {
                initDashboard();
            } else if (page === 'trade') {
                initTradePage();
            } else if (page === 'signals') {
                initSignalsPage();
            } else if (page === 'settings') {
                initSettingsPage();
            }
        }
    } catch (error) {
        console.error('加载页面失败:', error);
        showNotification('加载页面失败', 'danger');
    }
}

// 开始价格更新
function startPriceUpdates() {
    updatePrice();
    priceUpdateInterval = setInterval(updatePrice, 2000);
}

// 更新价格
async function updatePrice() {
    try {
        const response = await fetch('/api/price');
        if (response.ok) {
            const data = await response.json();
            updatePriceDisplay(data);
        }
    } catch (error) {
        console.error('获取价格失败:', error);
    }
}

// 更新价格显示
function updatePriceDisplay(data) {
    const priceElement = document.getElementById('current-price');
    const bidElement = document.getElementById('bid-price');
    const askElement = document.getElementById('ask-price');
    
    if (priceElement && data.ask) {
        priceElement.textContent = data.ask.toFixed(2);
    }
    if (bidElement) {
        bidElement.textContent = data.bid ? data.bid.toFixed(2) : '-';
    }
    if (askElement) {
        askElement.textContent = data.ask ? data.ask.toFixed(2) : '-';
    }
}

// 初始化仪表板
async function initDashboard() {
    await loadAccountInfo();
    await loadPositions();
    await updateSystemStatus();
}

// 加载账户信息
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

// 更新账户显示
function updateAccountDisplay(data) {
    const balanceEl = document.getElementById('account-balance');
    const equityEl = document.getElementById('account-equity');
    const profitEl = document.getElementById('account-profit');
    
    if (balanceEl && data.balance !== undefined) {
        balanceEl.textContent = `$${data.balance.toFixed(2)}`;
    }
    if (equityEl && data.equity !== undefined) {
        equityEl.textContent = `$${data.equity.toFixed(2)}`;
    }
    if (profitEl) {
        const profit = data.profit || 0;
        profitEl.textContent = `${profit >= 0 ? '+' : ''}$${profit.toFixed(2)}`;
        profitEl.className = `stat-value ${profit >= 0 ? '' : 'text-danger'}`;
    }
}

// 加载持仓
async function loadPositions() {
    try {
        const response = await fetch('/api/positions');
        if (response.ok) {
            const data = await response.json();
            updatePositionsTable(data);
        }
    } catch (error) {
        console.error('获取持仓失败:', error);
    }
}

// 更新持仓表格
function updatePositionsTable(positions) {
    const tbody = document.getElementById('positions-tbody');
    const countEl = document.getElementById('positions-count');
    
    if (!tbody) return;
    
    if (countEl) {
        countEl.textContent = positions.length;
    }
    
    if (positions.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="8" class="text-center text-muted py-4">
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
                <span class="position-badge ${pos.type === 0 ? 'long' : 'short'}">
                    ${pos.type === 0 ? '做多' : '做空'}
                </span>
            </td>
            <td>${pos.volume}</td>
            <td>${pos.openPrice.toFixed(2)}</td>
            <td>${pos.currentPrice.toFixed(2)}</td>
            <td class="${pos.profit >= 0 ? 'text-success' : 'text-danger'}">
                <strong>${pos.profit >= 0 ? '+' : ''}$${pos.profit.toFixed(2)}</strong>
            </td>
            <td>${pos.sl ? pos.sl.toFixed(2) : '-'}</td>
            <td>${pos.tp ? pos.tp.toFixed(2) : '-'}</td>
            <td>
                <button class="btn btn-sm btn-danger" onclick="closePosition(${pos.ticket})">
                    <i class="fas fa-times"></i> 平仓
                </button>
            </td>
        </tr>
    `).join('');
}

// 平仓
async function closePosition(ticket) {
    if (!confirm('确定要平掉这个仓位吗？')) return;
    
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

// 全部平仓
async function closeAllPositions() {
    if (!confirm('确定要平掉所有持仓吗？')) return;
    
    try {
        const response = await fetch('/api/positions/close-all', {
            method: 'POST'
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

// 更新系统状态
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

// 更新状态显示
function updateStatusDisplay(data) {
    const statusEl = document.getElementById('system-status');
    if (statusEl) {
        statusEl.className = `status-indicator ${data.mt5_connected ? 'online' : 'offline'}`;
        statusEl.innerHTML = `
            <span class="pulse"></span>
            ${data.mt5_connected ? 'MT5 已连接' : 'MT5 未连接'}
        `;
    }
}

// 初始化交易页面
function initTradePage() {
    updatePrice();
}

// 开仓
async function openPosition(action) {
    // 先尝试从快速交易框获取值，如果没有再从交易页面获取
    const lotInput = document.getElementById('quick-lot') || document.getElementById('trade-lot');
    const slInput = document.getElementById('quick-sl') || document.getElementById('trade-sl');
    const tpInput = document.getElementById('quick-tp') || document.getElementById('trade-tp');
    const symbolInput = document.getElementById('trade-symbol');
    
    const lot = parseFloat(lotInput ? lotInput.value : '0.1');
    const slPoints = parseInt(slInput ? slInput.value : '50');
    const tpPoints = parseInt(tpInput ? tpInput.value : '100');
    const symbol = symbolInput ? symbolInput.value : 'XAUUSD';
    
    if (isNaN(lot) || lot <= 0) {
        showNotification('请输入有效的手数', 'warning');
        return;
    }
    
    try {
        const response = await fetch('/api/trade', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                strategy: 'manual',
                action: action,
                symbol: symbol,
                lot: lot,
                sl_points: slPoints,
                tp_points: tpPoints
            })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showNotification('订单执行成功!', 'success');
            if (currentPage === 'dashboard') {
                await loadPositions();
                await loadAccountInfo();
            }
        } else {
            showNotification(result.message || '订单执行失败', 'danger');
        }
    } catch (error) {
        console.error('交易失败:', error);
        showNotification('交易失败', 'danger');
    }
}

// 初始化信号测试页面
function initSignalsPage() {
}

// 发送测试信号
async function sendTestSignal() {
    const signal = {
        strategy: 'test',
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
                <h5>${response.ok ? '✅ 信号处理成功' : '❌ 信号处理失败'}</h5>
                <pre class="mb-0">${JSON.stringify(result, null, 2)}</pre>
            </div>
        `;
        
        if (response.ok && currentPage === 'dashboard') {
            await loadPositions();
            await loadAccountInfo();
        }
    } catch (error) {
        console.error('发送信号失败:', error);
        showNotification('发送信号失败', 'danger');
    }
}

// 初始化设置页面
function initSettingsPage() {
    loadConfig();
}

// 加载配置
async function loadConfig() {
    try {
        const response = await fetch('/api/config');
        if (response.ok) {
            const config = await response.json();
            populateConfigForm(config);
        }
    } catch (error) {
        console.error('加载配置失败:', error);
    }
}

// 填充配置表单
function populateConfigForm(config) {
    const trading = config.trading || {};
    
    document.getElementById('config-symbol').value = trading.symbol || 'XAUUSD';
    document.getElementById('config-lot').value = trading.lot_size || 0.1;
    document.getElementById('config-max-lot').value = trading.max_lot || 1.0;
    document.getElementById('config-sl').value = trading.sl_points || 50;
    document.getElementById('config-tp').value = trading.tp_points || 100;
    document.getElementById('config-reverse').checked = trading.allow_reverse !== false;
}

// 保存配置
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

// 显示通知
function showNotification(message, type = 'info') {
    // 创建通知元素
    const notification = document.createElement('div');
    notification.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
    notification.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(notification);
    
    // 3秒后自动消失
    setTimeout(() => {
        if (notification.parentNode) {
            notification.remove();
        }
    }, 3000);
}
