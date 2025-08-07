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
from common.types import HybridGenerationError
from typing import Tuple

class PromptBuilder:
    """プロンプト構築機能統合クラス"""

    def __init__(self, config: dict, prompts_data: dict, gen_types_data: dict):
        self.logger = ColorLogger()
        self.config = config
        self.prompts_data = prompts_data
        self.gen_types_data = gen_types_data

        # プロンプト要素の読み込み
        if 'quality_prompts' in self.prompts_data:
            # Ver3／SDXL統合構造
            self.quality_prompts = self.prompts_data.get('quality_prompts', {})
            self.face_prompts    = self.prompts_data.get('face_prompts', {})
            self.body_prompts    = self.prompts_data.get('body_prompts', {})
            self.other_prompts   = self.prompts_data.get('other_prompts', {})
            self.user_prompts    = self.prompts_data.get('user_prompts', {})
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

    def build_prompts(self, gen_type, mode: str="auto") -> Tuple[str,str,str]:
        """
        プロンプト構築入口
        Args:
            gen_type: GenerationType
            mode: "auto","basic","detailed","sdxl_unified"
        Returns:
            (prompt, negative_prompt, adetailer_negative)
        """
        if mode == "auto":
            if hasattr(self, 'quality_prompts'):
                if 'sdxl_unified' in self.quality_prompts:
                    return self.build_unified_sdxl_prompts(gen_type)
                else:
                    p1, p2, neg, adneg = self.build_detailed_prompts(gen_type)
                    return p2, neg, adneg
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

    def build_unified_sdxl_prompts(self, gen_type) -> Tuple[str,str,str]:
        """SDXL統合プロンプト構築"""
        def safe_get(d, key):
            v = d.get(key, "")
            if isinstance(v, dict):
                if "prompt" in v: return v["prompt"]
                if "text" in v:   return v["text"]
                return ", ".join(str(x) for x in v.values())
            return str(v) if v else ""

        # 手足品質強化要素
        hf = ""
        if self.anatomy_prompts:
            parts = []
            for k in ['accurate_hands','accurate_feet','perfect_anatomy','neck_position','skeletal_structure','full_anatomy']:
                parts.append(safe_get(self.anatomy_prompts, k))
            hf = ", " + ", ".join([p for p in parts if p])

        # ランダム要素
        additional = gen_type.random_elements  # 実際は RandomElementGenerator が付与

        # 年齢要素
        age = gen_type.age_range
        from random import randint
        selected_age = randint(age[0], age[1])
        age_prompt = f", BREAK, {selected_age} years old"

        # 基本要素結合
        parts = [
            safe_get(self.quality_prompts, 'sdxl_unified'),
            safe_get(self.face_prompts, 'sdxl_unified'),
            safe_get(self.body_prompts, 'sdxl_unified'),
            safe_get(self.user_prompts, 'nsfw_content'),
            safe_get(self.user_prompts, 'ethnicity'),
            safe_get(self.user_prompts, 'custom_addition'),
            str(gen_type.prompt)
        ]
        valid = [p for p in parts if p]
        prompt = ", ".join(valid) + hf + additional + age_prompt

        # LoRA と Pose は各マネージャで付与
        neg = safe_get(self.negative_prompts, 'comprehensive')
        if gen_type.negative_prompt:
            neg = f"{neg}, {gen_type.negative_prompt}" if neg else gen_type.negative_prompt
        adneg = safe_get(self.negative_prompts, 'adetailer_negative')
        if gen_type.negative_prompt:
            adneg = f"{adneg}, {gen_type.negative_prompt}" if adneg else gen_type.negative_prompt

        # 手足強化ネガティブ
        if hf:
            hf_neg = safe_get(self.negative_prompts, 'hand_foot_negative')
            ns_neg = safe_get(self.negative_prompts, 'neck_skeleton_negative')
            neg += f", {hf_neg}, {ns_neg}"
            adneg += f", {hf_neg}, {ns_neg}"

        return prompt, neg, adneg

    def build_detailed_prompts(self, gen_type, highres_mode="SDXL"):
        """詳細プロンプト構築（Phase1+Phase2 分離）"""
        def safe_get(d, key): return d.get(key,"")
        # Phase1
        p1 = ",".join(filter(None, [
            safe_get(self.quality_prompts, 'phase1_quality'),
            safe_get(self.face_prompts, 'phase1_face'),
            safe_get(self.body_prompts, 'phase1_body'),
            safe_get(self.user_prompts, 'nsfw_content'),
            gen_type.prompt
        ]))
        # Phase2
        key = 'phase2_face_sdxl' if highres_mode=="SDXL" else 'phase2_face_sd15'
        p2 = ",".join(filter(None, [
            safe_get(self.quality_prompts, 'phase2_quality'),
            safe_get(self.face_prompts, key),
            safe_get(self.body_prompts, 'phase2_body'),
            safe_get(self.user_prompts, 'nsfw_content'),
            safe_get(self.user_prompts, 'ethnicity'),
            safe_get(self.user_prompts, 'custom_addition'),
            gen_type.prompt
        ]))
        # ネガ
        neg = safe_get(self.negative_prompts, 'comprehensive')
        if gen_type.negative_prompt:
            neg = f"{neg}, {gen_type.negative_prompt}" if neg else gen_type.negative_prompt
        adneg = safe_get(self.negative_prompts, 'adetailer_negative')
        if gen_type.negative_prompt:
            adneg = f"{adneg}, {gen_type.negative_prompt}" if adneg else gen_type.negative_prompt

        # 手足品質
        hf = ""
        if self.anatomy_prompts:
            hf = ", ".join(filter(None, [
                safe_get(self.anatomy_prompts, 'accurate_hands'),
                safe_get(self.anatomy_prompts, 'accurate_feet'),
                safe_get(self.anatomy_prompts, 'perfect_anatomy')
            ]))
        if hf:
            p1 += ", " + hf
            p2 += ", " + hf
            neg += f", {safe_get(self.negative_prompts,'hand_foot_negative')}"
            adneg += f", {safe_get(self.negative_prompts,'hand_foot_negative')}"

        return p1, p2, neg, adneg

    def build_basic_prompts(self, gen_type):
        """基本プロンプト構築（旧 v2 互換）"""
        from random import randint
        age = gen_type.age_range
        selected_age = randint(age[0], age[1])
        age_prompt = f", BREAK, {selected_age} years old"

        # ランダム要素
        additional = gen_type.random_elements

        prompt = f"{self.core_prompt}, {self.beauty_prompt}, {gen_type.prompt}{additional}{age_prompt}"
        neg = f"{self.core_negative_prompt}, {self.beauty_negative_prompt}"
        if gen_type.negative_prompt:
            neg = f"{neg}, {gen_type.negative_prompt}"
        return prompt, prompt, neg, neg
