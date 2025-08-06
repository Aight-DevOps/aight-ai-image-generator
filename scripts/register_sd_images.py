#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stable Diffusion Image Registration Script - SD画像登録実行スクリプト
"""

import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.append(str(Path(__file__).parent.parent))

from src.core.config_manager import ConfigManager
from src.register.sd_image_registrar import SDImageRegistrar
from src.utils.logger import ColorLogger

def main():
    """SD画像登録実行"""
    logger = ColorLogger()
    logger.print_stage("🚀 SD画像登録ツール開始")
    
    try:
        # 設定管理初期化
        config_manager = ConfigManager()
        
        # SD画像登録器初期化
        registrar = SDImageRegistrar(config_manager)
        
        logger.print_success("✅ SD画像登録器初期化完了")
        
        # 登録実行（メニュー表示・処理実行）
        registrar.show_menu_and_process()
        
    except KeyboardInterrupt:
        logger.print_warning("🛑 ユーザーによる中断")
    except Exception as e:
        logger.print_error(f"❌ エラー: {e}")
        import traceback
        traceback.print_exc()
    finally:
        logger.print_stage("👋 SD画像登録ツール終了")

if __name__ == "__main__":
    main()
