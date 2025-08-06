#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Process Timer - 処理時間計測クラス
"""

import time
from .logger import ColorLogger

class ProcessTimer:
    """処理時間計測クラス"""

    def __init__(self, logger=None):
        """
        タイマー初期化
        
        Args:
            logger: ロガーインスタンス（Noneの場合は新規作成）
        """
        self.logger = logger if logger else ColorLogger()
        self.start_time = None
        self.phase_times = {}
        self.process_name = "処理"

    def start(self, process_name="処理"):
        """
        時間計測開始
        
        Args:
            process_name: 処理名
        """
        self.start_time = time.time()
        self.process_name = process_name

    def mark_phase(self, phase_name):
        """
        フェーズマーク
        
        Args:
            phase_name: フェーズ名
        """
        if self.start_time:
            elapsed = time.time() - self.start_time
            self.phase_times[phase_name] = elapsed

    def end_and_report(self, success_count=None):
        """
        時間計測終了と結果表示
        
        Args:
            success_count: 成功数（複数処理の場合）
            
        Returns:
            float: 総処理時間（秒）
        """
        if not self.start_time:
            return 0.0

        total_time = time.time() - self.start_time
        formatted_time = self.format_duration(total_time)

        self.logger.print_timing(f"⏱️ {self.process_name}完了時間: {formatted_time}")

        # フェーズ別時間表示
        if self.phase_times:
            for phase, duration in self.phase_times.items():
                phase_formatted = self.format_duration(duration)
                self.logger.print_timing(f" └─ {phase}: {phase_formatted}")

        # 平均時間表示（複数画像の場合）
        if success_count and success_count > 1:
            avg_time = total_time / success_count
            avg_formatted = self.format_duration(avg_time)
            self.logger.print_timing(f"📊 1枚あたり平均時間: {avg_formatted}")

        return total_time

    @staticmethod
    def format_duration(seconds):
        """
        秒数を「○時間○分○秒」形式にフォーマット
        
        Args:
            seconds: 秒数
            
        Returns:
            str: フォーマットされた時間文字列
        """
        if seconds < 60:
            return f"{seconds:.1f}秒"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = seconds % 60
            return f"{minutes}分{secs:.1f}秒"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = seconds % 60
            return f"{hours}時間{minutes}分{secs:.1f}秒"
