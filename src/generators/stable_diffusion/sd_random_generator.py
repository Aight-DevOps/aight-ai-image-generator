#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stable Diffusion Random Element Generator - SD専用
"""

import os
import json
import secrets
from pathlib import Path
from collections import deque, Counter
from typing import List, Any, Dict

class EnhancedSecureRandom:
    def __init__(self):
        self.rng = secrets.SystemRandom()
        self.histories: Dict[str, deque] = {}
        self.counters: Dict[str, Counter] = {}

    @staticmethod
    def _to_hashable(item: Any) -> Any:
        try:
            hash(item)
            return item
        except TypeError:
            return json.dumps(item, ensure_ascii=False, sort_keys=True)

    def choice_no_repeat(self, seq: List[Any], category: str, window: int = 3) -> Any:
        if category not in self.histories:
            self.histories[category] = deque(maxlen=window)
            self.counters[category] = Counter()
        history = self.histories[category]
        cand = [x for x in seq if self._to_hashable(x) not in history]
        if not cand:
            history.clear()
            cand = seq
        if len(cand) > 1:
            min_cnt = min(self.counters[category].get(self._to_hashable(x), 0) for x in cand)
            weights = [max(1, min_cnt + 1 - self.counters[category].get(self._to_hashable(x), 0)) for x in cand]
            sel = self.rng.choices(cand, weights=weights, k=1)[0]
        else:
            sel = cand[0]
        history.append(self._to_hashable(sel))
        self.counters[category][self._to_hashable(sel)] += 1
        return sel

    def get_usage_stats(self) -> Dict[str,int]:
        return {cat: dict(cnt) for cat, cnt in self.counters.items()}


class RandomElementGenerator:
    """ランダム要素生成"""

    def __init__(self, specific: Dict[str, List[Any]], general: Dict[str, List[Any]], history_file: str = None):
        self.specific = specific
        self.general = general
        self.history_file = history_file
        self.enh = EnhancedSecureRandom()
        if history_file and os.path.exists(history_file):
            self._load_history()

    def _load_history(self):
        with open(self.history_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        for cat, hist in data.get("histories", {}).items():
            dq = deque(hist, maxlen=len(hist))
            self.enh.histories[cat] = dq
        for cat, cnt in data.get("counters", {}).items():
            self.enh.counters[cat] = Counter(cnt)

    def _save_history(self):
        if not self.history_file:
            return
        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump({
                "histories": {k:list(v) for k,v in self.enh.histories.items()},
                "counters": {k:dict(v) for k,v in self.enh.counters.items()}
            }, f, ensure_ascii=False, indent=2)

    def generate_elements(self, gen_type: Any) -> str:
        prompt = ""
        for elem in getattr(gen_type, "random_elements", []):
            opts = self.specific.get(elem, [])
            if not opts:
                continue
            sel = self.enh.choice_no_repeat(opts, elem, window=3)
            prompt += f", {sel}"
        self._save_history()
        return prompt
        

class InputImagePool:
    """入力画像プール管理"""

    def __init__(self, source_dir: str, formats: List[str], history_file: str = None):
        self.source_dir = Path(source_dir)
        self.formats = formats
        self.history_file = history_file
        self.hist: Counter = Counter()
        self.pool: List[str] = []
        self.idx = 0
        self._scan()
        if history_file and self.history_file.exists():
            self._load()

    def _scan(self):
        self.pool = []
        for ext in self.formats:
            self.pool += [str(p) for p in self.source_dir.rglob(f"*.{ext}")]
        secrets.SystemRandom().shuffle(self.pool)

    def _load(self):
        with open(self.history_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.hist = Counter(data.get("usage_counter", {}))

    def _save(self):
        if not self.history_file:
            return
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump({"usage_counter": dict(self.hist)}, f, ensure_ascii=False, indent=2)

    def get_next_image(self) -> str:
        if not self.pool:
            raise FileNotFoundError(f"No images in {self.source_dir}")
        if self.idx >= len(self.pool):
            self.idx = 0
            secrets.SystemRandom().shuffle(self.pool)
        path = self.pool[self.idx]
        self.idx += 1
        self.hist[path] += 1
        self._save()
        return path
