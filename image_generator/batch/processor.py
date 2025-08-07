#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
BatchProcessor - 画像生成バッチ処理
- generate_hybrid_image: 単体生成
- generate_hybrid_batch: 指定ジャンルバッチ生成
- generate_daily_hybrid_batch: 日次バッチ生成
"""

import time
from common.logger import ColorLogger
from common.timer import ProcessTimer
from common.types import HybridGenerationError

class BatchProcessor:
    """バッチ処理管理クラス"""

    def __init__(self, generator, config: dict, logger=None):
        """
        Args:
            generator: HybridBijoImageGeneratorV7 インスタンス
            config: 設定 dict
        """
        self.generator = generator
        self.config = config
        self.logger = logger or ColorLogger()

    def generate_hybrid_image(self, gen_type, count=1) -> int:
        """
        単体または複数画像生成（モデル切替含む）
        Returns 成功数
        """
        overall = ProcessTimer(self.logger)
        overall.start(f"SDXL統合画像生成バッチ（{count}枚）")

        # モデル切替
        try:
            from ..core.model_manager import ModelManager
            ModelManager(self.config).ensure_model_for_generation_type(gen_type)
        except HybridGenerationError as e:
            self.logger.print_error(f"❌ モデル切替失敗: {e}")
            return 0

        success = 0
        for i in range(count):
            img_timer = ProcessTimer(self.logger)
            img_timer.start(f"画像{i+1}/{count}")
            self.logger.print_stage(f"=== {gen_type.name} 生成開始 ({i+1}/{count}) ===")
            try:
                path, resp = self.generator._generate_single(gen_type, i)
                success += 1
                img_timer.end_and_report(1)
            except Exception as e:
                self.logger.print_error(f"❌ 生成エラー ({i+1}): {e}")
                break

        overall.end_and_report(success)
        self.logger.print_stage(f"=== 完了: {success}/{count}枚 ===")
        return success

    def generate_hybrid_batch(self, genre: str, count: int=1) -> int:
        """
        ジャンル別バッチ生成
        """
        # 生成タイプ取得
        gen_type = next((gt for gt in self.generator.generation_types if gt.name==genre), None)
        if not gen_type:
            self.logger.print_error(f"❌ ジャンル '{genre}' が見つかりません")
            return 0
        return self.generate_hybrid_image(gen_type, count)

    def generate_daily_hybrid_batch(self):
        """
        日次バッチ生成
        """
        if self.generator.local_mode:
            self.logger.print_warning("⚠️ ローカルモードでは日次バッチ非推奨")
            if input("続行しますか？ (y/N): ").lower()!='y':
                self.logger.print_status("キャンセル")
                return

        overall = ProcessTimer(self.logger)
        overall.start("1日分SDXL統合画像生成バッチ")

        batch_size = self.config['generation']['batch_size']
        genres = self.config['generation']['genres']
        dist = self.config['generation'].get('genre_distribution', {})

        for idx, genre in enumerate(genres):
            ratio = dist.get(genre, 1.0/len(genres))
            num = max(1, int(batch_size*ratio))
            if idx==0:
                allocated = sum(int(batch_size*dist.get(g,1.0/len(genres))) for g in genres)
                num += batch_size - allocated

            self.logger.print_status(f"{genre}: {num} 枚生成予定")
            self.generate_hybrid_batch(genre, num)

            if idx < len(genres)-1 and self.generator.memory_manager.enabled:
                self.logger.print_status("🧹 ジャンル間メモリクリーンアップ")
                self.generator.memory_manager.perform_aggressive_memory_cleanup()
                time.sleep(60)

        overall.end_and_report()
        self.logger.print_stage("=== 日次バッチ生成完了 ===")
