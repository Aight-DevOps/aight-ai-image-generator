#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RandomElementGenerator - ランダム要素生成
"""

import os
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from .secure_random import EnhancedSecureRandom

# JST タイムゾーン
JST = timezone(timedelta(hours=9))

class RandomElementGenerator:
    """ランダム要素生成（バリエーション重視・永続化対応）"""
    
    def __init__(self, specific_elements: Dict[str, Any], general_elements: Dict[str, Any], history_file: Optional[str] = None):
        self.specific_elements = specific_elements
        self.general_elements = general_elements
        self.history_file = history_file
        self.enhanced_random = EnhancedSecureRandom()
        
        # 履歴の読み込み（再起動時の継承）
        if self.history_file:
            self._load_history()
    
    def _load_history(self):
        """履歴ファイルの読み込み"""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 履歴データの復元
                for category, history_list in data.get('histories', {}).items():
                    if category not in self.enhanced_random.histories:
                        from collections import deque
                        self.enhanced_random.histories[category] = deque(maxlen=5)
                    self.enhanced_random.histories[category].extend(history_list)
                
                # カウンターデータの復元
                for category, counter_dict in data.get('counters', {}).items():
                    if category not in self.enhanced_random.counters:
                        from collections import Counter
                        self.enhanced_random.counters[category] = Counter()
                    self.enhanced_random.counters[category].update(counter_dict)
                
                print(f"📂 要素履歴読み込み完了: {len(data.get('histories', {}))}カテゴリ")
        except Exception as e:
            print(f"⚠️ 要素履歴読み込みエラー: {e}")
    
    def _save_history(self):
        """履歴ファイルの保存"""
        if not self.history_file:
            return
        try:
            data = {
                'histories': {cat: list(hist) for cat, hist in self.enhanced_random.histories.items()},
                'counters': {cat: dict(counter) for cat, counter in self.enhanced_random.counters.items()},
                'saved_at': datetime.now(JST).isoformat()
            }
            os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ 要素履歴保存エラー: {e}")
    
    def generate_elements(self, gen_type, max_general: int = 3) -> str:
        """改良版ランダム要素生成（永続化対応・ポーズ検出モード対応）"""
        additional_prompt = ""
        
        # 特定ランダム要素（重複回避・履歴継承）
        for element_type in gen_type.random_elements:
            if element_type not in self.specific_elements:
                continue
            
            elements_options = self.specific_elements[element_type]
            if not elements_options:
                continue
            
            # ポーズカテゴリは常にスキップ（重複回避のため修正）
            if element_type == "poses":
                continue
            
            # ヘアスタイル専用処理（既存のまま維持）
            if element_type == "hairstyles":
                if isinstance(elements_options, list):
                    entry = self.enhanced_random.choice_no_repeat(
                        elements_options, "hairstyles", window=4
                    )
                    if isinstance(entry, dict) and "length" in entry and "style" in entry:
                        length = entry["length"]
                        style_val = entry["style"]
                        if isinstance(style_val, list):
                            style_choice = self.enhanced_random.choice_no_repeat(
                                style_val, "hairstyles_style", window=3
                            )
                            additional_prompt += f", {length}, {style_choice}"
                        else:
                            additional_prompt += f", {length}, {style_val}"
                    elif isinstance(entry, str):
                        additional_prompt += f", {entry}"
                
                continue  # hairstyles はここで終了
            
            # その他 specific_elements 共通処理（background, Sexual_expressions, breast_size含む）
            if isinstance(elements_options, list):
                safe_opts = []
                for opt in elements_options:
                    if isinstance(opt, dict):
                        safe_opts.append(
                            str(opt.get("text") or opt.get("value") or ", ".join(map(str, opt.values())))
                        )
                    else:
                        safe_opts.append(str(opt))
                
                if safe_opts:
                    sel = self.enhanced_random.choice_no_repeat(
                        safe_opts, element_type, window=5
                    )
                    additional_prompt += f", {sel}"
        
        # 履歴保存
        self._save_history()
        
        return additional_prompt
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """使用統計の取得"""
        return self.enhanced_random.get_usage_stats()