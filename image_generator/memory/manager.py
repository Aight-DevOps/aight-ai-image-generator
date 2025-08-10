#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MemoryManager - ウルトラメモリ管理システム
- check_memory_usage: VRAM 使用量監視
- perform_aggressive_memory_cleanup: 積極的メモリクリーンアップ
- escalate_memory_adjustment: 段階的メモリ調整
- execute_with_ultra_memory_safety: メモリセーフ実行
"""

import time
import gc
import torch
from common.logger import ColorLogger
from common.types import HybridGenerationError

class MemoryManager:
    """ウルトラメモリ管理システムクラス"""

    def __init__(self, config: dict):
        self.logger = ColorLogger()
        mem_cfg = config.get('memory_management', {})
        self.enabled = mem_cfg.get('enabled', True)
        self.threshold = mem_cfg.get('threshold_percent', 70)
        self.auto_adjust = mem_cfg.get('auto_adjustment_enabled', True)
        self.cleanup_interval = mem_cfg.get('cleanup_interval', 1)

        # 強化設定
        self.aggressive_cleanup = True
        self.preemptive_adjustment = True
        self.ultra_safe_mode = True
        self.max_retries = mem_cfg.get('max_memory_retries', 5)
        self.recovery_delay = mem_cfg.get('memory_recovery_delay', 10)

        # フォールバック解像度リスト
        self.fallback_resolutions = config.get('fallback_resolutions', [])
        self.current_level = -1
        # オリジナル解像度保存
        self.original = {
            'width': config.get('sdxl_generation', {}).get('width'),
            'height': config.get('sdxl_generation', {}).get('height')
        }

    def check_memory_usage(self, force_cleanup=False) -> bool:
        """VRAM 使用量の監視と閾値超過時対応"""
        if not torch.cuda.is_available() or not self.enabled:
            return True
        try:
            alloc = torch.cuda.memory_allocated() / 1024**3
            total = torch.cuda.get_device_properties(0).total_memory / 1024**3
            percent = (alloc/total)*100
            self.logger.print_status(f"🧠 VRAM使用: {alloc:.2f}GB/{total:.2f}GB ({percent:.1f}%)")
            if force_cleanup or percent > self.threshold:
                if force_cleanup:
                    self.perform_aggressive_memory_cleanup()
                else:
                    self.logger.print_warning(f"⚠️ VRAM {self.threshold}% 超過: {percent:.1f}%")
                    self.perform_aggressive_memory_cleanup()
                    if self.auto_adjust:
                        self.escalate_memory_adjustment()
                return False
            return True
        except Exception as e:
            self.logger.print_error(f"❌ メモリ監視エラー: {e}")
            return True

    def perform_aggressive_memory_cleanup(self):
        """積極的なメモリクリーンアップ"""
        try:
            self.logger.print_status("🧹 積極的メモリクリーンアップ開始")
            if torch.cuda.is_available():
                for _ in range(3):
                    torch.cuda.empty_cache()
                    torch.cuda.synchronize()
                    time.sleep(1)
            for _ in range(3):
                gc.collect()
                time.sleep(0.5)
            time.sleep(self.recovery_delay)
            self.logger.print_success("✅ メモリクリーンアップ完了")
        except Exception as e:
            self.logger.print_error(f"❌ メモリクリーンアップエラー: {e}")

    def escalate_memory_adjustment(self) -> bool:
        """段階的メモリ調整（フォールバック解像度切り替え）"""
        self.current_level += 1
        if self.current_level >= len(self.fallback_resolutions):
            self.logger.print_error("❌ フォールバック解像度上限に到達")
            return False
        fb = self.fallback_resolutions[self.current_level]
        torch.cuda.empty_cache()
        torch.cuda.synchronize()
        # 設定反映は外部で対応
        self.logger.print_warning(f"📉 解像度フォールバック適用: {fb['width']}x{fb['height']}")
        return True

    def execute_with_ultra_memory_safety(self, func, name: str, max_retries: int=None):
        """
        ウルトラセーフティ付き実行
        Args:
            func: 実行関数
            name: 処理名
        """
        if max_retries is None:
            max_retries = self.max_retries
        for attempt in range(max_retries):
            try:
                if self.ultra_safe_mode:
                    self.logger.print_status(f"🛡️ 事前メモリチェック: {name}")
                    self.check_memory_usage(force_cleanup=True)
                result = func()
                self.perform_aggressive_memory_cleanup()
                return result
            except RuntimeError as e:
                if "CUDA out of memory" in str(e) and attempt < max_retries-1:
                    self.logger.print_warning(f"⚠️ {name} 再試行 ({attempt+1}/{max_retries})")
                    self.perform_aggressive_memory_cleanup()
                    if self.auto_adjust:
                        self.escalate_memory_adjustment()
                    time.sleep(self.recovery_delay)
                    continue
                raise HybridGenerationError(f"{name} メモリ不足: {e}")
        raise HybridGenerationError(f"{name} 最大リトライ回数到達")
