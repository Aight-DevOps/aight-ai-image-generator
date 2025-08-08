#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PromptBuilder - プロンプト構築機能統合
"""

from common.logger import ColorLogger
from common.types import HybridGenerationError
from typing import Tuple, Dict, Any

class PromptBuilder:
    """プロンプト構築機能統合クラス"""

    def __init__(self, config: Dict[str, Any], prompts_data: Dict[str, Any], gen_types_data: Dict[str, Any]):
        self.logger = ColorLogger()
        self.config = config
        self.prompts_data = prompts_data
        self.gen_types_data = gen_types_data

        # プロンプト要素の読み込み
        if 'quality_prompts' in self.prompts_data:
            # Ver3／SDXL統合構造
            self.quality_prompts = self.prompts_data.get('quality_prompts', {})
            self.face_prompts = self.prompts_data.get('face_prompts', {})
            self.body_prompts = self.prompts_data.get('body_prompts', {})
            self.other_prompts = self.prompts_data.get('other_prompts', {})
            self.user_prompts = self.prompts_data.get('user_prompts', {})
            self.anatomy_prompts = self.prompts_data.get('anatomy_prompts', {})
            self.negative_prompts = self.prompts_data.get('negative_prompts', {})
        else:
            # Ver2 構造またはデフォルト
            self.quality_prompts = {"sdxl_unified": "masterpiece, best quality, ultra detailed"}
            self.face_prompts = {"sdxl_unified": "beautiful face, detailed eyes"}
            self.body_prompts = {"sdxl_unified": "perfect body"}
            self.other_prompts = {}
            self.user_prompts = {}
            self.anatomy_prompts = {}
            self.negative_prompts = {"comprehensive": "low quality, blurry, bad anatomy"}

    def build_prompts(self, gen_type, mode: str="auto") -> Tuple[str, str, str]:
        """
        プロンプト構築入口
        Args:
            gen_type: GenerationType
            mode: "auto","basic","detailed","sdxl_unified"
        Returns:
            (prompt, negative_prompt, adetailer_negative)
        """
        if mode == "auto":
            if 'sdxl_unified' in self.quality_prompts:
                return self.build_unified_sdxl_prompts(gen_type)
            else:
                return self.build_basic_prompts(gen_type)
        elif mode == "basic":
            return self.build_basic_prompts(gen_type)
        elif mode == "detailed":
            return self.build_detailed_prompts(gen_type)
        elif mode == "sdxl_unified":
            return self.build_unified_sdxl_prompts(gen_type)
        else:
            raise HybridGenerationError(f"Unknown prompt mode: {mode}")

    def build_unified_sdxl_prompts(self, gen_type) -> Tuple[str, str, str]:
        """SDXL統合プロンプト構築"""
        def safe_get(d, key):
            v = d.get(key, "")
            if isinstance(v, dict):
                if "prompt" in v: return v["prompt"]
                if "text" in v: return v["text"]
                return ", ".join(str(x) for x in v.values())
            return str(v) if v else ""

        # 年齢要素
        age = gen_type.age_range
        import random
        selected_age = random.randint(age[0], age[1])
        age_prompt = f", {selected_age} years old"

        # 基本要素結合
        parts = [
            safe_get(self.quality_prompts, 'sdxl_unified'),
            safe_get(self.face_prompts, 'sdxl_unified'),
            safe_get(self.body_prompts, 'sdxl_unified'),
            str(gen_type.prompt)
        ]
        valid = [p for p in parts if p]
        prompt = ", ".join(valid) + age_prompt

        # ネガティブプロンプト
        neg = safe_get(self.negative_prompts, 'comprehensive')
        if gen_type.negative_prompt:
            neg = f"{neg}, {gen_type.negative_prompt}" if neg else gen_type.negative_prompt

        adneg = safe_get(self.negative_prompts, 'adetailer_negative')
        if not adneg:
            adneg = neg  # フォールバック

        return prompt, neg, adneg

    def build_basic_prompts(self, gen_type) -> Tuple[str, str, str]:
        """基本プロンプト構築"""
        import random
        age = gen_type.age_range
        selected_age = random.randint(age[0], age[1])
        age_prompt = f", {selected_age} years old"

        prompt = f"masterpiece, best quality, {gen_type.prompt}{age_prompt}"
        neg = f"low quality, blurry, bad anatomy"
        if gen_type.negative_prompt:
            neg = f"{neg}, {gen_type.negative_prompt}"
        
        return prompt, neg, neg

    def build_detailed_prompts(self, gen_type, highres_mode="SDXL"):
        """詳細プロンプト構築（Phase1+Phase2 分離）"""
        # 簡易版実装
        return self.build_unified_sdxl_prompts(gen_type)
