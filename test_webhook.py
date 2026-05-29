# Webhook 测试脚本
import requests
import json

# Webhook 地址
webhook_url = "http://localhost:8000/webhook"

print("=" * 60)
print("黄金量化交易系统 - Webhook 测试")
print("=" * 60)
print()

# 测试 1: 健康检查
print("测试 1: 健康检查...")
try:
    response = requests.get("http://localhost:8000/health")
    if response.status_code == 200:
        print("✅ 健康检查通过!")
        print(f"   响应: {response.json()}")
    else:
        print(f"❌ 健康检查失败，状态码: {response.status_code}")
except Exception as e:
    print(f"❌ 健康检查异常: {e}")

print()

# 测试 2: 发送买入信号
print("测试 2: 发送买入信号 (仅测试，不会实际下单)...")
buy_signal = {
    "strategy": "test_strategy",
    "action": "buy",
    "symbol": "XAUUSD",
    "lot": 0.1,
    "sl_points": 50,
    "tp_points": 100
}

try:
    response = requests.post(webhook_url, json=buy_signal)
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")
    
    if response.status_code == 200:
        print("✅ 信号发送成功!")
    else:
        print("⚠️  信号处理返回非 200 状态码")
except Exception as e:
    print(f"❌ 发送信号异常: {e}")

print()
print("=" * 60)
print("测试完成!")
print()
print("提示:")
print("- 如果测试 2 显示风控检查失败（如已有持仓），是正常的")
print("- 实际使用时请在 TradingView 中配置 Webhook 警报")
print("- 交易有风险，请先用模拟账户充分测试!")
