#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Review System Launch Script - 検品システム実行スクリプト
"""

import sys
import subprocess
from pathlib import Path

def main():
    """検品システム実行"""
    print("🚀 美少女画像検品システム Ver7.2 起動中...")
    
    try:
        # Streamlitアプリを実行
        app_path = Path(__file__).parent.parent / "src" / "review" / "review.py"
        
        # Streamlitコマンド実行
        cmd = ["streamlit", "run", str(app_path)]
        
        print(f"✅ コマンド実行: {' '.join(cmd)}")
        print("🌐 ブラウザでアプリが開きます...")
        print("🛑 終了するには Ctrl+C を押してください")
        
        # Streamlitアプリを起動
        subprocess.run(cmd)
        
    except KeyboardInterrupt:
        print("\n🛑 ユーザーによる中断")
    except FileNotFoundError:
        print("❌ Streamlitがインストールされていません")
        print("💡 以下のコマンドでインストールしてください:")
        print("   pip install streamlit")
    except Exception as e:
        print(f"❌ エラー: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("👋 検品システム終了")

if __name__ == "__main__":
    main()
