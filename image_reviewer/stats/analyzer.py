#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
StatsAnalyzer - 統計情報取得・分析
- get_statistics: 総数, ステータス別, モード別, ジャンル別, TTL設定数
"""

from datetime import datetime, timedelta
from common.logger import ColorLogger

class StatsAnalyzer:
    """統計情報取得・分析クラス"""

    def __init__(self, dynamodb_table, logger):
        """
        Args:
            dynamodb_table: boto3 DynamoDB Table
            logger: ColorLogger
        """
        self.table = dynamodb_table
        self.logger = logger

    def get_statistics(self, days_back=7):
        """
        統計情報取得
        Returns:
            {
                'total_count': int,
                'status_counts': {status: count},
                'highres_mode_counts': {mode: count},
                'genre_counts': {genre: count},
                'ttl_items_count': int,
                'period_days': days_back
            }
        """
        try:
            self.logger.print_status("統計情報取得中...")
            resp = self.table.scan(Limit=500)
            items = resp.get('Items', [])

            total = len(items)
            status_counts = {}
            mode_counts = {}
            genre_counts = {}
            ttl_count = 0

            for item in items:
                # ステータス
                st = item.get('imageState') or item.get('status') or 'unknown'
                status_counts[st] = status_counts.get(st, 0) + 1

                # モード
                mode = item.get('highres_mode') or item.get('HIGHRES_MODE') or 'unknown'
                mode_counts[mode] = mode_counts.get(mode, 0) + 1

                # ジャンル
                gr = item.get('genre') or 'unknown'
                genre_counts[gr] = genre_counts.get(gr, 0) + 1

                # TTL
                if 'TTL' in item:
                    ttl_count += 1

            self.logger.print_success("✅ 統計取得完了")
            return {
                'total_count': total,
                'status_counts': status_counts,
                'highres_mode_counts': mode_counts,
                'genre_counts': genre_counts,
                'ttl_items_count': ttl_count,
                'period_days': days_back
            }
        except Exception as e:
            self.logger.print_error(f"❌ 統計取得エラー: {e}")
            return None
