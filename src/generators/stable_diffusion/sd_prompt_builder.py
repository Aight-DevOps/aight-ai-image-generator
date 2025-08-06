#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stable Diffusion Prompt Builder - SD専用プロンプト構築クラス
"""

import secrets
from typing import Tuple, Dict, Any
from ...core.config_manager import ConfigManager
from ...core.exceptions import HybridGenerationError
from .sd_random_generator import RandomElementGenerator, EnhancedSecureRandom

class SDPromptBuilder:
    """Stable Diffusion専用プロンプト構築クラス"""

    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.random_gen: RandomElementGenerator = None  # 後に設定
        self.pose_mode: str = None
        self._load_prompt_data()

    def _load_prompt_data(self):
        try:
            cfg = self.config_manager
            rnd = cfg.load_config("random_elements")
            prm = cfg.load_config("prompts")
            gen = cfg.load_config("generation_types")
            self.specific = rnd.get("specific_random_elements", {})
            self.general = rnd.get("general_random_elements", {})
            # YAML構造に応じたデータ保持
            self.quality = prm.get("quality_prompts", {})
            self.face = prm.get("face_prompts", {})
            self.body = prm.get("body_prompts", {})
            self.neg = prm.get("negative_prompts", {})
        except Exception as e:
            raise HybridGenerationError(f"プロンプト読み込みエラー: {e}")

    def set_random_element_generator(self, gen: RandomElementGenerator):
        self.random_gen = gen

    def set_pose_mode(self, mode: str):
        self.pose_mode = mode

    def build_prompts(self, gen_type: Any, mode: str = "auto") -> Tuple[str, str, str]:
        # ここでは統一SDXLプロンプトのみ対応
        return self.build_unified_sdxl_prompts(gen_type)

    def build_unified_sdxl_prompts(self, gen_type: Any) -> Tuple[str, str, str]:
        parts = []
        parts += [self.quality.get("sdxl_unified", "")]
        parts += [self.face.get("sdxl_unified", "")]
        parts += [self.body.get("sdxl_unified", "")]
        # random elements
        if self.random_gen:
            parts.append(self.random_gen.generate_elements(gen_type))
        prompt = ", ".join([p for p in parts if p])
        neg = self.neg.get("comprehensive", "")
        if hasattr(gen_type, "negative_prompt"):
            neg = f"{neg}, {gen_type.negative_prompt}" if neg else gen_type.negative_prompt
        ad_neg = self.neg.get("adetailer_negative", "")
        return prompt, neg, ad_neg
