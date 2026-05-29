# 黄金量化交易系统

基于 TradingView 信号和 MT5 的全自动黄金 (XAUUSD) 量化交易系统。

## 系统架构

```
TradingView (策略)
    ↓ Webhook
FastAPI (Webhook 服务器)
    ↓
策略引擎 + 风控管理
    ↓
MT5 终端
    ↓
市场
```

## 功能特性

- ✅ **Webhook 接收**: 接收 TradingView 策略信号
- ✅ **自动交易**: 通过 MT5 自动执行买卖操作
- ✅ **风控管理**: 
  - 仓位大小计算
  - 止损止盈设置
  - 防重复开仓
  - 保证金检查
- ✅ **通知系统**: Telegram / 邮件通知
- ✅ **数据采集**: 自动采集行情数据和技术指标
- ✅ **AI 扩展**: 预留 AI 模型接口（可选）
- ✅ **日志系统**: 完善的日志记录

## 项目结构

```
gold_trading_bot/
├── config.yaml              # 配置文件
├── main.py                  # 程序入口
├── mt5_interface.py         # MT5 接口封装
├── risk_manager.py          # 风控管理
├── strategy_engine.py       # 策略引擎
├── webhook_server.py        # Webhook 服务器
├── notification.py          # 通知管理
├── ai_model.py              # AI 模型接口（可选）
├── data_collector.py        # 数据采集（可选）
├── requirements.txt         # 依赖包
└── utils/
    ├── logger.py            # 日志模块
    └── helpers.py           # 辅助函数
```

## 安装步骤

### 1. 环境要求

- Windows 系统（MT5 仅支持 Windows）
- Python 3.9+
- MT5 终端已安装并登录

### 2. 安装依赖

```bash
py -m pip install -r requirements.txt
```

### 3. 配置

编辑 `config.yaml` 文件：

```yaml
mt5:
  path: "C:\\Program Files\\MetaTrader 5\\terminal64.exe"  # MT5 安装路径
  login: 123456789                                          # 账户号
  password: "your_password"                                 # 密码
  server: "ICMarkets-Demo"                                  # 服务器

trading:
  symbol: "XAUUSD"          # 交易品种
  lot_size: 0.1             # 默认手数
  max_lot: 1.0              # 最大手数
  sl_points: 50             # 止损点数
  tp_points: 100            # 止盈点数
  allow_reverse: true       # 允许反手
```

## 使用方法

### 1. 启动系统

```bash
py main.py
```

### 2. TradingView Webhook 配置

在 TradingView 策略的警报设置中：

- **Webhook URL**: `http://your-server-ip:8000/webhook`
- **消息内容** (JSON 格式):

```json
{
  "strategy": "gold_strategy",
  "action": "buy",
  "symbol": "XAUUSD",
  "lot": 0.1,
  "sl_points": 50,
  "tp_points": 100
}
```

### 3. 信号说明

- `action`: "buy" / "sell" / "close" / "close_all"
- `symbol`: 交易品种
- `lot`: 手数（可选，使用配置默认值）
- `sl_points`: 止损点数（可选，使用配置默认值）
- `tp_points`: 止盈点数（可选，使用配置默认值）

## 注意事项

⚠️ **重要提醒**:
1. 此系统仅供学习和研究使用，实盘交易风险自负
2. 请先在模拟账户测试充分后再考虑实盘
3. 确保 MT5 终端始终保持运行
4. 建议在 VPS 上 24 小时运行
5. Webhook 服务应限制 IP 访问，确保安全

## 安全建议

- 使用防火墙限制 Webhook 端口访问
- 考虑在配置中添加 Webhook 密钥验证
- 定期备份配置和日志
- 监控系统运行状态

## 许可证

MIT License
