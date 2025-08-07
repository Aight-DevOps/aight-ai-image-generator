#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ImageGenerator メイン実行ファイル
- インタラクティブメニューによる画像生成機能呼び出し
"""

from common.logger import ColorLogger
from image_generator.core.generator import HybridBijoImageGeneratorV7
from image_generator.batch.processor import BatchProcessor

def main():
    logger = ColorLogger()
    logger.print_stage("🚀 美少女画像SDXL統合生成ツール 起動")

    # ジェネレータ初期化
    generator = HybridBijoImageGeneratorV7()
    batcher = BatchProcessor(generator, generator.config)

    # メニュー表示ループ
    while True:
        print("\n" + "="*80)
        print("📋 メインメニュー")
        print("="*80)
        print("1. 単発SDXL統合生成")
        print("2. 日次SDXL統合バッチ生成")
        print("3. 終了")
        print("="*80)

        choice = input("選択 (1-3): ").strip()
        if choice == '1':
            # ジャンルと枚数指定
            print(f"利用可能なジャンル: {[gt.name for gt in generator.generation_types]}")
            genre = input("ジャンル: ").strip()
            count = int(input("枚数: ").strip() or 1)
            batcher.generate_hybrid_batch(genre, count)
        elif choice == '2':
            batcher.generate_daily_hybrid_batch()
        elif choice == '3':
            break
        else:
            print("❌ 無効な選択です")

    logger.print_status("プログラム終了")

if __name__ == "__main__":
    main()
