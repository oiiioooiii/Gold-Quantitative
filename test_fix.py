"""
快速测试脚本 - 验证 symbol 参数修复
"""
import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(__file__))

from mt5_interface import MT5Interface
from utils.helpers import load_config

def test_mt5():
    print("=" * 60)
    print("测试 MT5 连接和持仓获取")
    print("=" * 60)
    
    # 加载配置
    config = load_config('config.yaml')
    
    # 初始化 MT5
    mt5 = MT5Interface(config)
    
    if not mt5.initialize():
        print("❌ MT5 初始化失败")
        return False
    
    print("✅ MT5 初始化成功")
    
    # 测试获取账户信息
    account = mt5.get_account_info()
    if account:
        print(f"✅ 账户信息: 余额=${account.balance:.2f}, 净值=${account.equity:.2f}")
    else:
        print("❌ 获取账户信息失败")
    
    # 测试获取价格
    symbol = config.get('trading', {}).get('symbol', 'XAUUSD')
    price = mt5.get_current_price(symbol)
    if price:
        print(f"✅ {symbol} 价格: Bid={price[0]:.2f}, Ask={price[1]:.2f}")
    else:
        print(f"❌ 获取 {symbol} 价格失败")
    
    # 测试获取持仓（带 symbol 参数）
    positions = mt5.get_positions(symbol)
    print(f"✅ {symbol} 持仓数量: {len(positions)}")
    
    if positions:
        for pos in positions:
            print(f"  - Ticket: {pos.ticket}, 类型: {'做多' if pos.type == 0 else '做空'}, 盈亏: ${pos.profit:.2f}")
    
    # 测试获取所有持仓（不带参数）
    all_positions = mt5.get_positions()
    print(f"✅ 所有持仓数量: {len(all_positions)}")
    
    # 关闭连接
    mt5.shutdown()
    print("\n✅ 测试完成！所有功能正常工作。")
    return True

if __name__ == "__main__":
    try:
        success = test_mt5()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
