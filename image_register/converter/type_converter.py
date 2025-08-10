#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TypeConverter - DynamoDB型変換（完全版）
Float型をDecimal型に変換してDynamoDB互換性を確保
"""

from decimal import Decimal
from common.logger import ColorLogger

class TypeConverter:
    """型変換クラス（完全版）"""

    def __init__(self, logger):
        self.logger = logger

    def convert_for_dynamodb(self, data):
        """DynamoDB用の型変換（Decimal型対応）"""
        return self._safe_convert_numeric(data)

    def _safe_convert_numeric(self, value):
        """数値を安全にDynamoDB対応型に変換"""
        if isinstance(value, float):
            return Decimal(str(value))
        elif isinstance(value, dict):
            return {k: self._safe_convert_numeric(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._safe_convert_numeric(item) for item in value]
        return value

    def convert_for_json(self, value):
        """JSON送信用に安全に変換"""
        if isinstance(value, Decimal):
            return float(value)
        elif isinstance(value, dict):
            return {k: self.convert_for_json(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self.convert_for_json(item) for item in value]
        return value
