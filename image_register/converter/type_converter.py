#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TypeConverter - DynamoDB 対応型変換
- convert_for_dynamodb: float→Decimal
"""

from decimal import Decimal
from common.logger import ColorLogger

class TypeConverter:
    """型変換クラス"""

    def __init__(self, logger):
        self.logger = logger

    def convert_for_dynamodb(self, item):
        """ネスト dict/list の float → Decimal 変換"""
        if isinstance(item, dict):
            return {k: self.convert_for_dynamodb(v) for k,v in item.items()}
        if isinstance(item, list):
            return [self.convert_for_dynamodb(v) for v in item]
        if isinstance(item, float):
            return Decimal(str(item))
        return item
