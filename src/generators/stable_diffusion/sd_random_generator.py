#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stable Diffusion Random Element Generator - ランダム要素生成（SD専用）
DynamoDB Float型→Decimal型変換対応版
"""

import json
import os
import secrets
from collections import deque, Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Any, Dict
from decimal import Decimal
from ...utils.logger import ColorLogger

# JST タイムゾーン
JST = timezone(timedelta(hours=9))

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
    - DynamoDB対応: Float型→Decimal型自動変換機能付き
    """

    def __init__(self):
        self.rng = secrets.SystemRandom()
        self.histories: dict[str, deque] = {}
        self.counters: dict[str, Counter] = {}

    # ---------- 内部ユーティリティ ---------- #

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

    @staticmethod
    def safe_convert_for_dynamodb(value):
        """
        DynamoDB保存用にFloat型をDecimal型に安全に変換
        
        Args:
            value: 変換対象の値
            
        Returns:
            変換後の値（Float→Decimal、その他は元の値）
        """
        if isinstance(value, float):
            return Decimal(str(value))
        elif isinstance(value, dict):
            return {k: EnhancedSecureRandom.safe_convert_for_dynamodb(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [EnhancedSecureRandom.safe_convert_for_dynamodb(item) for item in value]
        return value

    # ---------- 公開メソッド ---------- #

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

    def get_usage_stats(self, category: str | None = None):
        """
        使用統計を辞書で返す（DynamoDB対応版）
        - category 指定なしで全カテゴリ集計
        - Float値は自動的にDecimal型に変換
        """
        if category:
            stats = dict(self.counters.get(category, {}))
            return self.safe_convert_for_dynamodb(stats)
        
        all_stats = {cat: dict(cnt) for cat, cnt in self.counters.items()}
        return self.safe_convert_for_dynamodb(all_stats)

class InputImagePool:
    """入力画像プール管理（重複回避・均等分散・毎回スキャン対応・DynamoDB対応）"""

    def __init__(self, source_directory: str, supported_formats: List[str], history_file: str = None):
        self.source_directory = source_directory
        self.supported_formats = supported_formats
        self.history_file = history_file
        self.rng = secrets.SystemRandom()
        self.pool = []
        self.current_index = 0
        self.usage_counter = Counter()
        self.logger = ColorLogger()

        # 毎回フルスキャン実行
        self._initialize_pool()

        # 履歴の読み込み（再起動時の継承）
        if self.history_file:
            self._load_history()

    def _initialize_pool(self):
        """画像プールの初期化（毎回フルスキャン）"""
        self.logger.print_status("🔍 画像ディレクトリフルスキャン実行中...")
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

        self.logger.print_success(f"✅ フルスキャン完了: {len(self.pool)}枚の画像を検出")

    def _load_history(self):
        """履歴ファイルの読み込み（簡素化版）"""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # 使用回数のみ復元（インデックスは毎回リセット）
                self.usage_counter = Counter(data.get('usage_counter', {}))
                self.logger.print_status(f"📂 履歴読み込み完了: 使用回数={sum(self.usage_counter.values())}")
        except Exception as e:
            self.logger.print_warning(f"⚠️ 履歴読み込みエラー: {e}")

    def _save_history(self):
        """履歴ファイルの保存（簡素化版・DynamoDB対応）"""
        if not self.history_file:
            return

        try:
            # DynamoDB対応: Float値をDecimal型に変換してから保存
            data = {
                'usage_counter': dict(self.usage_counter),
                'total_images': len(self.pool),
                'saved_at': datetime.now(JST).isoformat()
            }
            
            # Float→Decimal変換を適用
            data = EnhancedSecureRandom.safe_convert_for_dynamodb(data)

            os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
            with open(self.history_file, 'w', encoding='utf-8') as f:
                # Decimal型をJSONに保存する際は文字列化
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        except Exception as e:
            self.logger.print_warning(f"⚠️ 履歴保存エラー: {e}")

    def get_next_image(self) -> str:
        """次の画像を取得（完全重複回避・毎回スキャン対応）"""
        if not self.pool:
            raise FileNotFoundError(f"画像ファイルが見つかりません: {self.source_directory}")

        # プール末尾に達したら再シャッフル
        if self.current_index >= len(self.pool):
            self.rng.shuffle(self.pool)
            self.current_index = 0
            self.logger.print_status("🔄 画像プール完全消化: 再シャッフルして新サイクル開始")

        selected_image = self.pool[self.current_index]
        self.current_index += 1
        self.usage_counter[selected_image] += 1

        # 履歴保存
        self._save_history()

        return selected_image

    def get_usage_stats(self) -> dict:
        """使用統計の取得（簡素化版・DynamoDB対応）"""
        total_used = sum(self.usage_counter.values())
        stats = {
            'total_images': len(self.pool),
            'used_images': len(self.usage_counter),
            'unused_images': len(self.pool) - len(self.usage_counter),
            'total_generations': total_used,
            'current_cycle_progress': f"{self.current_index}/{len(self.pool)}",
            'most_used': dict(self.usage_counter.most_common(5))
        }
        
        # DynamoDB対応: Float値をDecimal型に変換
        return EnhancedSecureRandom.safe_convert_for_dynamodb(stats)

class RandomElementGenerator:
    """ランダム要素生成（バリエーション重視・永続化対応・DynamoDB対応）"""

    def __init__(self, specific_elements: dict, general_elements: dict, history_file: str = None):
        self.specific_elements = specific_elements
        self.general_elements = general_elements
        self.history_file = history_file
        self.enhanced_random = EnhancedSecureRandom()
        self.logger = ColorLogger()

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
                        self.enhanced_random.histories[category] = deque(maxlen=5)
                    self.enhanced_random.histories[category].extend(history_list)

                # カウンターデータの復元
                for category, counter_dict in data.get('counters', {}).items():
                    if category not in self.enhanced_random.counters:
                        self.enhanced_random.counters[category] = Counter()
                    self.enhanced_random.counters[category].update(counter_dict)

                self.logger.print_status(f"📂 要素履歴読み込み完了: {len(data.get('histories', {}))}カテゴリ")
        except Exception as e:
            self.logger.print_warning(f"⚠️ 要素履歴読み込みエラー: {e}")

    def _save_history(self):
        """履歴ファイルの保存（DynamoDB対応）"""
        if not self.history_file:
            return

        try:
            data = {
                'histories': {cat: list(hist) for cat, hist in self.enhanced_random.histories.items()},
                'counters': {cat: dict(counter) for cat, counter in self.enhanced_random.counters.items()},
                'saved_at': datetime.now(JST).isoformat()
            }

            # DynamoDB対応: Float値をDecimal型に変換
            data = EnhancedSecureRandom.safe_convert_for_dynamodb(data)

            os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
            with open(self.history_file, 'w', encoding='utf-8') as f:
                # Decimal型をJSONに保存する際は文字列化
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        except Exception as e:
            self.logger.print_warning(f"⚠️ 要素履歴保存エラー: {e}")

    def generate_elements(self, gen_type, max_general: int = 3) -> str:
        """
        改良版ランダム要素生成（永続化対応・ポーズ検出モード対応・DynamoDB対応）
        
        Args:
            gen_type: 生成タイプ
            max_general: 最大一般要素数
            
        Returns:
            str: 生成されたランダム要素プロンプト
        """
        additional_prompt = ""

        # --- 特定ランダム要素（重複回避・履歴継承） --- #
        for element_type in gen_type.random_elements:
            if element_type not in self.specific_elements:
                continue

            elements_options = self.specific_elements[element_type]
            if not elements_options:
                continue

            # ポーズカテゴリは常にスキップ（重複回避のため修正）
            if element_type == "poses":
                continue # ← ここを修正：モードに関係なく常にスキップ

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
                continue # hairstyles はここで終了

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

        # general_random_elementsの処理は削除（全てspecific_random_elementsに移動するため）

        # --- 履歴保存 --- #
        self._save_history()

        return additional_prompt

    def get_usage_stats(self) -> dict:
        """使用統計の取得（DynamoDB対応）"""
        stats = self.enhanced_random.get_usage_stats()
        # DynamoDB対応: Float値をDecimal型に変換
        return EnhancedSecureRandom.safe_convert_for_dynamodb(stats)

    def generate_lora_strength(self, strength_range: List[float]) -> Decimal:
        """
        LoRA強度をDecimal型で生成（DynamoDB対応）
        
        Args:
            strength_range: 強度範囲 [min, max]
            
        Returns:
            Decimal: LoRA強度（Decimal型）
        """
        min_strength, max_strength = strength_range
        
        # 0.01刻みで生成
        steps = int((max_strength - min_strength) / 0.01) + 1
        strength = min_strength + (self.enhanced_random.rng.randint(0, steps - 1) * 0.01)
        
        # Decimal型で返す（DynamoDB対応）
        return Decimal(str(round(strength, 2)))

    def generate_age_from_range(self, age_range: List[int]) -> int:
        """
        年齢範囲からランダム年齢生成
        
        Args:
            age_range: 年齢範囲 [min, max]
            
        Returns:
            int: 生成された年齢
        """
        min_age, max_age = age_range
        return self.enhanced_random.rng.randint(min_age, max_age)

    def generate_pose_element(self, pose_mode: str) -> str:
        """
        ポーズ要素生成（ポーズ指定モード専用）
        
        Args:
            pose_mode: ポーズモード ("detection" or "specification")
            
        Returns:
            str: ポーズプロンプト（指定モードの場合のみ）
        """
        if pose_mode != "specification":
            return ""

        # random_elements.yamlからposesカテゴリを取得
        poses = self.specific_elements.get('poses', [])
        if not poses:
            self.logger.print_warning("⚠️ poses カテゴリが見つかりません")
            return ""

        # ランダムポーズ選択（重複回避）
        selected_pose = self.enhanced_random.choice_no_repeat(
            poses, "poses", window=5
        )

        self.logger.print_status(f"🎯 選択されたポーズ: {selected_pose}")
        return f", {selected_pose}"

    def convert_metadata_for_dynamodb(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        メタデータをDynamoDB保存用に変換
        
        Args:
            metadata: 変換対象のメタデータ
            
        Returns:
            Dict[str, Any]: DynamoDB保存用メタデータ
        """
        return EnhancedSecureRandom.safe_convert_for_dynamodb(metadata)

    def validate_dynamodb_compatibility(self, data: Any) -> bool:
        """
        DynamoDB互換性検証
        
        Args:
            data: 検証対象データ
            
        Returns:
            bool: DynamoDB互換性があればTrue
        """
        try:
            # Float型が含まれていないかチェック
            def has_float(obj):
                if isinstance(obj, float):
                    return True
                elif isinstance(obj, dict):
                    return any(has_float(v) for v in obj.values())
                elif isinstance(obj, list):
                    return any(has_float(item) for item in obj)
                return False
            
            return not has_float(data)
        except Exception:
            return False

    def force_decimal_conversion(self, data: Any) -> Any:
        """
        強制的なDecimal変換（デバッグ用）
        
        Args:
            data: 変換対象データ
            
        Returns:
            Any: 変換後データ
        """
        return EnhancedSecureRandom.safe_convert_for_dynamodb(data)
