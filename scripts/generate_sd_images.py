#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stable Diffusion Image Generation Script - SD画像生成実行スクリプト（メニュー機能復活版）
"""

import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.append(str(Path(__file__).parent.parent))

from src.core.config_manager import ConfigManager
from src.generators.stable_diffusion.sd_generator import StableDiffusionGenerator
from src.utils.logger import ColorLogger

class SDImageGenerationMenu:
    """SD画像生成メニュークラス"""
    
    def __init__(self):
        self.logger = ColorLogger()
        self.config_manager = None
        self.generator = None
    
    def initialize_system(self):
        """システム初期化"""
        try:
            self.logger.print_stage("🚀 Stable Diffusion画像生成ツール開始")
            
            # 設定管理初期化
            self.config_manager = ConfigManager()
            
            # SD生成器初期化
            self.generator = StableDiffusionGenerator(self.config_manager)
            
            self.logger.print_success("✅ SD生成器初期化完了")
            return True
            
        except Exception as e:
            self.logger.print_error(f"❌ 初期化エラー: {e}")
            return False
    
    def show_main_menu(self):
        """メインメニュー表示"""
        while True:
            print("\n" + "="*60)
            print("🎨 Stable Diffusion画像生成ツール v7.0")
            print("="*60)
            print("1. バッチ画像生成")
            print("2. 単発画像生成")
            print("3. 設定確認")
            print("4. 終了")
            print("="*60)
            
            try:
                choice = input("選択 (1-4): ").strip()
                
                if choice == '1':
                    self.batch_generation_menu()
                elif choice == '2':
                    self.single_generation_menu()
                elif choice == '3':
                    self.show_settings()
                elif choice == '4':
                    break
                else:
                    print("❌ 無効な選択です")
                    
            except KeyboardInterrupt:
                print("\n🛑 ユーザーによる中断")
                break
    
    def batch_generation_menu(self):
        """バッチ生成メニュー"""
        print("\n" + "="*50)
        print("📊 バッチ画像生成")
        print("="*50)
        
        # ポーズモード選択
        pose_mode = self.select_pose_mode()
        if pose_mode is None:
            return
        
        self.generator.set_pose_mode(pose_mode)
        
        # ジャンル選択
        genre = self.select_genre()
        if genre is None:
            return
        
        # 生成枚数入力
        try:
            count = int(input("生成枚数 (1-50): "))
            if count < 1 or count > 50:
                print("❌ 1-50の範囲で入力してください")
                return
        except ValueError:
            print("❌ 数値を入力してください")
            return
        
        # 確認
        local_mode = self.config_manager.is_local_mode()
        mode_text = "ローカル保存" if local_mode else "AWS連携"
        
        print(f"\n📋 実行確認")
        print(f"ジャンル: {genre}")
        print(f"ポーズモード: {pose_mode}")
        print(f"生成枚数: {count}枚")
        print(f"実行モード: {mode_text}")
        
        confirm = input("\n実行しますか？ (y/N): ").strip().lower()
        if confirm != 'y':
            print("❌ 実行をキャンセルしました")
            return
        
        # バッチ生成実行
        self.logger.print_stage(f"🎨 {genre} バッチ生成開始")
        success_count = self.generator.run_batch_generation(genre, count)
        self.logger.print_success(f"🎉 バッチ生成完了: {success_count}/{count}枚成功")
    
    def single_generation_menu(self):
        """単発生成メニュー"""
        print("\n" + "="*50)
        print("🎯 単発画像生成")
        print("="*50)
        
        # ポーズモード選択
        pose_mode = self.select_pose_mode()
        if pose_mode is None:
            return
        
        self.generator.set_pose_mode(pose_mode)
        
        # ジャンル選択
        genre = self.select_genre()
        if genre is None:
            return
        
        # 確認
        local_mode = self.config_manager.is_local_mode()
        mode_text = "ローカル保存" if local_mode else "AWS連携"
        
        print(f"\n📋 実行確認")
        print(f"ジャンル: {genre}")
        print(f"ポーズモード: {pose_mode}")
        print(f"生成枚数: 1枚")
        print(f"実行モード: {mode_text}")
        
        confirm = input("\n実行しますか？ (y/N): ").strip().lower()
        if confirm != 'y':
            print("❌ 実行をキャンセルしました")
            return
        
        # 単発生成実行
        gen_type = self.generator.get_generation_type(genre)
        if not gen_type:
            self.logger.print_error(f"❌ 未知のジャンル: {genre}")
            return
        
        try:
            self.logger.print_stage(f"🎨 {genre} 単発生成開始")
            image_path, metadata = self.generator.generate_image(gen_type)
            
            if self.generator.upload_and_save(image_path, metadata):
                self.logger.print_success(f"🎉 単発生成完了: {image_path}")
            else:
                self.logger.print_error("❌ 保存処理に失敗しました")
                
        except Exception as e:
            self.logger.print_error(f"❌ 単発生成エラー: {e}")
    
    def select_pose_mode(self):
        """ポーズモード選択"""
        print("\n🎯 ポーズモード選択")
        print("1. ポーズ検出モード（入力画像ベース）")
        print("2. ポーズ指定モード（プロンプトベース）")
        
        try:
            choice = input("選択 (1-2): ").strip()
            if choice == '1':
                self.logger.print_success("✅ ポーズ検出モード（入力画像ベース）を選択しました")
                return "detection"
            elif choice == '2':
                self.logger.print_success("✅ ポーズ指定モード（プロンプトベース）を選択しました")
                return "specification"
            else:
                print("❌ 無効な選択です")
                return None
                
        except KeyboardInterrupt:
            print("\n🛑 ポーズモード選択が中断されました")
            return None
    
    def select_genre(self):
        """ジャンル選択"""
        available_genres = self.generator.get_available_genres()
        
        print("\n📋 ジャンル選択")
        for i, genre in enumerate(available_genres, 1):
            print(f"{i}. {genre}")
        
        try:
            choice = input(f"選択 (1-{len(available_genres)}): ").strip()
            choice_num = int(choice)
            
            if 1 <= choice_num <= len(available_genres):
                selected_genre = available_genres[choice_num - 1]
                self.logger.print_success(f"✅ ジャンル '{selected_genre}' を選択しました")
                return selected_genre
            else:
                print("❌ 無効な選択です")
                return None
                
        except ValueError:
            print("❌ 数値を入力してください")
            return None
        except KeyboardInterrupt:
            print("\n🛑 ジャンル選択が中断されました")
            return None
    
    def show_settings(self):
        """設定確認表示"""
        print("\n" + "="*50)
        print("⚙️ 現在の設定")
        print("="*50)
        
        # 基本設定
        local_mode = self.config_manager.is_local_mode()
        fast_mode = self.config_manager.is_fast_mode()
        bedrock_enabled = self.config_manager.is_bedrock_enabled()
        
        print(f"実行モード: {'ローカル' if local_mode else 'AWS連携'}")
        print(f"高速化モード: {'有効' if fast_mode else '無効'}")
        print(f"Bedrock機能: {'有効' if bedrock_enabled else '無効'}")
        
        # SDXL設定
        sdxl_config = self.config_manager.get_sdxl_generation_config()
        print(f"解像度: {sdxl_config.get('width', 896)}x{sdxl_config.get('height', 1152)}")
        print(f"ステップ数: {sdxl_config.get('steps', 30)}")
        print(f"CFG Scale: {sdxl_config.get('cfg_scale', 7.0)}")
        print(f"サンプラー: {sdxl_config.get('sampler_name', 'DPM++ 2M Karras')}")
        
        # 利用可能ジャンル
        available_genres = self.generator.get_available_genres()
        print(f"利用可能ジャンル: {', '.join(available_genres)}")
        
        # メモリ管理設定
        memory_stats = self.generator.memory_manager.get_memory_stats()
        print(f"メモリ監視: {'有効' if memory_stats['monitoring_enabled'] else '無効'}")
        print(f"ウルトラセーフモード: {'有効' if memory_stats['ultra_safe_mode'] else '無効'}")
        
        input("\nEnterキーを押して戻る...")

def main():
    """メイン関数"""
    menu = SDImageGenerationMenu()
    
    try:
        # システム初期化
        if not menu.initialize_system():
            return
        
        # メインメニュー表示
        menu.show_main_menu()
        
    except KeyboardInterrupt:
        menu.logger.print_warning("🛑 ユーザーによる中断")
    except Exception as e:
        menu.logger.print_error(f"❌ エラー: {e}")
        import traceback
        traceback.print_exc()
    finally:
        menu.logger.print_stage("👋 SD画像生成ツール終了")

if __name__ == "__main__":
    main()
