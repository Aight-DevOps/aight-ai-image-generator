#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Memory Manager - メモリ管理クラス（Ultra Safe対応）
"""

import gc
import torch
import warnings
from typing import Dict, Any
from .logger import ColorLogger

class MemoryManager:
    """メモリ管理クラス（ウルトラセーフモード対応）"""

    def __init__(self, config_manager):
        """
        メモリ管理クラス初期化
        
        Args:
            config_manager: 設定管理クラスインスタンス
        """
        self.config_manager = config_manager
        self.logger = ColorLogger()
        
        # メモリ管理設定の読み込み
        self.memory_config = config_manager.get_memory_management_config()
        self.memory_monitoring_enabled = self.memory_config.get('enabled', True)
        self.memory_threshold = self.memory_config.get('threshold_percent', 70)
        self.auto_adjustment_enabled = self.memory_config.get('auto_adjustment_enabled', True)
        self.cleanup_interval = self.memory_config.get('cleanup_interval', 1)
        
        # 強化されたメモリ制御パラメータ
        self.aggressive_cleanup = self.memory_config.get('aggressive_cleanup', True)
        self.preemptive_adjustment = self.memory_config.get('preemptive_adjustment', True)
        self.ultra_safe_mode = self.memory_config.get('ultra_safe_mode', True)
        self.max_memory_retries = self.memory_config.get('max_memory_retries', 5)
        self.memory_recovery_delay = self.memory_config.get('memory_recovery_delay', 10)
        
        # 段階的フォールバック解像度設定（SDXL用に調整）
        self.fallback_resolutions = [
            {'width': 640, 'height': 832},   # 最小
            {'width': 768, 'height': 960},   # 小
            {'width': 832, 'height': 1088},  # 中
        ]
        self.current_fallback_level = -1  # -1は通常設定を意味する
        
        # デフォルト解像度設定の保存（自動調整用）
        sdxl_config = config_manager.get_sdxl_generation_config()
        self.original_config = {
            'width': sdxl_config.get('width', 896),
            'height': sdxl_config.get('height', 1152)
        }
        
        self.logger.print_status("🧠 ウルトラメモリ管理システム初期化完了")
        self.logger.print_status(f"🔍 メモリ監視: {'有効' if self.memory_monitoring_enabled else '無効'}")
        self.logger.print_status(f"⚙️ 自動調整: {'有効' if self.auto_adjustment_enabled else '無効'}")
        self.logger.print_status(f"📊 メモリ閾値: {self.memory_threshold}%")
        self.logger.print_status(f"🛡️ ウルトラセーフモード: {'有効' if self.ultra_safe_mode else '無効'}")

    def get_gpu_memory_info(self) -> Dict[str, float]:
        """
        GPU メモリ使用状況取得
        
        Returns:
            Dict[str, float]: メモリ情報
        """
        try:
            if torch.cuda.is_available():
                allocated = torch.cuda.memory_allocated() / 1024**3  # GB
                reserved = torch.cuda.memory_reserved() / 1024**3   # GB
                total = torch.cuda.get_device_properties(0).total_memory / 1024**3  # GB
                usage_percent = (allocated / total) * 100
                
                return {
                    'allocated_gb': allocated,
                    'reserved_gb': reserved,
                    'total_gb': total,
                    'usage_percent': usage_percent,
                    'free_gb': total - allocated
                }
            else:
                return {'error': 'CUDA not available'}
        except Exception as e:
            self.logger.print_warning(f"⚠️ GPU メモリ情報取得エラー: {e}")
            return {'error': str(e)}

    def monitor_memory(self) -> bool:
        """
        メモリ監視実行
        
        Returns:
            bool: メモリ使用量が閾値以下の場合True
        """
        if not self.memory_monitoring_enabled:
            return True
        
        memory_info = self.get_gpu_memory_info()
        
        if 'error' in memory_info:
            self.logger.print_warning(f"⚠️ メモリ監視スキップ: {memory_info['error']}")
            return True
        
        usage_percent = memory_info['usage_percent']
        
        # 詳細なメモリ情報表示
        self.logger.print_status(
            f"🧠 GPU メモリ: {memory_info['allocated_gb']:.1f}GB/"
            f"{memory_info['total_gb']:.1f}GB ({usage_percent:.1f}%)"
        )
        
        # 閾値チェック
        if usage_percent > self.memory_threshold:
            self.logger.print_warning(
                f"⚠️ メモリ使用量が閾値({self.memory_threshold}%)を超過: {usage_percent:.1f}%"
            )
            return False
        
        return True

    def perform_aggressive_memory_cleanup(self):
        """積極的なメモリクリーンアップ実行"""
        self.logger.print_status("🧠 積極的メモリクリーンアップ開始...")
        
        # 事前メモリ状況
        before_info = self.get_gpu_memory_info()
        
        if torch.cuda.is_available():
            try:
                # PyTorchキャッシュクリア
                torch.cuda.empty_cache()
                
                # 強制ガベージコレクション（複数回実行）
                for i in range(3):
                    collected = gc.collect()
                    if collected > 0:
                        self.logger.print_status(f"🗑️ ガベージコレクション {i+1}: {collected}個回収")
                
                # さらに強力なCUDAキャッシュクリア
                if hasattr(torch.cuda, 'synchronize'):
                    torch.cuda.synchronize()
                
                # 警告抑制
                warnings.filterwarnings('ignore', category=UserWarning)
                
                # 事後メモリ状況
                after_info = self.get_gpu_memory_info()
                
                if 'error' not in before_info and 'error' not in after_info:
                    freed_gb = before_info['allocated_gb'] - after_info['allocated_gb']
                    self.logger.print_success(
                        f"✅ メモリクリーンアップ完了: {freed_gb:.2f}GB解放 "
                        f"({before_info['usage_percent']:.1f}% → {after_info['usage_percent']:.1f}%)"
                    )
                else:
                    self.logger.print_success("✅ メモリクリーンアップ完了")
                
            except Exception as e:
                self.logger.print_error(f"❌ メモリクリーンアップエラー: {e}")
        else:
            # CUDA非対応環境でもガベージコレクションは実行
            collected = gc.collect()
            self.logger.print_success(f"✅ ガベージコレクション完了: {collected}個回収")

    def escalate_memory_adjustment(self) -> bool:
        """
        段階的メモリ設定調整
        
        Returns:
            bool: 調整が実行された場合True
        """
        if not self.auto_adjustment_enabled:
            return False
        
        # フォールバック段階を上げる
        if self.current_fallback_level < len(self.fallback_resolutions) - 1:
            self.current_fallback_level += 1
            fallback_config = self.fallback_resolutions[self.current_fallback_level]
            
            self.logger.print_warning(
                f"📉 メモリ調整レベル {self.current_fallback_level + 1}: "
                f"解像度を{fallback_config['width']}x{fallback_config['height']}に調整"
            )
            
            # 設定に反映（実際の設定変更は呼び出し元で実行）
            return True
        else:
            self.logger.print_error("❌ 最大メモリ調整レベルに到達しました")
            return False

    def get_current_resolution_config(self) -> Dict[str, int]:
        """
        現在の解像度設定を取得
        
        Returns:
            Dict[str, int]: 解像度設定
        """
        if self.current_fallback_level >= 0:
            return self.fallback_resolutions[self.current_fallback_level]
        else:
            return self.original_config

    def reset_memory_adjustments(self):
        """メモリ調整をリセット"""
        if self.current_fallback_level >= 0:
            self.current_fallback_level = -1
            self.logger.print_success("✅ メモリ調整を原設定にリセットしました")

    def is_memory_safe(self) -> bool:
        """
        メモリ安全性チェック
        
        Returns:
            bool: メモリが安全な状態の場合True
        """
        if not self.memory_monitoring_enabled:
            return True
        
        memory_info = self.get_gpu_memory_info()
        if 'error' in memory_info:
            return True  # エラー時は安全とみなす
        
        return memory_info['usage_percent'] <= self.memory_threshold

    def prepare_for_generation(self) -> bool:
        """
        生成前のメモリ準備
        
        Returns:
            bool: 準備が完了した場合True
        """
        if not self.ultra_safe_mode:
            return True
        
        self.logger.print_status("🛡️ ウルトラセーフモード: 生成前メモリ準備開始")
        
        # 事前クリーンアップ
        self.perform_aggressive_memory_cleanup()
        
        # メモリ監視
        if not self.monitor_memory():
            self.logger.print_warning("⚠️ メモリ使用量が高い状態で生成を開始します")
        
        return True

    def cleanup_after_generation(self):
        """生成後のメモリクリーンアップ"""
        if self.ultra_safe_mode:
            self.logger.print_status("🛡️ ウルトラセーフモード: 生成後メモリクリーンアップ")
            self.perform_aggressive_memory_cleanup()

    def get_memory_stats(self) -> Dict[str, Any]:
        """
        メモリ統計情報取得
        
        Returns:
            Dict[str, Any]: メモリ統計
        """
        memory_info = self.get_gpu_memory_info()
        current_resolution = self.get_current_resolution_config()
        
        return {
            'memory_info': memory_info,
            'current_resolution': current_resolution,
            'fallback_level': self.current_fallback_level,
            'monitoring_enabled': self.memory_monitoring_enabled,
            'ultra_safe_mode': self.ultra_safe_mode,
            'auto_adjustment_enabled': self.auto_adjustment_enabled,
            'threshold_percent': self.memory_threshold
        }
