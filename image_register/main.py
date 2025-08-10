#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Hybrid Bijo Register メイン実行（CLI版）
- 完全なCLIベースのメニュー実行
- リファクタリング前仕様完全再現
"""

import sys
import os

# パス設定
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.logger import ColorLogger
from image_register.core.register import HybridBijoRegisterV9

def main():
    """メイン関数（完全CLI版）"""
    try:
        print("🚀 Hybrid Bijo Register v9 (DynamoDB Float型エラー修正版) 開始")
        print("🔧 修正内容: Float型をDecimal型に自動変換してDynamoDB登録")
        print("✅ DynamoDB互換性完全対応")
        print("Ctrl+Cで中断できます")
        
        register = HybridBijoRegisterV9()
        register.show_menu_and_process()
        
    except KeyboardInterrupt:
        print("\n🛑 ユーザーによる中断")
    except Exception as e:
        print(f"❌ エラー: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("👋 プログラム終了")

if __name__ == "__main__":
    main()
