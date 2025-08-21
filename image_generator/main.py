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
    """ポーズモード設定（永続化対応版）"""
    from .core.generator import HybridBijoImageGeneratorV7
    
    try:
        # ★ 修正: グローバルな設定永続化のため、設定ファイルに保存
        import json
        import os
        
        pose_config_file = "config/pose_mode.json"
        
        # 現在の設定読み込み
        current_mode = "detection"
        if os.path.exists(pose_config_file):
            try:
                with open(pose_config_file, 'r') as f:
                    pose_config = json.load(f)
                    current_mode = pose_config.get('pose_mode', 'detection')
            except:
                pass
        
        print(f"\n🎯 ポーズモード設定")
        print(f"現在のモード: {current_mode}")
        print("1. 検出モード（入力画像ベース・ControlNet使用）")
        print("2. 指定モード（プロンプトベース・ControlNet無効）")
        
        choice = input("選択 (1-2): ").strip()
        
        if choice == "1":
            new_mode = "detection"
            print("✅ ポーズ検出モードに設定されました")
            print("   - ControlNet (OpenPose + Depth) が有効になります")
        elif choice == "2":
            new_mode = "specification"
            print("✅ ポーズ指定モードに設定されました")
            print("   - ControlNetが無効になり、プロンプトベースのポーズが使用されます")
        else:
            print("❌ 無効な選択です")
            return
        
        # ★ 修正: 設定を永続化
        pose_config = {"pose_mode": new_mode}
        os.makedirs(os.path.dirname(pose_config_file), exist_ok=True)
        with open(pose_config_file, 'w') as f:
            json.dump(pose_config, f)
        
        print(f"✅ ポーズモードが '{new_mode}' に保存されました")
        
        # ★ 新機能: テスト生成の提案
        test_choice = input("\nテスト画像を1枚生成しますか？ (y/N): ").strip().lower()
        if test_choice == 'y':
            generator = HybridBijoImageGeneratorV7()
            if generator.generation_types:
                print("🎨 テスト画像生成中...")
                success = generator.generate_hybrid_image(generator.generation_types[0], 1)
                if success:
                    print("✅ テスト画像生成完了！")
                else:
                    print("❌ テスト画像生成失敗")
            
    except Exception as e:
        print(f"❌ ポーズモード設定エラー: {e}")
        import traceback
        traceback.print_exc()


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
