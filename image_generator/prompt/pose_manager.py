#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PoseManager - ポーズ制御機能
- ポーズモード選択（detection / specification）
- ポーズプロンプト生成
"""

from common.logger import ColorLogger
from random import choice

class PoseManager:
    """ポーズ制御管理クラス"""

    def __init__(self, specific_random_elements):
        """
        Args:
            specific_random_elements: random_elements.yaml の内容 dict
        """
        self.logger = ColorLogger()
        self.pose_mode = None  # "detection" or "specification"
        self.specific_random_elements = specific_random_elements

    def setup_pose_mode(self):
        """初期ポーズモード設定"""
        self.pose_mode = None
        self.logger.print_status("🎯 ポーズモード設定初期化完了")

    def select_pose_mode(self):
        """ポーズモード選択インタラクティブ"""
        while True:
            print("\n" + "="*50)
            print("🎯 ポーズモード選択")
            print("="*50)
            print("1. ポーズ検出モード（入力画像ベース）")
            print("2. ポーズ指定モード（プロンプトベース）")
            print("="*50)
            try:
                choice_idx = input("選択 (1-2): ").strip()
                if choice_idx == '1':
                    self.pose_mode = "detection"
                    self.logger.print_success("✅ ポーズ検出モードを選択")
                    break
                elif choice_idx == '2':
                    self.pose_mode = "specification"
                    self.logger.print_success("✅ ポーズ指定モードを選択")
                    break
                else:
                    print("❌ 無効な選択です")
            except KeyboardInterrupt:
                print("\n🛑 ポーズモード選択が中断されました")
                raise

    def generate_pose_prompt(self, gen_type):
        """
        ポーズプロンプト生成（ポーズ指定モード用）
        Args:
            gen_type: GenerationType
        Returns:
            ", pose_text" または ""
        """
        if self.pose_mode != "specification":
            return ""

        poses = self.specific_random_elements.get('poses', [])
        if not poses:
            self.logger.print_warning("⚠️ poses カテゴリが見つかりません")
            return ""

        selected_pose = choice(poses)
        self.logger.print_status(f"🎯 選択されたポーズ: {selected_pose}")
        return f", {selected_pose}"
