#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
BatchProcessor - バッチ処理管理（完全版）
"""

import time
from common.logger import ColorLogger

class BatchProcessor:
    """バッチ処理管理クラス（完全版）"""
    
    def __init__(self, logger):
        self.logger = logger
    
    def process_with_delay(self, items, processor_func, delay=1):
        """遅延付きバッチ処理"""
        results = []
        
        for i, item in enumerate(items, 1):
            self.logger.print_status(f"--- {i}/{len(items)} ---")
            
            result = processor_func(item)
            results.append(result)
            
            # API制限対策：処理間隔
            if i < len(items):
                time.sleep(delay)
        
        return results
