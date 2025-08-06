#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuration Manager - 設定ファイル管理クラス
"""

import yaml
from pathlib import Path
from typing import Any, Dict
from .exceptions import ConfigurationError

class ConfigManager:
    """設定ファイル管理クラス"""

    def __init__(self, config_dir: str = "config"):
        """
        Args:
            config_dir: 設定ファイルディレクトリ
        """
        self.config_dir = Path(config_dir)
        self._configs: Dict[str, Any] = {}
        self._main_config: Dict[str, Any] = {}
        self._load_main_config()

    def _load_main_config(self):
        """メイン設定ファイル読み込み（互換性対応）"""
        for filename in ("config_v10.yaml", "config_v5.yaml", "config.yaml"):
            path = self.config_dir / filename
            if not path.exists():
                continue
            try:
                with path.open("r", encoding="utf-8") as f:
                    self._main_config = yaml.safe_load(f)
                print(f"✅ {filename} 読み込み成功")
                return
            except yaml.YAMLError as e:
                print(f"❌ {filename} 読み込みエラー: {e}")
        raise ConfigurationError(
            "設定ファイルが見つかりません（config_v10.yaml, config_v5.yaml または config.yaml を配置してください）"
        )

    def load_config(self, name: str) -> Dict[str, Any]:
        """
        指定された設定ファイルを読み込み
        Args:
            name: 設定ファイル名（拡張子なし）
        Returns:
            設定データ
        """
        if name in self._configs:
            return self._configs[name]
        path = self.config_dir / f"{name}.yaml"
        if not path.exists():
            raise ConfigurationError(f"設定ファイルが見つかりません: {path}")
        try:
            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            self._configs[name] = data
            return data
        except yaml.YAMLError as e:
            raise ConfigurationError(f"YAML読み込みエラー {path}: {e}")

    def get_config(self, name: str) -> Dict[str, Any]:
        """
        設定を取得（メイン設定優先、その後個別ファイル）
        Args:
            name: 設定名
        Returns:
            設定データ
        """
        if name in self._main_config:
            return self._main_config[name]  # type: ignore
        return self.load_config(name)

    def get_main_config(self) -> Dict[str, Any]:
        """メイン設定ファイル全体を取得"""
        return self._main_config

    def get_aws_config(self) -> Dict[str, Any]:
        """AWS設定を取得"""
        return self._main_config.get("aws", {})  # type: ignore

    def get_bedrock_config(self) -> Dict[str, Any]:
        """Bedrock設定を取得"""
        return self._main_config.get("bedrock_features", {})  # type: ignore

    def get_local_execution_config(self) -> Dict[str, Any]:
        """ローカル実行設定を取得"""
        return self._main_config.get("local_execution", {})  # type: ignore

    def get_memory_management_config(self) -> Dict[str, Any]:
        """メモリ管理設定を取得"""
        return self._main_config.get("memory_management", {})  # type: ignore

    def get_sdxl_generation_config(self) -> Dict[str, Any]:
        """SDXL生成設定を取得"""
        return self._main_config.get("sdxl_generation", {})  # type: ignore

    def get_controlnet_config(self) -> Dict[str, Any]:
        """ControlNet設定を取得"""
        return self._main_config.get("controlnet", {})  # type: ignore

    def get_input_images_config(self) -> Dict[str, Any]:
        """入力画像設定を取得"""
        return self._main_config.get("input_images", {})  # type: ignore

    def get_adetailer_config(self) -> Dict[str, Any]:
        """ADetailer設定を取得"""
        return self._main_config.get("adetailer", {})  # type: ignore

    def get_fast_mode_config(self) -> Dict[str, Any]:
        """高速化モード設定を取得"""
        return self._main_config.get("fast_mode", {})  # type: ignore

    def get_temp_files_config(self) -> Dict[str, Any]:
        """一時ファイル設定を取得"""
        return self._main_config.get("temp_files", {})  # type: ignore

    def get_stable_diffusion_config(self) -> Dict[str, Any]:
        """Stable Diffusion API設定を取得"""
        return self._main_config.get("stable_diffusion", {})  # type: ignore

    def is_local_mode(self) -> bool:
        """ローカルモードかどうか"""
        return bool(self.get_local_execution_config().get("enabled", False))

    def is_fast_mode(self) -> bool:
        """高速化モードかどうか"""
        return bool(self.get_fast_mode_config().get("enabled", False))

    def is_bedrock_enabled(self) -> bool:
        """Bedrock機能が有効かどうか"""
        return bool(self.get_bedrock_config().get("enabled", False))

    def get_adetailer_config(self) -> Dict[str, Any]:
        """
        ADetailer 設定を取得
        """
        return self._main_config.get('adetailer', {})
