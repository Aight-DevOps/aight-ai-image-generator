#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Image Generator Main Entry Point
"""

import sys
import os

def show_interactive_menu():
    """インタラクティブCUIメニュー表示"""
    from common.logger import ColorLogger
    logger = ColorLogger()
    logger.print_stage("🎨 美少女画像生成ツール Ver7.0")

    while True:
        print("\n" + "="*60)
        print("📋 メイン機能選択")
        print("="*60)
        print("1. 画像生成（単発）")
        print("2. 画像生成（バッチ）")
        print("3. 日次バッチ生成")
        print("4. ポーズモード設定")
        print("5. 設定確認")
        print("6. 終了")
        print("="*60)

        try:
            choice = input("選択 (1-6): ").strip()
            if choice == "1":
                single_generation()
            elif choice == "2":
                batch_generation()
            elif choice == "3":
                daily_batch_generation()
            elif choice == "4":
                pose_mode_setting()
            elif choice == "5":
                show_config()
            elif choice == "6":
                logger.print_success("🔚 終了します")
                break
            else:
                print("❌ 無効な選択です")
        except KeyboardInterrupt:
            logger.print_warning("\n🛑 処理を中断しました")
            break

def single_generation():
    """単発画像生成"""
    from common.logger import ColorLogger
    logger = ColorLogger()

    try:
        from .core.generator import HybridBijoImageGeneratorV7
        from .batch.processor import BatchProcessor

        generator = HybridBijoImageGeneratorV7()
        processor = BatchProcessor(generator, generator.config)

        genres = [gt.name for gt in generator.generation_types]
        print("\n📂 ジャンル選択:")
        for i, genre in enumerate(genres, 1):
            print(f"{i}. {genre}")

        choice = input("ジャンル番号: ").strip()
        if not choice.isdigit() or int(choice) < 1 or int(choice) > len(genres):
            logger.print_error("❌ 無効な選択です")
            return

        genre = genres[int(choice)-1]
        gen_type = next(gt for gt in generator.generation_types if gt.name == genre)

        logger.print_stage(f"🎨 {genre} 画像生成開始")
        result = processor.generate_hybrid_image(gen_type, 1)
        logger.print_success(f"✅ 生成完了: {result}枚")

    except Exception as e:
        logger.print_error(f"❌ 生成エラー: {e}")
        import traceback; traceback.print_exc()
def batch_generation():
    """バッチ画像生成"""
    from common.logger import ColorLogger
    logger = ColorLogger()

    try:
        from .core.generator import HybridBijoImageGeneratorV7
        from .batch.processor import BatchProcessor

        generator = HybridBijoImageGeneratorV7()
        processor = BatchProcessor(generator, generator.config)

        genres = [gt.name for gt in generator.generation_types]
        print("\n📂 ジャンル選択:")
        for i, genre in enumerate(genres, 1):
            print(f"{i}. {genre}")

        choice = input("ジャンル番号: ").strip()
        if not choice.isdigit() or int(choice) < 1 or int(choice) > len(genres):
            logger.print_error("❌ 無効な選択です")
            return

        genre = genres[int(choice)-1]
        count = int(input("生成枚数: ").strip() or "1")

        logger.print_stage(f"🎨 {genre} バッチ生成開始 ({count}枚)")
        result = processor.generate_hybrid_batch(genre, count)
        logger.print_success(f"✅ 生成完了: {result}枚")

    except Exception as e:
        logger.print_error(f"❌ 生成エラー: {e}")
        import traceback; traceback.print_exc()

def daily_batch_generation():
    """日次バッチ生成"""
    from common.logger import ColorLogger
    logger = ColorLogger()

    try:
        from .core.generator import HybridBijoImageGeneratorV7
        from .batch.processor import BatchProcessor

        generator = HybridBijoImageGeneratorV7()
        processor = BatchProcessor(generator, generator.config)

        logger.print_stage("🌅 日次バッチ生成開始")
        processor.generate_daily_hybrid_batch()

    except Exception as e:
        logger.print_error(f"❌ 生成エラー: {e}")
        import traceback; traceback.print_exc()

def pose_mode_setting():
    """ポーズモード設定"""
    print("\n🎯 ポーズモード設定")
    print("1. 検出モード（入力画像ベース）")
    print("2. 指定モード（プロンプトベース）")

    choice = input("選択 (1-2): ").strip()
    if choice == "1":
        print("✅ ポーズ検出モードに設定されました")
    elif choice == "2":
        print("✅ ポーズ指定モードに設定されました")
    else:
        print("❌ 無効な選択です")

def show_config():
    """設定確認"""
    from common.logger import ColorLogger
    logger = ColorLogger()

    try:
        from .core.generator import HybridBijoImageGeneratorV7
        generator = HybridBijoImageGeneratorV7()

        print("\n📋 現在の設定:")
        print(f"- ローカルモード: {generator.config.get('local_execution', {}).get('enabled', False)}")
        print(f"- 高速モード: {generator.config.get('fast_mode', {}).get('enabled', False)}")
        print(f"- Bedrock: {generator.config.get('bedrock_features', {}).get('enabled', False)}")
        print(f"- AWS リージョン: {generator.config.get('aws', {}).get('region', 'N/A')}")
        print(f"- 生成タイプ: {len(generator.generation_types)}種類")

    except Exception as e:
        logger.print_error(f"❌ 設定読み込みエラー: {e}")
        import traceback; traceback.print_exc()
def main():
    """メインエントリーポイント"""
    try:
        if len(sys.argv) >= 2 and sys.argv[1] == "batch":
            from .core.generator import HybridBijoImageGeneratorV7
            from .batch.processor import BatchProcessor

            generator = HybridBijoImageGeneratorV7()
            processor = BatchProcessor(generator, generator.config)

            genre = sys.argv[2]
            count = int(sys.argv[3]) if len(sys.argv) >= 4 else 1

            if genre == "daily":
                processor.generate_daily_hybrid_batch()
            else:
                processor.generate_hybrid_batch(genre, count)
        elif len(sys.argv) == 1:
            show_interactive_menu()
        else:
            print("使用方法:")
            print("  python3 -m image_generator.main             # インタラクティブモード")
            print("  python3 -m image_generator.main batch <genre> [count]  # バッチモード")
            print("  python3 -m image_generator.main batch daily          # 日次バッチ")
    except Exception as e:
        from common.logger import ColorLogger
        logger = ColorLogger()
        logger.print_error(f"❌ メインエラー: {e}")
        import traceback; traceback.print_exc()

if __name__ == "__main__":
    main()
