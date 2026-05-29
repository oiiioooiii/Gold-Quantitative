#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试AI功能 - 定位500错误原因
"""

import sys
import os

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.config import load_config
from mt5_interface import MT5Interface
from data_collector import DataCollector
from ai_model import AIModelManager
from risk_manager import RiskManager
from utils.logger import get_logger

logger = get_logger()

def test():
    """逐步测试AI功能"""
    print("=" * 60)
    print("开始测试AI功能")
    print("=" * 60)
    
    try:
        # 1. 加载配置
        print("\n[1/6] 加载配置...")
        config = load_config()
        print("✓ 配置加载成功")
        
        # 2. 初始化MT5接口
        print("\n[2/6] 初始化MT5接口...")
        mt5 = MT5Interface(config)
        if not mt5.initialize():
            print("✗ MT5初始化失败")
            return
        print("✓ MT5初始化成功")
        
        # 3. 测试数据采集器
        print("\n[3/6] 测试数据采集器...")
        try:
            collector = DataCollector(config, mt5)
            print("✓ 数据采集器初始化成功")
            
            # 测试获取AI特征
            print("正在获取AI特征...")
            features = collector.get_ai_features()
            print(f"✓ 获取到 {len(features)} 个AI特征")
            if len(features) > 0:
                print(f"部分特征: {list(features.keys())[:10]}")
        except Exception as e:
            print(f"✗ 数据采集器测试失败: {e}")
            import traceback
            print(traceback.format_exc())
            return
        
        # 4. 测试AI模型管理器
        print("\n[4/6] 测试AI模型管理器...")
        try:
            ai_manager = AIModelManager(config)
            print("✓ AI模型管理器初始化成功")
            
            # 测试生成信号
            print("正在生成AI信号...")
            signals = ai_manager.generate_signals(features)
            print(f"✓ 生成了 {len(signals)} 个信号")
            
            # 测试综合信号
            combined = ai_manager.get_combined_signal(features)
            print(f"✓ 综合信号: {combined.signal_type if combined else '无'}, 置信度: {combined.confidence if combined else 0}")
        except Exception as e:
            print(f"✗ AI模型管理器测试失败: {e}")
            import traceback
            print(traceback.format_exc())
            return
        
        # 5. 测试风控管理器
        print("\n[5/6] 测试风控管理器...")
        try:
            risk_manager = RiskManager(config, mt5)
            print("✓ 风控管理器初始化成功")
            
            # 测试AI风控
            print("正在计算AI风控参数...")
            risk_params = risk_manager.calculate_risk_params_with_ai(
                "XAUUSD", features, combined.confidence if combined else 0.5
            )
            print(f"✓ AI风控参数: {risk_params}")
        except Exception as e:
            print(f"✗ 风控管理器测试失败: {e}")
            import traceback
            print(traceback.format_exc())
            return
        
        # 6. 测试序列化
        print("\n[6/6] 测试JSON序列化...")
        try:
            # 测试AI分析结果序列化
            result = {
                "enabled": True,
                "features": features,
                "signals": [s.to_dict() for s in signals] if signals else [],
                "combined_signal": combined.to_dict() if combined else None,
                "risk_params": risk_params
            }
            
            import json
            json_str = json.dumps(result)
            print(f"✓ 序列化成功，长度: {len(json_str)} 字符")
        except Exception as e:
            print(f"✗ 序列化测试失败: {e}")
            import traceback
            print(traceback.format_exc())
            return
        
        print("\n" + "=" * 60)
        print("✅ 所有测试通过！")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        print(traceback.format_exc())
    finally:
        # 关闭MT5连接
        try:
            mt5.shutdown()
        except:
            pass

if __name__ == "__main__":
    test()
