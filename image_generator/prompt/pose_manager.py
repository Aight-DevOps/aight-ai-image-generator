#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PoseManager - ポーズ制御機能
- ポーズモード選択（detection / specification）
- ポーズプロンプト生成（設定ファイル対応版）
"""

from common.logger import ColorLogger
from random import choice
import json
import os

class PoseManager:
    """ポーズ制御管理クラス（設定ファイル対応版）"""

    def __init__(self, specific_random_elements):
        """
        Args:
            specific_random_elements: random_elements.yaml の内容 dict
        """
        self.logger = ColorLogger()
        self.specific_random_elements = specific_random_elements
        
        # ★ 修正: 設定ファイルからポーズモードを読み込み
        self.pose_config_file = "config/pose_mode.json"
        self.pose_mode = self._load_pose_mode()
        
        # デバッグ情報
        poses_count = len(self.specific_random_elements.get('poses', []))
        self.logger.print_status("🎯 ポーズマネージャー初期化完了")
        self.logger.print_status(f"📋 現在のモード: {self.pose_mode}")
        self.logger.print_status(f"📋 利用可能ポーズ数: {poses_count}")
        
        # フォールバックポーズ（yamlにposesがない場合用）
        self.fallback_poses = [
            "standing pose",
            "sitting pose", 
            "lying down",
            "crossed arms",
            "hands on hips",
            "peace sign",
            "waving hand",
            "looking back",
            "side profile",
            "close-up portrait"
        ]

    def _load_pose_mode(self):
        """設定ファイルからポーズモードを読み込み"""
        if os.path.exists(self.pose_config_file):
            try:
                with open(self.pose_config_file, 'r') as f:
                    pose_config = json.load(f)
                    mode = pose_config.get('pose_mode', 'detection')
                    self.logger.print_status(f"🔍 設定ファイルからポーズモード読み込み: {mode}")
                    return mode
            except Exception as e:
                self.logger.print_warning(f"⚠️ 設定ファイル読み込みエラー: {e}")
        
        # デフォルト値
        self.logger.print_status("🔍 デフォルトポーズモードを使用: detection")
        return "detection"

    def set_pose_mode(self, mode: str):
        """
        ポーズモードを設定（設定ファイルにも保存）
        Args:
            mode: "detection" または "specification"
        """
        if mode in ["detection", "specification"]:
            old_mode = self.pose_mode
            self.pose_mode = mode
            mode_text = "ポーズ検出モード" if mode == "detection" else "ポーズ指定モード"
            
            # 設定ファイルに保存
            try:
                pose_config = {"pose_mode": mode}
                os.makedirs(os.path.dirname(self.pose_config_file), exist_ok=True)
                with open(self.pose_config_file, 'w') as f:
                    json.dump(pose_config, f)
                self.logger.print_success(f"✅ ポーズモード変更: {old_mode} → {mode}")
                self.logger.print_success(f"✅ {mode_text}に設定・保存されました")
            except Exception as e:
                self.logger.print_error(f"❌ 設定保存エラー: {e}")
        else:
            self.logger.print_error(f"❌ 無効なポーズモード: {mode}")

    def get_pose_mode(self) -> str:
        """現在のポーズモードを取得"""
        # ★ 修正: 毎回設定ファイルから最新の値を読み込み
        current_mode = self._load_pose_mode()
        if current_mode != self.pose_mode:
            self.pose_mode = current_mode
            self.logger.print_status(f"🔄 ポーズモードを更新: {current_mode}")
        
        self.logger.print_status(f"🔍 現在のポーズモード: {self.pose_mode}")
        return self.pose_mode

    def generate_pose_prompt(self, gen_type):
        """
        ポーズプロンプト生成（強化版）
        Args:
            gen_type: GenerationType
        Returns:
            ", pose_text" または ""
        """
        # 最新のポーズモードを取得
        current_mode = self.get_pose_mode()
        
        self.logger.print_status(f"🔍 ポーズプロンプト生成開始:")
        self.logger.print_status(f"  - 現在のモード: {current_mode}")
        self.logger.print_status(f"  - ジャンル: {gen_type.name}")

        if current_mode != "specification":
            self.logger.print_status("🎯 ポーズ検出モード: ポーズプロンプトをスキップ")
            return ""

        # YAMLからポーズを取得
        poses = self.specific_random_elements.get('poses', [])
        self.logger.print_status(f"🔍 YAML posesデータ数: {len(poses)}")
        
        if not poses:
            self.logger.print_warning("⚠️ YAMLファイルにposesデータがありません")
            poses = self.fallback_poses
            self.logger.print_success(f"✅ フォールバックポーズを使用: {len(poses)}個")

        if not poses:
            self.logger.print_error("❌ 使用可能なポーズデータが全くありません")
            return ""

        selected_pose = choice(poses)
        self.logger.print_success(f"🎯 選択されたポーズ: {selected_pose}")
        self.logger.print_success(f"🎯 生成されるポーズプロンプト: '{selected_pose}'")
        
        return f", {selected_pose}"
