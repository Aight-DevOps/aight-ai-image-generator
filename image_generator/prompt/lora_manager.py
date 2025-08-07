#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
LoRAManager - LoRA プロンプト生成
- generation_types.yaml の lora_settings に基づいてプロンプトを構築
"""

import random

class LoRAManager:
    """LoRA プロンプト生成クラス"""

    def generate_lora_prompt(self, gen_type):
        """
        LoRAプロンプト生成
        Args:
            gen_type: GenerationType
        Returns:
            ', LoRAプロンプト...' または ''
        """
        if not hasattr(gen_type, 'lora_settings') or not gen_type.lora_settings:
            return ""

        lora_prompts = []
        for setting in gen_type.lora_settings:
            lora_id = setting.get('lora_id')
            strength_range = setting.get('strength_range', [0.5, 1.0])
            if not lora_id:
                continue

            min_s, max_s = strength_range
            # 0.01 刻みランダム
            steps = int((max_s - min_s) / 0.01) + 1
            strength = min_s + random.randint(0, steps - 1) * 0.01
            strength = round(strength, 2)
            lora_prompts.append(f"<lora:{lora_id}:{strength}>")

        return ", " + ", ".join(lora_prompts) if lora_prompts else ""
