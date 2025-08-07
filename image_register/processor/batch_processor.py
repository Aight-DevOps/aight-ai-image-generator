#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
BatchProcessor - バッチ処理機能
- process_batch: 単一バッチ処理
"""

class BatchProcessor:
    """バッチ処理ヘルパークラス"""

    def __init__(self, register):
        self.register = register

    def run(self, genre):
        """指定ジャンルバッチ実行"""
        return self.register.process_batch(genre)
