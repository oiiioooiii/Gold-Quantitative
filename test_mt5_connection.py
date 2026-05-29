# MT5 连接测试脚本
import MetaTrader5 as mt5
import sys
import os

print("=" * 60)
print("黄金量化交易系统 - MT5 连接测试")
print("=" * 60)
print()

# 测试 1: 尝试连接到已运行的 MT5
print("测试 1: 尝试连接到已运行的 MT5 终端...")
if mt5.initialize():
    print("✅ 成功连接到已运行的 MT5!")
    
    # 获取终端信息
    terminal_info = mt5.terminal_info()
    if terminal_info:
        print(f"   MT5 路径: {terminal_info.path}")
        print(f"   数据路径: {terminal_info.data_path}")
        print(f"   交易允许: {terminal_info.trade_allowed}")
    
    # 获取账户信息
    account_info = mt5.account_info()
    if account_info:
        print(f"   账户登录: {account_info.login}")
        print(f"   账户余额: {account_info.balance:.2f}")
        print(f"   服务器: {account_info.server}")
        print(f"   公司: {account_info.company}")
    else:
        print("⚠️  未检测到已登录账户，请先在 MT5 中登录!")
    
    # 获取 XAUUSD 价格
    print()
    print("测试 2: 获取 XAUUSD 价格...")
    symbol = "XAUUSD"
    tick = mt5.symbol_info_tick(symbol)
    if tick:
        print(f"✅ {symbol} 价格: 买价={tick.bid:.2f}, 卖价={tick.ask:.2f}")
    else:
        print(f"❌ 无法获取 {symbol} 价格，错误: {mt5.last_error()}")
        print("   请确保 MT5 中已添加 XAUUSD 品种!")
    
    print()
    print("✅ MT5 测试完成!")
    mt5.shutdown()
    sys.exit(0)
else:
    print("❌ 无法连接到已运行的 MT5!")
    print()
    
    # 检查常见问题
    print("可能的原因:")
    print("1. MT5 终端没有运行 - 请先手动打开 MT5")
    print("2. MT5 终端已启动但未登录账户 - 请先登录账户")
    print("3. Python 与 MT5 架构不一致（都是 64 位或都是 32 位）")
    print()
    
    # 尝试查找 MT5 安装路径
    print("正在搜索 MT5 安装路径...")
    common_paths = [
        r"C:\Program Files\MetaTrader 5\terminal64.exe",
        r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
        r"C:\Program Files\MetaTrader 5\terminal.exe",
    ]
    
    found_path = None
    for path in common_paths:
        if os.path.exists(path):
            found_path = path
            print(f"✅ 找到 MT5: {path}")
            break
    
    if found_path:
        print()
        print(f"建议您:")
        print(f"1. 手动运行: {found_path}")
        print(f"2. 在 MT5 中登录您的账户")
        print(f"3. 再次运行此测试脚本")
    else:
        print("❌ 未找到 MT5 常见安装位置，请确认 MT5 是否已安装")
    
    print()
    print("❌ 测试失败，请先完成上述步骤后重试!")
    sys.exit(1)
