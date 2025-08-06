# src/core/base_generator.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Base Generator - 画像生成器の基底クラス
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple, Optional
from .config_manager import ConfigManager
from .aws_manager import AWSManager
from .exceptions import HybridGenerationError

class GenerationType:
    """生成タイプクラス"""

    def __init__(
        self,
        name: str,
        model_name: str,
        prompt: str,
        negative_prompt: str,
        random_elements=None,
        age_range=None,
        lora_settings=None
    ):
        self.name = name
        self.model_name = model_name
        self.prompt = prompt
        self.negative_prompt = negative_prompt
        self.random_elements = random_elements or []
        self.age_range = age_range or [18, 24]
        self.lora_settings = lora_settings or []

class BaseImageGenerator(ABC):
    """画像生成器の基底クラス"""

    def __init__(self, config_manager: ConfigManager):
        """
        Args:
            config_manager: 設定管理クラスインスタンス
        """
        self.config_manager = config_manager
        self.aws_manager = AWSManager(config_manager)
        self.logger = None  # 各実装で設定
        self.generation_types: list[GenerationType] = []
        self.local_mode = config_manager.is_local_mode()
        self.fast_mode = config_manager.is_fast_mode()
        self.bedrock_enabled = config_manager.is_bedrock_enabled()
        self._setup_base_components()

    def _setup_base_components(self):
        """共通コンポーネント初期化"""
        self.main_config = self.config_manager.get_main_config()
        self._load_generation_types()

    def _load_generation_types(self):
        """generation_types.yaml から Type オブジェクトを生成"""
        data = self.config_manager.load_config("generation_types")
        for td in data.get("generation_types", []):
            # teen/jk は age>=18 へ補正
            if td["name"] in ("teen", "jk"):
                td["age_range"] = [18, td.get("age_range", [18, 24])[1]]
            gt = GenerationType(
                name=td["name"],
                model_name=td["model_name"],
                prompt=td["prompt"],
                negative_prompt=td["negative_prompt"],
                random_elements=td.get("random_elements", []),
                age_range=td.get("age_range", [18, 24]),
                lora_settings=td.get("lora_settings", []),
            )
            self.generation_types.append(gt)
        if self.logger:
            names = [g.name for g in self.generation_types]
            self.logger.print_status(f"📋 生成タイプ読み込み完了: {names}")

    def get_generation_type(self, name: str) -> Optional[GenerationType]:
        """名前で GenerationType を取得"""
        return next((g for g in self.generation_types if g.name == name), None)

    def get_available_genres(self) -> list[str]:
        """利用可能ジャンル一覧取得"""
        return [g.name for g in self.generation_types]

    @abstractmethod
    def generate_image(self, gen_type: GenerationType, **kwargs) -> Tuple[str, Dict[str, Any]]:
        """
        画像生成抽象メソッド
        Returns: (画像パス, メタデータ)
        """
        pass

    @abstractmethod
    def build_prompts(self, gen_type: GenerationType, mode: str = "auto") -> Tuple[str, str]:
        """
        プロンプト構築抽象メソッド
        Returns: (prompt, negative_prompt)
        """
        pass

    def upload_and_save(self, image_path: str, metadata: Dict[str, Any]) -> bool:
        """
        生成後の S3 アップロード + DynamoDB 保存を実施
        """
        if self.local_mode:
            if self.logger:
                self.logger.print_status("⚠️ ローカルモード: 保存処理をスキップ")
            return True
        s3_key = metadata.get("s3Key", "")
        if s3_key:
            if not self.aws_manager.upload_to_s3(image_path, s3_key):
                return False
        return self.aws_manager.save_to_dynamodb(metadata)
