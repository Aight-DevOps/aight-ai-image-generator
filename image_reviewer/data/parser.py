#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
DataParser - DynamoDB AttributeValue 解析・プロンプト抽出機能
- parse_dynamodb_attribute_value
- extract_prompt_from_nested_structure
- extract_negative_prompt_from_nested_structure
- extract_lora_from_prompt
"""

import json
import re
from common.logger import ColorLogger

class DataParser:
    """DynamoDBデータ解析クラス"""

    def __init__(self, logger):
        self.logger = logger

    def parse_dynamodb_attribute_value(self, value):
        """AttributeValue形式を通常値に変換"""
        if isinstance(value, dict):
            if 'S' in value:
                return value['S']
            if 'N' in value:
                num = value['N']
                return float(num) if '.' in num else int(num)
            if 'BOOL' in value:
                return value['BOOL']
            if 'M' in value:
                return {k: self.parse_dynamodb_attribute_value(v) for k,v in value['M'].items()}
            if 'L' in value:
                return [self.parse_dynamodb_attribute_value(v) for v in value['L']]
            if 'SS' in value:
                return value['SS']
            if 'NS' in value:
                return [float(n) if '.' in n else int(n) for n in value['NS']]
            if 'NULL' in value:
                return None
        return value

    def extract_prompt_from_nested_structure(self, sd_params):
        """
        ネストしたsdParams構造からプロンプト抽出
        """
        prompts = {}
        # 直接フィールド
        direct = sd_params.get('prompt') or sd_params.get('PROMPT')
        if direct:
            prompts['direct'] = direct
        # sdxl_unified
        unified = sd_params.get('sdxl_unified')
        if isinstance(unified, dict):
            parsed = unified.get('M') and self.parse_dynamodb_attribute_value(unified) or unified
            p = parsed.get('prompt','')
            if p:
                prompts['sdxl_unified'] = p
        # base
        base = sd_params.get('base')
        if isinstance(base, dict):
            parsed = base.get('M') and self.parse_dynamodb_attribute_value(base) or base
            p = parsed.get('prompt','')
            if p:
                prompts['base'] = p
        return prompts

    def extract_negative_prompt_from_nested_structure(self, sd_params):
        """
        ネガティブプロンプト抽出
        """
        negs = {}
        direct = sd_params.get('negative_prompt') or sd_params.get('NEGATIVE_PROMPT')
        if direct:
            negs['direct'] = direct
        unified = sd_params.get('sdxl_unified')
        if isinstance(unified, dict):
            parsed = unified.get('M') and self.parse_dynamodb_attribute_value(unified) or unified
            n = parsed.get('negative_prompt','')
            if n:
                negs['sdxl_unified'] = n
        return negs

    def extract_lora_from_prompt(self, prompt):
        """
        プロンプトからLoRA情報抽出
        """
        if not prompt:
            return []
        pattern = r'<lora:([^:>]+):([0-9.]+)>'
        matches = re.findall(pattern, prompt)
        return [(name, strength) for name,strength in matches]
