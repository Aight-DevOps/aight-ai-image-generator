#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
InputImagePool - 入力画像プール管理
"""

import os
import json
import secrets
from collections import Counter
from typing import List, Optional
from pathlib import Path
from datetime import datetime, timezone, timedelta

# JST タイムゾーン
JST = timezone(timedelta(hours=9))

class InputImagePool:
    """入力画像プール管理（重複回避・均等分散・毎回スキャン対応）"""
    
    def __init__(self, source_directory: str, supported_formats: List[str], history_file: Optional[str] = None):
        self.source_directory = source_directory
        self.supported_formats = supported_formats
        self.history_file = history_file
        self.rng = secrets.SystemRandom()
        self.pool = []
        self.current_index = 0
        self.usage_counter = Counter()
        
        # 毎回フルスキャン実行
        self._initialize_pool()
        
        # 履歴の読み込み（再起動時の継承）
        if self.history_file:
            self._load_history()
    
    def _initialize_pool(self):
        """画像プールの初期化（毎回フルスキャン）"""
        print("🔍 画像ディレクトリフルスキャン実行中...")
        self.pool.clear()
        
        # Path オブジェクトを安全に文字列化
        temp_pool = []
        for fmt in self.supported_formats:
            source_path = Path(self.source_directory)
            # 各形式で検索して文字列として追加
            temp_pool.extend([str(p) for p in source_path.rglob(f"*.{fmt}")])
            temp_pool.extend([str(p) for p in source_path.rglob(f"*.{fmt.lower()}")])
            temp_pool.extend([str(p) for p in source_path.rglob(f"*.{fmt.upper()}")])
        
        # 重複除去（文字列同士なのでset()が安全に使える）
        self.pool = list(set(temp_pool))
        
        # 毎回シャッフル
        self.rng.shuffle(self.pool)
        self.current_index = 0
        
        print(f"✅ フルスキャン完了: {len(self.pool)}枚の画像を検出")
    
    def _load_history(self):
        """履歴ファイルの読み込み（簡素化版）"""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # 使用回数のみ復元（インデックスは毎回リセット）
                self.usage_counter = Counter(data.get('usage_counter', {}))
                print(f"📂 履歴読み込み完了: 使用回数={sum(self.usage_counter.values())}")
        except Exception as e:
            print(f"⚠️ 履歴読み込みエラー: {e}")
    
    def _save_history(self):
        """履歴ファイルの保存（簡素化版）"""
        if not self.history_file:
            return
        try:
            data = {
                'usage_counter': dict(self.usage_counter),
                'total_images': len(self.pool),
                'saved_at': datetime.now(JST).isoformat()
            }
            os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ 履歴保存エラー: {e}")
    
    def get_next_image(self) -> str:
        """次の画像を取得（完全重複回避・毎回スキャン対応）"""
        if not self.pool:
            raise FileNotFoundError(f"画像ファイルが見つかりません: {self.source_directory}")
        
        # プール末尾に達したら再シャッフル
        if self.current_index >= len(self.pool):
            self.rng.shuffle(self.pool)
            self.current_index = 0
            print("🔄 画像プール完全消化: 再シャッフルして新サイクル開始")
        
        selected_image = self.pool[self.current_index]
        self.current_index += 1
        self.usage_counter[selected_image] += 1
        
        # 履歴保存
        self._save_history()
        
        return selected_image
    
    def get_usage_stats(self) -> dict:
        """使用統計の取得（簡素化版）"""
        total_used = sum(self.usage_counter.values())
        return {
            'total_images': len(self.pool),
            'used_images': len(self.usage_counter),
            'unused_images': len(self.pool) - len(self.usage_counter),
            'total_generations': total_used,
            'current_cycle_progress': f"{self.current_index}/{len(self.pool)}",
            'most_used': dict(self.usage_counter.most_common(5))
        }