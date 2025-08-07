#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
BatchProcessor - バッチ処理機能統合
- generate_hybrid_image: 単発生成
- generate_hybrid_batch: ジャンル別バッチ生成
- generate_daily_hybrid_batch: 日次バッチ生成
"""

import time
from common.logger import ColorLogger
from common.timer import ProcessTimer

class BatchProcessor:
    """画像生成バッチ処理クラス"""

    def __init__(self, generator, config, logger=None):
        """
        Args:
            generator: HybridBijoImageGeneratorV7 インスタンス
            config: 設定 dict
        """
        self.generator = generator
        self.config = config
        self.logger = logger or ColorLogger()

    def generate_hybrid_image(self, gen_type, count=1):
        """
        単発画像生成
        """
        overall = ProcessTimer(self.logger)
        overall.start(f"SDXL統合画像生成バッチ（{count}枚）")

        try:
            self.generator.ensure_model_for_generation_type(gen_type)
        except Exception as e:
            self.logger.print_error(f"モデル切り替え失敗: {e}")
            return 0

        success = 0
        for i in range(count):
            img_timer = ProcessTimer(self.logger)
            img_timer.start(f"画像{i+1}/{count}")
            self.logger.print_stage(f"=== {gen_type.name} 生成開始 ({i+1}/{count}) ===")
            try:
                if self.generator.pose_mode is None:
                    self.generator.select_pose_mode()

                # 画像生成
                path, response = self.generator.generate_hybrid_single(gen_type)
                success += 1
                img_timer.end_and_report()
            except Exception as e:
                self.logger.print_error(f"生成エラー (試行{i+1}): {e}")
                break

        total = overall.end_and_report(success)
        self.logger.print_stage(f"=== {gen_type.name} 生成完了 成功数: {success}/{count} ===")
        return success

    def generate_hybrid_batch(self, genre, count=1):
        """
        ジャンル別バッチ生成
        """
        # 生成タイプ取得
        gen_type = None
        for gt in self.generator.generation_types:
            if gt.name == genre:
                gen_type = gt
                break
        if not gen_type:
            self.logger.print_error(f"ジャンル '{genre}' が見つかりません")
            return 0

        return self.generate_hybrid_image(gen_type, count)

    def generate_daily_hybrid_batch(self):
        """
        日次バッチ生成
        """
        if self.generator.local_mode:
            self.logger.print_warning("ローカルモードでは日次バッチ非推奨")
            confirm = input("続行しますか？ (y/N): ").strip().lower()
            if confirm != 'y':
                self.logger.print_status("キャンセル")
                return

        overall = ProcessTimer(self.logger)
        overall.start("1日分SDXL統合画像生成")

        batch_size = self.config['generation']['batch_size']
        genres = self.config['generation']['genres']

        # ジャンルごと分散
        for idx, genre in enumerate(genres):
            ratio = self.config['generation'].get('genre_distribution', {}).get(genre, 1.0/len(genres))
            num = max(1, int(batch_size * ratio))
            if idx == 0:
                num += batch_size - sum(int(batch_size * self.config['generation'].get('genre_distribution', {}).get(g, 1.0/len(genres))) for g in genres)

            self.logger.print_status(f"{genre}: {num} 枚生成予定")
            self.generate_hybrid_batch(genre, num)

            if idx < len(genres)-1 and self.generator.memory_manager.enabled:
                self.logger.print_status("ジャンル間メモリクリーンアップ")
                self.generator.memory_manager.perform_aggressive_memory_cleanup()
                time.sleep(60)

        overall.end_and_report()
        self.logger.print_stage("=== 日次バッチ生成完了 ===")
