#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SecureRandom - セキュアランダム機能
"""

import secrets
import json
from collections import deque, Counter
from typing import List, Any, Union, Dict, Optional

class SecureRandom:
    """暗号学的に安全なランダム関数を提供するクラス（既存互換性維持）"""
    
    @staticmethod
    def choice(sequence: List[Any]) -> Any:
        """リストから暗号学的に安全にランダム選択"""
        if not sequence:
            raise ValueError("空のシーケンスからは選択できません")
        return sequence[secrets.randbelow(len(sequence))]
    
    @staticmethod
    def randint(min_val: int, max_val: int) -> int:
        """指定範囲内で暗号学的に安全にランダムな整数を生成"""
        if min_val > max_val:
            raise ValueError("最小値が最大値より大きいです")
        return min_val + secrets.randbelow(max_val - min_val + 1)
    
    @staticmethod
    def random() -> float:
        """0.0以上1.0未満の暗号学的に安全なランダム浮動小数点数を生成"""
        return secrets.randbelow(2**32) / (2**32)
    
    @staticmethod
    def shuffle(sequence: List[Any]) -> List[Any]:
        """リストを暗号学的に安全にシャッフル（Fisher-Yatesアルゴリズム）"""
        shuffled = sequence.copy()
        for i in range(len(shuffled) - 1, 0, -1):
            j = secrets.randbelow(i + 1)
            shuffled[i], shuffled[j] = shuffled[j], shuffled[i]
        return shuffled

class EnhancedSecureRandom:
    """
    拡張セキュアランダムクラス（重複回避＆重み付き選択）
    - 非ハッシュ対象(dict, list 等)を安全にハッシュ可能なキーへ変換して履歴・カウンターに保存
    """
    
    def __init__(self):
        self.rng = secrets.SystemRandom()
        self.histories: Dict[str, deque] = {}
        self.counters: Dict[str, Counter] = {}
    
    @staticmethod
    def _to_hashable(item):
        """
        Counter / set のキーに安全に使える形へ変換する
        - 既にハッシュ可能ならそのまま
        - dict / list などは json.dumps(sort_keys=True) で安定化
        """
        try:
            hash(item)
            return item
        except TypeError:
            # dict 以外の list・set 等も文字列化で対応
            if isinstance(item, (dict, list, set)):
                return json.dumps(item, ensure_ascii=False, sort_keys=True)
            return str(item)
    
    def choice_no_repeat(self, sequence, category: str = "default", window: int = 3):
        """
        直近 window 回に出ていない要素を優先しつつランダム選択
        - 低出現回数ほど選ばれやすい重みを付与
        """
        if not sequence:
            raise ValueError("空のシーケンスからは選択できません")
        
        # カテゴリ別履歴・カウンタ初期化
        if category not in self.histories:
            self.histories[category] = deque(maxlen=window)
            self.counters[category] = Counter()
        
        history = self.histories[category]
        counter = self.counters[category]
        
        # 「履歴にないもの」を候補に
        candidates = [item for item in sequence 
                      if self._to_hashable(item) not in history]
        
        # 全て履歴にある場合は履歴クリア
        if not candidates:
            history.clear()
            candidates = sequence
        
        # 使用頻度に応じた重み計算
        if len(candidates) > 1:
            min_cnt = min(counter.get(self._to_hashable(x), 0) for x in candidates)
            weights = [
                max(1, min_cnt + 5 - counter.get(self._to_hashable(x), 0))
                for x in candidates
            ]
            selected = self.rng.choices(candidates, weights=weights, k=1)[0]
        else:
            selected = candidates[0]
        
        # 履歴・カウンターを更新（ハッシュ化キーで管理）
        key = self._to_hashable(selected)
        history.append(key)
        counter[key] += 1
        
        return selected
    
    def shuffle_pool(self, sequence):
        """ Fisher-Yates シャッフル """
        shuffled = sequence.copy()
        for i in range(len(shuffled) - 1, 0, -1):
            j = self.rng.randbelow(i + 1)
            shuffled[i], shuffled[j] = shuffled[j], shuffled[i]
        return shuffled
    
    def get_usage_stats(self, category: Optional[str] = None):
        """
        使用統計を辞書で返す
        - category 指定なしで全カテゴリ集計
        """
        if category:
            return dict(self.counters.get(category, {}))
        return {cat: dict(cnt) for cat, cnt in self.counters.items()}