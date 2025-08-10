#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Common types and data classes
共通データクラスと型定義
"""

class GenerationType:
    """生成タイプクラス"""
    
    def __init__(self, name, model_name, prompt, negative_prompt, random_elements=None, age_range=None, lora_settings=None):
        self.name = name
        self.model_name = model_name
        self.prompt = prompt
        self.negative_prompt = negative_prompt
        self.random_elements = random_elements or []
        self.age_range = age_range or [18, 24]
        self.lora_settings = lora_settings or []

class HybridGenerationError(Exception):
    """ハイブリッド生成専用エラー"""
    pass
