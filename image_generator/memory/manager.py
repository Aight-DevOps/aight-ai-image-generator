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

class MemoryManager:
    """ウルトラメモリ管理システムクラス"""

    def __init__(self, config):
        """
        Args:
            config: 設定 dict
        """
        self.logger = ColorLogger()
        mem_cfg = config.get('memory_management', {})
        self.enabled = mem_cfg.get('enabled', True)
        self.threshold = mem_cfg.get('threshold_percent', 70)
        self.auto_adjust = mem_cfg.get('auto_adjustment_enabled', True)
        self.cleanup_interval = mem_cfg.get('cleanup_interval', 1)

        # ウルトラセーフ設定
        self.aggressive = True
        self.preemptive = True
        self.ultra_safe = True
        self.max_retries = mem_cfg.get('max_retries', 5)
        self.recovery_delay = mem_cfg.get('memory_recovery_delay', 10)

        # フォールバック解像度
        self.fallbacks = config.get('fallback_resolutions', [])
        self.level = -1
        # 保存用オリジナル解像度
        self.original = {
            'width': config.get('sdxl_generation', {}).get('width'),
            'height': config.get('sdxl_generation', {}).get('height')
        }

    def check_memory_usage(self, force_cleanup=False) -> bool:
        """VRAM 使用量監視"""
        if not torch.cuda.is_available() or not self.enabled:
            return True

        try:
            allocated = torch.cuda.memory_allocated() / 1024**3
            total = torch.cuda.get_device_properties(0).total_memory / 1024**3
            percent = (allocated / total) * 100
            self.logger.print_status(f"🧠 VRAM使用量: {allocated:.2f}GB/{total:.2f}GB ({percent:.1f}%)")

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
        """積極的メモリクリーンアップ"""
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
        """段階的メモリ調整"""
        self.level += 1
        if self.level >= len(self.fallbacks):
            self.logger.print_error("❌ 最小解像度到達、これ以上調整できません")
            return False
        fb = self.fallbacks[self.level]
        torch.cuda.empty_cache()
        torch.cuda.synchronize()
        # ここで config に適用する想定
        self.logger.print_warning(f"📉 フォールバック解像度適用: {fb['width']}x{fb['height']}")
        return True

    def execute_with_ultra_memory_safety(self, func, operation_name, max_retries=None):
        """
        メモリセーフ実行ラッパー
        Args:
            func: 実行関数
            operation_name: 表示用名前
        """
        if max_retries is None:
            max_retries = self.max_retries

        for attempt in range(max_retries):
            try:
                if self.ultra_safe:
                    self.logger.print_status(f"🛡️ 事前安全チェック: {operation_name}")
                    self.check_memory_usage(force_cleanup=True)
                result = func()
                self.perform_aggressive_memory_cleanup()
                return result
            except RuntimeError as e:
                if "CUDA out of memory" in str(e) and attempt < max_retries - 1:
                    self.logger.print_warning(f"⚠️ メモリエラー再試行 ({attempt+1}/{max_retries})")
                    self.perform_aggressive_memory_cleanup()
                    if self.auto_adjust:
                        self.escalate_memory_adjustment()
                    time.sleep(self.recovery_delay)
                    continue
                raise
        raise HybridGenerationError(f"{operation_name}: メモリエラー最大リトライ到達")
