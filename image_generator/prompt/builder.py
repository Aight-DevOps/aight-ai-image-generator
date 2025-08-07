#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PromptBuilder - プロンプト構築機能統合
- build_prompts: 自動モード判定
- build_unified_sdxl_prompts: SDXL 統合プロンプト構築
- build_detailed_prompts: 詳細プロンプト構築（Phase1+Phase2 分離）
- build_basic_prompts: 基本プロンプト構築
"""

from common.logger import ColorLogger
from common.types import GenerationType, HybridGenerationError

class PromptBuilder:
    """プロンプト構築機能統合クラス"""

    def __init__(self, config, prompts_data, generation_types_data):
        self.logger = ColorLogger()
        self.config = config
        self.prompts_data = prompts_data
        self.generation_types_data = generation_types_data

        # プロンプト要素読み込み
        if 'quality_prompts' in self.prompts_data:
            # SDXL統合版 / Ver3 構造
            self.quality_prompts = self.prompts_data.get('quality_prompts', {})
            self.face_prompts = self.prompts_data.get('face_prompts', {})
            self.body_prompts = self.prompts_data.get('body_prompts', {})
            self.other_prompts = self.prompts_data.get('other_prompts', {})
            self.user_prompts = self.prompts_data.get('user_prompts', {})
            self.anatomy_prompts = self.prompts_data.get('anatomy_prompts', {})
            self.single_person_prompts = self.prompts_data.get('single_person_prompts', {})
            self.negative_prompts = self.prompts_data.get('negative_prompts', {})
        else:
            # Ver2 構造
            self.core_prompt = self.prompts_data.get('core_prompt', '')
            self.core_negative_prompt = self.prompts_data.get('core_negative_prompt', '')
            self.beauty_prompt = self.prompts_data.get('beauty_prompt', '')
            self.beauty_negative_prompt = self.prompts_data.get('beauty_negative_prompt', '')
            self.single_person_prompts = {}
            self.negative_prompts = {}

    def build_prompts(self, gen_type: GenerationType, mode: str = "auto"):
        """
        プロンプト構築メイン関数
        Args:
            gen_type: GenerationType オブジェクト
            mode: "auto", "basic", "detailed", "sdxl_unified"
        Returns:
            各モードに応じたプロンプトタプル
        """
        if mode == "auto":
            if hasattr(self, 'quality_prompts'):
                if 'sdxl_unified' in self.quality_prompts:
                    return self.build_unified_sdxl_prompts(gen_type)
                else:
                    return self.build_detailed_prompts(gen_type)
            else:
                return self.build_basic_prompts(gen_type)
        elif mode == "basic":
            return self.build_basic_prompts(gen_type)
        elif mode == "detailed":
            return self.build_detailed_prompts(gen_type)
        elif mode == "sdxl_unified":
            return self.build_unified_sdxl_prompts(gen_type)
        else:
            raise ValueError(f"Unknown prompt build mode: {mode}")

    def build_unified_sdxl_prompts(self, gen_type: GenerationType):
        """
        SDXL統合プロンプト構築（Phase1+Phase2 統合版）
        Returns: (prompt, negative_prompt, adetailer_negative)
        """
        # 手足品質向上要素
        hand_foot_quality = ""
        if hasattr(self, 'anatomy_prompts'):
            h = self.anatomy_prompts.get('accurate_hands', '')
            f = self.anatomy_prompts.get('accurate_feet', '')
            a = self.anatomy_prompts.get('perfect_anatomy', '')
            n = self.anatomy_prompts.get('neck_position', '')
            s = self.anatomy_prompts.get('skeletal_structure', '')
            k = self.anatomy_prompts.get('full_anatomy', '')
            hand_foot_quality = f", {h}, {f}, {a}, {n}, {s}, {k}"

        def safe_get(d: dict, key: str, default: str = "") -> str:
            if not isinstance(d, dict):
                return default
            v = d.get(key, default)
            if isinstance(v, dict):
                if "prompt" in v:
                    return str(v["prompt"])
                if "text" in v:
                    return str(v["text"])
                return ", ".join(str(x) for x in v.values() if x)
            return str(v) if v else default

        # ランダム要素と年齢プロンプト
        additional = gen_type.random_elements.__class__.__name__  # 実際は RandomElementGenerator 経由で生成
        min_age, max_age = gen_type.age_range
        age = __import__('common.randomization.secure_random').random.randint(min_age, max_age)
        age_prompt = f", BREAK, {age} years old"

        # ポーズプロンプト
        pose_prompt = ""  # PoseManager 経由

        # 一人強調要素
        single_person_emphasis = ""
        try:
            solo = self.single_person_prompts.get('solo_emphasis', '')
            if solo and solo.strip():
                single_person_emphasis = f", {solo}"
        except:
            pass

        # ランダム要素と基本要素組み合わせ
        parts = [
            safe_get(self.quality_prompts, 'sdxl_unified'),
            safe_get(self.face_prompts, 'sdxl_unified'),
            safe_get(self.body_prompts, 'sdxl_unified'),
            safe_get(self.user_prompts, 'nsfw_content'),
            safe_get(self.user_prompts, 'ethnicity'),
            safe_get(self.user_prompts, 'custom_addition'),
            str(gen_type.prompt) if gen_type.prompt else ""
        ]
        valid = [p for p in parts if p and p.strip()]
        unified = ", ".join(valid) + single_person_emphasis + additional + hand_foot_quality + age_prompt + pose_prompt

        # LoRA プロンプト
        lora_prompt = ""  # LoRAManager 経由
        unified += lora_prompt

        # ネガティブプロンプト
        base_neg = safe_get(self.negative_prompts, 'comprehensive')
        if gen_type.negative_prompt:
            if base_neg:
                base_neg = f"{base_neg}, {gen_type.negative_prompt}"
            else:
                base_neg = gen_type.negative_prompt

        ad_neg = safe_get(self.negative_prompts, 'adetailer_negative')
        if gen_type.negative_prompt:
            if ad_neg:
                ad_neg = f"{ad_neg}, {gen_type.negative_prompt}"
            else:
                ad_neg = gen_type.negative_prompt

        # 手足強化ネガティブ
        if hasattr(self, 'anatomy_prompts'):
            hf_neg = safe_get(self.negative_prompts, 'hand_foot_negative')
            ns_neg = safe_get(self.negative_prompts, 'neck_skeleton_negative')
            if hf_neg:
                base_neg = f"{base_neg}, {hf_neg}, {ns_neg}"
                ad_neg = f"{ad_neg}, {hf_neg}, {ns_neg}"

        return unified, base_neg, ad_neg
