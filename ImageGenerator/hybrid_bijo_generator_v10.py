#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Hybrid Bijo Image Generator v7 - SDXL統合プロンプト対応版 + モデル切り替え機能
- SDXL一本化生成対応
- プロンプト構築関数の整理・統合
- v6の全機能を保持（バッチ生成、ローカル実行、Bedrock、Slack通知等）
- Ultra Memory Safe、Bedrock対応、AWS S3/DynamoDB連携
- ランダム性大幅向上（重複回避・履歴永続化対応）
- LoRA機能対応（generation_types.yamlでのlora_settings対応）
- ポーズ指定モード追加（プロンプトベースポーズ指定）
- モデル切り替え機能追加（generation_types.yamlのmodel_name最優先）
"""

import requests
import time
import os
import base64
import subprocess
import shutil
from io import BytesIO
from PIL import Image, PngImagePlugin, ImageEnhance, ImageFilter
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config
from datetime import datetime, timedelta, timezone
import secrets
import yaml
import sys
import warnings
import json
import torch
import gc
import urllib3
from collections import deque, Counter
from decimal import Decimal
from typing import List, Any, Union
from pathlib import Path

# SSL警告を無視（修正版）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
        使用統計を辞書で返す
        - category 指定なしで全カテゴリ集計
        """
        if category:
            return dict(self.counters.get(category, {}))
        return {cat: dict(cnt) for cat, cnt in self.counters.items()}

class InputImagePool:
    """入力画像プール管理（重複回避・均等分散・毎回スキャン対応）"""
    
    def __init__(self, source_directory: str, supported_formats: List[str], history_file: str = None):
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

class RandomElementGenerator:
    """ランダム要素生成（バリエーション重視・永続化対応）"""
    
    def __init__(self, specific_elements: dict, general_elements: dict, history_file: str = None):
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
                        self.enhanced_random.histories[category] = deque(maxlen=5)
                    self.enhanced_random.histories[category].extend(history_list)
                
                # カウンターデータの復元
                for category, counter_dict in data.get('counters', {}).items():
                    if category not in self.enhanced_random.counters:
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
        
        # --- 特定ランダム要素（重複回避・履歴継承） --- #
        for element_type in gen_type.random_elements:
            if element_type not in self.specific_elements:
                continue
            
            elements_options = self.specific_elements[element_type]
            if not elements_options:
                continue
            
            # ポーズカテゴリは常にスキップ（重複回避のため修正）
            if element_type == "poses":
                continue  # ← ここを修正：モードに関係なく常にスキップ

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
        
        # general_random_elementsの処理は削除（全てspecific_random_elementsに移動するため）
        
        # --- 履歴保存 --- #
        self._save_history()
        
        return additional_prompt

    
    def get_usage_stats(self) -> dict:
        """使用統計の取得"""
        return self.enhanced_random.get_usage_stats()

class ColorLogger:
    """シェルスクリプトのカラー出力完全再現"""
    
    def __init__(self):
        # シェルスクリプトと同じANSIカラーコード
        self.GREEN = '\033[0;32m'
        self.YELLOW = '\033[0;33m'
        self.RED = '\033[0;31m'
        self.BLUE = '\033[0;34m'
        self.CYAN = '\033[0;36m'
        self.MAGENTA = '\033[0;35m'
        self.NC = '\033[0m'  # No Color
    
    def print_status(self, message):
        """[INFO] メッセージ（青色）"""
        print(f"{self.BLUE}[INFO]{self.NC} {message}")
    
    def print_success(self, message):
        """[SUCCESS] メッセージ（緑色）"""
        print(f"{self.GREEN}[SUCCESS]{self.NC} {message}")
    
    def print_warning(self, message):
        """[WARNING] メッセージ（黄色）"""
        print(f"{self.YELLOW}[WARNING]{self.NC} {message}")
    
    def print_error(self, message):
        """[ERROR] メッセージ（赤色）"""
        print(f"{self.RED}[ERROR]{self.NC} {message}")
    
    def print_stage(self, message):
        """[STAGE] メッセージ（シアン色）"""
        print(f"{self.CYAN}[STAGE]{self.NC} {message}")
    
    def print_timing(self, message):
        """[TIMING] メッセージ（マゼンタ色）"""
        print(f"{self.MAGENTA}[TIMING]{self.NC} {message}")

class HybridGenerationError(Exception):
    """ハイブリッド生成専用エラー"""
    pass

class ProcessTimer:
    """処理時間計測クラス"""
    
    def __init__(self, logger):
        self.logger = logger
        self.start_time = None
        self.phase_times = {}
    
    def start(self, process_name="処理"):
        """時間計測開始"""
        self.start_time = time.time()
        self.process_name = process_name
    
    def mark_phase(self, phase_name):
        """フェーズマーク"""
        if self.start_time:
            elapsed = time.time() - self.start_time
            self.phase_times[phase_name] = elapsed
    
    def end_and_report(self, success_count=None):
        """時間計測終了と結果表示"""
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
        """秒数を「○時間○分○秒」形式にフォーマット"""
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

class GenerationType:
    """生成タイプクラス"""
    
    def __init__(self, name, model_name, prompt, negative_prompt, random_elements=None, age_range=None, lora_settings=None):
        self.name = name
        self.model_name = model_name
        self.prompt = prompt
        self.negative_prompt = negative_prompt
        self.random_elements = random_elements or []
        self.age_range = age_range or [18, 24]
        self.lora_settings = lora_settings or []
class HybridBijoImageGeneratorV7:
    """美少女画像SDXL統合生成クラス v7.0（プロンプト統合対応版・ポーズ指定モード対応・モデル切り替え対応）"""
    
    def __init__(self):
        """美少女画像SDXL統合生成クラス初期化（Bedrock対応版・ポーズ指定モード対応・モデル切り替え対応）"""
        # 最初に重要な属性をデフォルト値で初期化（エラー回避対策）
        self.local_mode = False
        self.bedrock_enabled = False
        self.fast_mode = False
        self.ultra_safe_mode = False
        self.memory_monitoring_enabled = False
        self.auto_adjustment_enabled = False
        self.pose_mode = None  # 新規追加：ポーズモード管理
        
        self.logger = ColorLogger()
        self.logger.print_stage("🚀 美少女画像SDXL統合生成ツール Ver7.0 プロンプト統合対応版 + モデル切り替え機能 初期化中...")
        
        # セキュアランダム初期化（既存互換性維持）
        self.secure_random = SecureRandom()
        self.enhanced_random = EnhancedSecureRandom()
        self.input_image_pool = None  # 後で初期化
        self.random_element_generator = None  # 後で初期化
        
        self.logger.print_status("🔒 暗号学的安全ランダム関数初期化完了")
        
        # 設定読み込み
        self.config = self.load_config()
        
        # Bedrock機能設定の初期化
        self.setup_bedrock_features()
        
        # ローカル実行モード設定（この順序が重要）
        self.setup_local_execution_mode()
        
        # 高速化モード設定
        self.setup_fast_mode()
        
        # メモリ管理設定の初期化（強化版）
        self.setup_ultra_memory_management()
        
        # ポーズモード設定初期化（新規追加）
        self.setup_pose_mode()
        
        # 手足強化設定読み込み
        self.hand_foot_enhancement_config = self.config.get('hand_foot_enhancement', {})
        self.hand_foot_enhancement_enabled = self.hand_foot_enhancement_config.get('enabled', True)
        
        if self.hand_foot_enhancement_enabled:
            self.logger.print_status("🔧 手足品質強化モード有効")
        
        # AWS設定（ローカルモード時はスキップ）
        if not self.local_mode:
            self.setup_aws_clients()
        else:
            self.logger.print_warning("⚠️ ローカル実行モード: AWS接続をスキップします")
        
        # プロンプトデータ読み込み
        self.load_prompt_data()
        
        # 生成タイプ設定
        self.setup_generation_types()
        
        # SDXL生成設定（v7新機能）
        self.load_sdxl_config()
        
        # 一時ディレクトリ作成（先に実行）
        self.setup_temp_directory()
        
        # 拡張ランダム機能初期化（temp_dir使用後）
        self.setup_enhanced_randomness()
        
        # 最終初期化メッセージ
        self.logger.print_success("✅ SDXL統合初期化完了（モデル切り替え機能付き）...")
    
    def setup_pose_mode(self):
        """ポーズモード設定（新規追加）"""
        self.pose_mode = None  # "detection" または "specification"
        self.logger.print_status("🎯 ポーズモード設定初期化完了")
    
    def select_pose_mode(self):
        """ポーズモード選択（新規追加）"""
        while True:
            print("\n" + "="*50)
            print("🎯 ポーズモード選択")
            print("="*50)
            print("1. ポーズ検出モード（入力画像ベース）")
            print("2. ポーズ指定モード（プロンプトベース）")
            print("="*50)
            
            try:
                choice = input("選択 (1-2): ").strip()
                if choice == '1':
                    self.pose_mode = "detection"
                    self.logger.print_success("✅ ポーズ検出モード（入力画像ベース）を選択しました")
                    break
                elif choice == '2':
                    self.pose_mode = "specification"
                    self.logger.print_success("✅ ポーズ指定モード（プロンプトベース）を選択しました")
                    break
                else:
                    print("❌ 無効な選択です")
            except KeyboardInterrupt:
                print("\n🛑 ポーズモード選択が中断されました")
                raise
    
    def generate_pose_prompt(self, gen_type):
        """ポーズプロンプト生成（ポーズ指定モード用・新規追加）"""
        if self.pose_mode != "specification":
            return ""
        
        # random_elements.yamlからposesカテゴリを取得
        poses = self.specific_random_elements.get('poses', [])
        if not poses:
            self.logger.print_warning("⚠️ poses カテゴリが見つかりません")
            return ""
        
        # ランダムポーズ選択（重複回避）
        selected_pose = self.random_element_generator.enhanced_random.choice_no_repeat(
            poses, "poses", window=5
        )
        
        self.logger.print_status(f"🎯 選択されたポーズ: {selected_pose}")
        return f", {selected_pose}"

    def setup_enhanced_randomness(self):
        """拡張ランダム機能の初期化（毎回スキャン対応）"""
        # temp_dir の確認を追加
        if not hasattr(self, 'temp_dir'):
            self.logger.print_warning("⚠️ temp_dir が初期化されていません")
            return
        
        if not self.input_image_pool:
            self.logger.print_status("🔧 InputImagePool初期化中（毎回フルスキャン）...")
            self.input_image_pool = InputImagePool(
                self.input_images_config['source_directory'],
                self.input_images_config['supported_formats'],
                history_file=os.path.join(self.temp_dir, 'image_history.json')
            )
            self.logger.print_success(f"✅ InputImagePool初期化完了: {len(self.input_image_pool.pool)}枚の画像")
        
        if not self.random_element_generator:
            self.logger.print_status("🔧 RandomElementGenerator初期化中...")
            self.random_element_generator = RandomElementGenerator(
                self.specific_random_elements,
                self.general_random_elements,
                history_file=os.path.join(self.temp_dir, 'element_history.json')
            )
            self.logger.print_success("✅ RandomElementGenerator初期化完了")

    def setup_bedrock_features(self):
        """Bedrock機能設定の初期化"""
        self.bedrock_config = self.config.get('bedrock_features', {})
        self.bedrock_enabled = self.bedrock_config.get('enabled', True)
        self.bedrock_lambda_function = self.bedrock_config.get('lambda_function_name', 'aight_bedrock_comment_generator')
        
        # デフォルト適合時間帯
        self.default_suitable_slots = ["early_morning", "morning", "lunch", "evening", "night", "mid_night", "general"]
        
        if self.bedrock_enabled:
            self.logger.print_status("🤖 Bedrock機能有効")
            self.logger.print_status(f"📞 Bedrock Lambda関数: {self.bedrock_lambda_function}")
        else:
            self.logger.print_warning("⚠️ Bedrock機能無効")
    
    def setup_ultra_memory_management(self):
        """メモリ管理設定の初期化（強化版）"""
        self.memory_config = self.config.get('memory_management', {})
        self.memory_monitoring_enabled = self.memory_config.get('enabled', True)
        self.memory_threshold = self.memory_config.get('threshold_percent', 70)  # 70%に引き下げ
        self.auto_adjustment_enabled = self.memory_config.get('auto_adjustment_enabled', True)
        self.cleanup_interval = self.memory_config.get('cleanup_interval', 1)
        
        # 強化されたメモリ制御パラメータ
        self.aggressive_cleanup = True  # 積極的なクリーンアップ
        self.preemptive_adjustment = True  # 事前調整
        self.ultra_safe_mode = True  # ウルトラセーフモード
        self.max_memory_retries = 5  # メモリエラー時の最大リトライ回数
        self.memory_recovery_delay = 10  # メモリ回復待機時間（秒）
        
        # 段階的フォールバック解像度設定（SDXL用に調整）
        self.fallback_resolutions = [
            {'width': 640, 'height': 832},   # 最小
            {'width': 768, 'height': 960},   # 小
            {'width': 832, 'height': 1088},  # 中
        ]
        self.current_fallback_level = -1  # -1は通常設定を意味する
        
        # デフォルト解像度設定の保存（自動調整用）
        self.original_config = {
            'width': self.config.get('sdxl_generation', {}).get('width', 896),
            'height': self.config.get('sdxl_generation', {}).get('height', 1152)
        }
        
        self.logger.print_status("🧠 ウルトラメモリ管理システム初期化完了")
        self.logger.print_status(f"🔍 メモリ監視: {'有効' if self.memory_monitoring_enabled else '無効'}")
        self.logger.print_status(f"⚙️ 自動調整: {'有効' if self.auto_adjustment_enabled else '無効'}")
        self.logger.print_status(f"📊 メモリ閾値: {self.memory_threshold}%")
        self.logger.print_status(f"🛡️ ウルトラセーフモード: {'有効' if self.ultra_safe_mode else '無効'}")
    
    def setup_local_execution_mode(self):
        """ローカル実行モード設定"""
        self.local_execution_config = self.config.get('local_execution', {})
        self.local_mode = self.local_execution_config.get('enabled', False)
        
        if self.local_mode:
            self.logger.print_warning("🔧 ローカル実行モード有効")
            
            # ローカル出力ディレクトリ設定
            self.local_output_dir = self.local_execution_config.get('output_directory', './output/test_images')
            os.makedirs(self.local_output_dir, exist_ok=True)
            
            # ジャンル別サブディレクトリ作成
            if self.local_execution_config.get('create_subdirs', True):
                for genre in self.config.get('generation', {}).get('genres', ['normal', 'seiso', 'gyal_natural', 'gyal_black', 'gyal_erotic', 'teen']):
                    genre_dir = os.path.join(self.local_output_dir, genre)
                    os.makedirs(genre_dir, exist_ok=True)
            
            self.logger.print_status(f"📁 ローカル出力ディレクトリ: {self.local_output_dir}")
        else:
            self.logger.print_status("🔧 通常実行モード（AWS連携）")
    
    def setup_fast_mode(self):
        """高速化モード設定"""
        self.fast_mode_config = self.config.get('fast_mode', {})
        self.fast_mode = self.fast_mode_config.get('enabled', False)
        
        if self.fast_mode:
            self.logger.print_warning("⚡ 高速化モード有効")
            self.logger.print_warning("⚡ SDXL軽量化設定適用")
        else:
            self.logger.print_status("🔧 通常品質モード")
    def load_config(self):
        """設定ファイル読み込み（互換性対応）"""
        config_files = ['config_v10.yaml', 'config_v5.yaml', 'config.yaml']
        for config_file in config_files:
            try:
                with open(config_file, 'r', encoding='utf-8') as file:
                    config = yaml.safe_load(file)
                    self.logger.print_success(f"✅ {config_file}読み込み成功")
                    return config
            except FileNotFoundError:
                continue
            except yaml.YAMLError as e:
                self.logger.print_error(f"❌ {config_file}読み込みエラー: {e}")
                continue
        
        self.logger.print_error("❌ 設定ファイルが見つかりません（config_v8.yaml, config_v5.yaml または config.yaml）")
        sys.exit(1)
    
    def setup_aws_clients(self):
        """AWSクライアント初期化"""
        aws_config = self.config['aws']
        
        # タイムアウト設定
        boto_config = Config(
            retries={'max_attempts': 3},
            read_timeout=self.config.get('performance', {}).get('dynamodb_timeout', 30),
            connect_timeout=30
        )
        
        self.s3_client = boto3.client('s3', region_name=aws_config['region'], config=boto_config)
        self.dynamodb = boto3.resource('dynamodb', region_name=aws_config['region'], config=boto_config)
        self.dynamodb_table = self.dynamodb.Table(aws_config['dynamodb_table'])
        
        # Bedrock機能用のLambdaクライアント初期化
        if self.bedrock_enabled and not self.local_mode:
            self.lambda_client = boto3.client('lambda', region_name=aws_config['region'], config=boto_config)
            self.logger.print_status("🤖 Bedrock Lambda クライアント初期化完了")
        
        self.logger.print_status(f"🔧 AWS設定: リージョン={aws_config['region']}, S3={aws_config['s3_bucket']}, DynamoDB={aws_config['dynamodb_table']}")
    
    def load_yaml(self, filepath):
        """YAMLファイル読み込み"""
        try:
            with open(filepath, 'r', encoding='utf-8') as file:
                return yaml.safe_load(file)
        except FileNotFoundError:
            self.logger.print_error(f"❌ YAMLファイルが見つかりません: {filepath}")
            sys.exit(1)
        except yaml.YAMLError as e:
            self.logger.print_error(f"❌ YAML読み込みエラー {filepath}: {e}")
            sys.exit(1)
    
    def load_prompt_data(self):
        """プロンプト関連データ読み込み（Ver2/Ver3両対応・SDXL統合対応）"""
        prompt_files = self.config['prompt_files']
        self.logger.print_status("📂 プロンプトファイル読み込み中...")
        
        self.random_elements_data = self.load_yaml(prompt_files['random_elements'])
        self.prompts_data = self.load_yaml(prompt_files['prompts'])
        self.generation_types_data = self.load_yaml(prompt_files['generation_types'])
        
        # プロンプト要素を取得
        self.specific_random_elements = self.random_elements_data.get('specific_random_elements', {})
        self.general_random_elements = self.random_elements_data.get('general_random_elements', {})
        
        # Ver2/Ver3/SDXL統合版 プロンプト構造に対応
        if 'quality_prompts' in self.prompts_data:
            # Ver3構造またはSDXL統合構造
            self.quality_prompts = self.prompts_data.get('quality_prompts', {})
            self.face_prompts = self.prompts_data.get('face_prompts', {})
            self.body_prompts = self.prompts_data.get('body_prompts', {})
            self.other_prompts = self.prompts_data.get('other_prompts', {})
            self.user_prompts = self.prompts_data.get('user_prompts', {})
            self.anatomy_prompts = self.prompts_data.get('anatomy_prompts', {})  # 手足強化用
            self.single_person_prompts = self.prompts_data.get('single_person_prompts', {})  # 一人の人物生成強化プロンプト
            self.negative_prompts = self.prompts_data.get('negative_prompts', {})
        else:
            # Ver2構造（互換性対応）
            self.core_prompt = self.prompts_data.get('core_prompt', '')
            self.core_negative_prompt = self.prompts_data.get('core_negative_prompt', '')
            self.beauty_prompt = self.prompts_data.get('beauty_prompt', '')
            self.beauty_negative_prompt = self.prompts_data.get('beauty_negative_prompt', '')
            self.single_person_prompts = {}  # Ver2互換性のため空辞書を追加
        
        self.logger.print_success("✅ プロンプトファイル読み込み完了")
    
    def setup_generation_types(self):
        """生成タイプ設定"""
        self.generation_types = []
        if 'generation_types' in self.generation_types_data:
            for type_data in self.generation_types_data['generation_types']:
                # teen/jkタイプの年齢を18歳以上に修正
                if type_data['name'] in ['teen', 'jk']:
                    type_data['age_range'] = [18, 20]
                
                gen_type = GenerationType(
                    name=type_data['name'],
                    model_name=type_data['model_name'],
                    prompt=type_data['prompt'],
                    negative_prompt=type_data['negative_prompt'],
                    random_elements=type_data.get('random_elements', []),
                    age_range=type_data.get('age_range', [18, 24]),
                    lora_settings=type_data.get('lora_settings', [])  # LoRA設定を追加
                )
                self.generation_types.append(gen_type)
            
            self.logger.print_status(f"📋 生成タイプ: {[gt.name for gt in self.generation_types]}")
        else:
            self.logger.print_error("❌ generation_types.yamlにgeneration_typesキーが見つかりません")
            sys.exit(1)
    
    def load_sdxl_config(self):
        """SDXL生成設定を読み込み（v7新機能）"""
        self.sdxl_config = self.config.get('sdxl_generation', {})
        self.controlnet_config = self.config.get('controlnet', {})
        self.input_images_config = self.config.get('input_images', {})
        self.adetailer_config = self.config.get('adetailer', {})
        self.error_handling_config = self.config.get('error_handling', {})
        
        # 高速化設定適用
        if self.fast_mode:
            self.apply_fast_mode_settings()
        
        self.logger.print_status("🔧 SDXL統合生成設定読み込み完了")
    
    def apply_fast_mode_settings(self):
        """高速化設定を適用（SDXL用）"""
        self.logger.print_warning("⚡ SDXL高速化設定適用中...")
        
        # SDXL軽量化
        sdxl_fast = self.fast_mode_config.get('sdxl_fast', {})
        if sdxl_fast:
            for key, value in sdxl_fast.items():
                if key in self.sdxl_config:
                    self.sdxl_config[key] = value
                    self.logger.print_status(f"⚡ SDXL {key}: {value}")
        
        # ControlNet軽量化
        controlnet_fast = self.fast_mode_config.get('controlnet_fast', {})
        if controlnet_fast:
            if 'openpose_weight' in controlnet_fast:
                self.controlnet_config['openpose']['weight'] = controlnet_fast['openpose_weight']
                self.logger.print_status(f"⚡ OpenPose weight: {controlnet_fast['openpose_weight']}")
            
            if 'depth_weight' in controlnet_fast:
                self.controlnet_config['depth']['weight'] = controlnet_fast['depth_weight']
                self.logger.print_status(f"⚡ Depth weight: {controlnet_fast['depth_weight']}")
            
            if 'processor_res' in controlnet_fast:
                self.controlnet_config['openpose']['processor_res'] = controlnet_fast['processor_res']
                self.controlnet_config['depth']['processor_res'] = controlnet_fast['processor_res']
                self.logger.print_status(f"⚡ Processor res: {controlnet_fast['processor_res']}")
        
        # ADetailer軽量化
        adetailer_fast = self.fast_mode_config.get('adetailer_fast', {})
        if adetailer_fast:
            if 'steps' in adetailer_fast:
                self.adetailer_config['steps'] = adetailer_fast['steps']
                self.logger.print_status(f"⚡ ADetailer steps: {adetailer_fast['steps']}")
            
            if 'inpaint_width' in adetailer_fast:
                self.adetailer_config['inpaint_width'] = adetailer_fast['inpaint_width']
                self.adetailer_config['inpaint_height'] = adetailer_fast['inpaint_height']
                self.logger.print_status(f"⚡ ADetailer inpaint size: {adetailer_fast['inpaint_width']}x{adetailer_fast['inpaint_height']}")
    
    def setup_temp_directory(self):
        """一時ディレクトリ設定"""
        self.temp_dir = self.config.get('temp_files', {}).get('directory', '/tmp/sd_process')
        os.makedirs(self.temp_dir, exist_ok=True)
        self.logger.print_status(f"📁 一時ディレクトリ: {self.temp_dir}")
    
    # ========== 統合プロンプト構築関数群 ==========
    
    def build_prompts(self, gen_type, mode="auto"):
        """
        プロンプト構築メイン関数（統合版）
        Args:
            gen_type: 生成タイプ
            mode: 構築モード ("auto", "basic", "detailed", "sdxl_unified")
        Returns:
            tuple: モードに応じたプロンプト構造
        """
        if mode == "auto":
            # 自動判定：YAML構造に基づく分岐
            if hasattr(self, 'quality_prompts'):
                if 'sdxl_unified' in self.quality_prompts:
                    # SDXL統合版が利用可能
                    return self.build_unified_sdxl_prompts(gen_type)
                else:
                    # 詳細プロンプト構築（旧v3）
                    return self.build_detailed_prompts(gen_type)
            else:
                # 基本プロンプト構築（旧v2）
                return self.build_basic_prompts(gen_type)
        elif mode == "basic":
            return self.build_basic_prompts(gen_type)
        elif mode == "detailed":
            return self.build_detailed_prompts(gen_type)
        elif mode == "sdxl_unified":
            return self.build_unified_sdxl_prompts(gen_type)
        else:
            raise ValueError(f"Unknown prompt build mode: {mode}")
    
    def build_unified_sdxl_prompts(self, gen_type):
        """
        SDXL統合プロンプト構築（Phase1+Phase2統合版）
        Args:
            gen_type: 生成タイプ
        Returns:
            tuple: (prompt, negative_prompt, adetailer_negative)
        """
        # 手足品質向上プロンプト、一人強化プロンプト
        hand_foot_quality = ""
        if self.hand_foot_enhancement_enabled:
            h = self.anatomy_prompts.get('accurate_hands', '')
            f = self.anatomy_prompts.get('accurate_feet', '')
            a = self.anatomy_prompts.get('perfect_anatomy', '')
            n = self.anatomy_prompts.get('neck_position', '')
            s = self.anatomy_prompts.get('skeletal_structure', '')
            k = self.anatomy_prompts.get('full_anatomy', '')
            hand_foot_quality = f", {h}, {f}, {a}, {n}, {s}, {k}"
        
        # 型安全にプロンプト文字列取得
        def safe_get(d: dict, key: str, default: str = "") -> str:
            if d is None:
                return default
            if not isinstance(d, dict):
                return default
            v = d.get(key, default)
            if isinstance(v, dict):
                if "prompt" in v:
                    return str(v["prompt"])
                if "text" in v:
                    return str(v["text"])
                return ", ".join(str(x) for x in v.values() if x)
            return str(v) if v else default
        
        # ランダム要素と年齢プロンプトを先に用意
        additional = self.random_element_generator.generate_elements(gen_type)
        min_age, max_age = gen_type.age_range
        age = self.enhanced_random.rng.randint(min_age, max_age)
        age_prompt = f", BREAK, {age} years old"
        
        # ポーズプロンプト生成（新機能）
        pose_prompt = self.generate_pose_prompt(gen_type)
        
        # 一人の人物生成強化プロンプト（新規追加）
        single_person_emphasis = ""
        if (hasattr(self, 'single_person_prompts') and
            self.single_person_prompts is not None and
            isinstance(self.single_person_prompts, dict) and
            len(self.single_person_prompts) > 0):
            try:
                solo_prompt = safe_get(self.single_person_prompts, 'solo_emphasis')
                if solo_prompt and solo_prompt.strip():
                    single_person_emphasis = f", {solo_prompt}"
            except Exception as e:
                self.logger.print_warning(f"⚠️ single_person_prompts処理エラー: {e}")
                single_person_emphasis = ""
        
        # 統合プロンプト要素
        parts = [
            safe_get(self.quality_prompts, 'sdxl_unified'),
            safe_get(self.face_prompts, 'sdxl_unified'),
            safe_get(self.body_prompts, 'sdxl_unified'),
            safe_get(self.user_prompts, 'nsfw_content'),
            safe_get(self.user_prompts, 'ethnicity'),
            safe_get(self.user_prompts, 'custom_addition'),
            str(gen_type.prompt) if gen_type.prompt else ""
        ]
        
        valid = [p for p in parts if p and p.strip()]
        unified = ", ".join(valid) + single_person_emphasis + additional + hand_foot_quality + age_prompt + pose_prompt
        
        # LoRAプロンプトを追加
        lora_prompt = self.generate_lora_prompt(gen_type)
        unified += lora_prompt
        
        # ネガティブプロンプト（修正版：generation_types.yamlのnegative_promptを統合）
        base_neg = safe_get(self.negative_prompts, 'comprehensive')
        # generation_types.yamlのnegative_promptを統合（修正箇所）
        if hasattr(gen_type, 'negative_prompt') and gen_type.negative_prompt:
            if base_neg:
                base_neg = f"{base_neg}, {gen_type.negative_prompt}"
            else:
                base_neg = gen_type.negative_prompt
        
        ad_neg = safe_get(self.negative_prompts, 'adetailer_negative')
        # generation_types.yamlのnegative_promptをADetailerにも適用（修正箇所）
        if hasattr(gen_type, 'negative_prompt') and gen_type.negative_prompt:
            if ad_neg:
                ad_neg = f"{ad_neg}, {gen_type.negative_prompt}"
            else:
                ad_neg = gen_type.negative_prompt
        
        if self.hand_foot_enhancement_enabled:
            hf_neg = safe_get(self.negative_prompts, 'hand_foot_negative')
            ns_neg = safe_get(self.negative_prompts, 'neck_skeleton_negative')
            if hf_neg:
                base_neg = f"{base_neg}, {hf_neg}, {ns_neg}"
                ad_neg = f"{ad_neg}, {hf_neg}, {ns_neg}"
        
        return unified, base_neg, ad_neg
    
    def build_detailed_prompts(self, gen_type, highres_mode="SDXL"):
        """
        詳細プロンプト構築（旧v3：Phase1+Phase2分離版）
        Args:
            gen_type: 生成タイプ
            highres_mode: 高画質化モード（"SDXL" or "SD15"）
        Returns:
            tuple: (phase1_prompt, phase2_prompt, negative_prompt, adetailer_negative)
        """
        # 手足品質向上プロンプトを追加
        hand_foot_quality = ""
        if self.hand_foot_enhancement_enabled and hasattr(self, 'anatomy_prompts'):
            hand_quality = self.anatomy_prompts.get('accurate_hands', '')
            foot_quality = self.anatomy_prompts.get('accurate_feet', '')
            anatomy_quality = self.anatomy_prompts.get('perfect_anatomy', '')
            hand_foot_quality = f", {hand_quality}, {foot_quality}, {anatomy_quality}"
        
        # Phase1プロンプト構築
        phase1_prompt_parts = [
            self.quality_prompts.get('phase1_quality', ''),
            self.face_prompts.get('phase1_face', ''),
            self.body_prompts.get('phase1_body', ''),
            self.user_prompts.get('nsfw_content', ''),
            gen_type.prompt
        ]
        
        # Phase2プロンプト構築（高画質化モード対応）
        if highres_mode == "SDXL":
            phase2_face = self.face_prompts.get('phase2_face_sdxl', '')
        else:  # SD15
            phase2_face = self.face_prompts.get('phase2_face_sd15', '')
        
        phase2_prompt_parts = [
            self.quality_prompts.get('phase2_quality', ''),
            phase2_face,
            self.body_prompts.get('phase2_body', ''),
            self.user_prompts.get('nsfw_content', ''),
            self.user_prompts.get('ethnicity', ''),
            self.user_prompts.get('custom_addition', ''),
            gen_type.prompt
        ]
        
        # セキュアランダム要素追加（改良版使用）
        additional_prompt = self.generate_random_elements(gen_type)
        
        # セキュア年齢選択
        min_age, max_age = gen_type.age_range
        selected_age = self.enhanced_random.rng.randint(min_age, max_age)
        age_prompt = f", BREAK, {selected_age} years old"
        
        # ポーズプロンプト追加（新機能）
        pose_prompt = self.generate_pose_prompt(gen_type)
        
        # LoRAプロンプト追加
        lora_prompt = self.generate_lora_prompt(gen_type)
        
        # 最終プロンプト構築
        phase1_prompt = ", ".join([p for p in phase1_prompt_parts if p]) + additional_prompt + hand_foot_quality + age_prompt + pose_prompt + lora_prompt
        phase2_prompt = ", ".join([p for p in phase2_prompt_parts if p]) + additional_prompt + hand_foot_quality + age_prompt + pose_prompt + lora_prompt
        
        # ネガティブプロンプト（修正版：generation_types.yamlのnegative_promptを統合）
        base_negative = self.negative_prompts.get('comprehensive', '')
        # generation_types.yamlのnegative_promptを統合（修正箇所）
        if hasattr(gen_type, 'negative_prompt') and gen_type.negative_prompt:
            if base_negative:
                base_negative = f"{base_negative}, {gen_type.negative_prompt}"
            else:
                base_negative = gen_type.negative_prompt
        
        adetailer_negative = self.negative_prompts.get('adetailer_negative', '')
        # generation_types.yamlのnegative_promptをADetailerにも適用（修正箇所）
        if hasattr(gen_type, 'negative_prompt') and gen_type.negative_prompt:
            if adetailer_negative:
                adetailer_negative = f"{adetailer_negative}, {gen_type.negative_prompt}"
            else:
                adetailer_negative = gen_type.negative_prompt
        
        # 手足強化：手足専用ネガティブプロンプトを追加
        if self.hand_foot_enhancement_enabled:
            hand_foot_negative = self.negative_prompts.get('hand_foot_negative', '')
            neck_skeleton_negative = self.negative_prompts.get('neck_skeleton_negative', '')
            if hand_foot_negative:
                base_negative = f"{base_negative}, {hand_foot_negative}, {neck_skeleton_negative}"
                adetailer_negative = f"{adetailer_negative}, {hand_foot_negative}, {neck_skeleton_negative}"
        
        return phase1_prompt, phase2_prompt, base_negative, adetailer_negative
    
    def build_basic_prompts(self, gen_type):
        """
        基本プロンプト構築（旧v2：互換性維持用）
        Args:
            gen_type: 生成タイプ
        Returns:
            tuple: (prompt, prompt, negative_prompt, negative_prompt)
        Note: Phase1/Phase2共通のため同じプロンプトを2回返す
        """
        # ランダム要素追加（改良版使用）
        additional_prompt = self.generate_random_elements(gen_type)
        self.logger.print_success(f"🔒 Random要素追加完了: {additional_prompt}")
        
        # 年齢追加
        min_age, max_age = gen_type.age_range
        selected_age = self.enhanced_random.rng.randint(min_age, max_age)
        age_prompt = f", BREAK, {selected_age} years old"
        
        # ポーズプロンプト追加（新機能）
        pose_prompt = self.generate_pose_prompt(gen_type)
        
        # LoRAプロンプト追加
        lora_prompt = self.generate_lora_prompt(gen_type)
        
        # 基本プロンプト（Phase1/Phase2共通）
        enhanced_prompt = f"{self.core_prompt}, {self.beauty_prompt}, {gen_type.prompt}{additional_prompt}{age_prompt}{pose_prompt}{lora_prompt}"
        
        # ネガティブプロンプト（修正版：generation_types.yamlのnegative_promptを統合）
        enhanced_negative_prompt = f"{self.core_negative_prompt}, {self.beauty_negative_prompt}"
        # generation_types.yamlのnegative_promptを統合（修正箇所）
        if hasattr(gen_type, 'negative_prompt') and gen_type.negative_prompt:
            enhanced_negative_prompt = f"{enhanced_negative_prompt}, {gen_type.negative_prompt}"
        
        return enhanced_prompt, enhanced_prompt, enhanced_negative_prompt, enhanced_negative_prompt
    # ========== モデル切り替え機能（新規追加） ==========
    
    def get_current_model(self):
        """現在のモデル名を取得"""
        try:
            response = requests.get(
                f"{self.config['stable_diffusion']['api_url']}/sdapi/v1/options",
                timeout=30,
                verify=self.config['stable_diffusion']['verify_ssl']
            )
            response.raise_for_status()
            result = response.json()
            current_model = result.get('sd_model_checkpoint', 'Unknown')
            return current_model
        except Exception as e:
            self.logger.print_warning(f"⚠️ 現在のモデル取得エラー: {e}")
            return None
    
    def switch_model(self, target_model_name):
        """モデルを指定されたモデルに切り替え"""
        try:
            # 現在のモデルを確認
            current_model = self.get_current_model()
            if current_model == target_model_name:
                self.logger.print_status(f"🎯 モデル切り替え不要: 既に {target_model_name} が使用中")
                return True
            
            self.logger.print_status(f"🔄 モデル切り替え開始: {current_model} → {target_model_name}")
            
            # モデル切り替え設定取得
            switch_config = self.config.get('model_switching', {})
            switch_timeout = switch_config.get('switch_timeout', 120)
            wait_after_switch = switch_config.get('wait_after_switch', 10)
            verification_retries = switch_config.get('verification_retries', 3)
            
            # モデル切り替えAPI呼び出し
            switch_start = time.time()
            payload = {
                "sd_model_checkpoint": target_model_name
            }
            
            response = requests.post(
                f"{self.config['stable_diffusion']['api_url']}/sdapi/v1/options",
                json=payload,
                timeout=switch_timeout,
                verify=self.config['stable_diffusion']['verify_ssl']
            )
            response.raise_for_status()
            
            switch_duration = time.time() - switch_start
            self.logger.print_status(f"⏱️ モデル切り替えAPI呼び出し完了: {switch_duration:.1f}秒")
            
            # 切り替え後待機
            self.logger.print_status(f"⏳ モデル切り替え後待機: {wait_after_switch}秒")
            time.sleep(wait_after_switch)
            
            # モデル切り替え確認
            for attempt in range(verification_retries):
                current_model = self.get_current_model()
                if current_model == target_model_name:
                    total_duration = time.time() - switch_start
                    self.logger.print_success(f"✅ モデル切り替え完了: {target_model_name} (総時間: {total_duration:.1f}秒)")
                    return True
                else:
                    self.logger.print_warning(f"⚠️ モデル切り替え確認失敗 (試行{attempt + 1}/{verification_retries}): 期待={target_model_name}, 実際={current_model}")
                    if attempt < verification_retries - 1:
                        time.sleep(5)  # リトライ前に待機
            
            # 最終確認失敗
            self.logger.print_error(f"❌ モデル切り替え失敗: {verification_retries}回試行後も {target_model_name} に切り替わりませんでした")
            return False
            
        except requests.RequestException as e:
            self.logger.print_error(f"❌ モデル切り替えAPI呼び出しエラー: {e}")
            return False
        except Exception as e:
            self.logger.print_error(f"❌ モデル切り替え処理エラー: {e}")
            return False
    
    def ensure_model_for_generation_type(self, gen_type):
        """生成タイプに必要なモデルが設定されていることを確認し、必要に応じて切り替え"""
        # generation_types.yamlでmodel_nameが未定義の場合はエラー
        if not hasattr(gen_type, 'model_name') or not gen_type.model_name:
            self.logger.print_error(f"❌ 生成タイプ '{gen_type.name}' のmodel_nameが未定義です")
            self.logger.print_error("❌ generation_types.yamlでmodel_nameを指定してください")
            raise HybridGenerationError(f"生成タイプ '{gen_type.name}' のmodel_nameが未定義")
        
        target_model = gen_type.model_name
        self.logger.print_status(f"🎯 生成タイプ '{gen_type.name}' 必要モデル: {target_model}")
        
        # モデル切り替え実行
        success = self.switch_model(target_model)
        if not success:
            raise HybridGenerationError(f"モデル切り替え失敗: {target_model}")
        
        return True
    
    # ========== LoRA・Bedrock・ランダム要素関数群 ==========
    
    def generate_lora_prompt(self, gen_type):
        """
        LoRAプロンプト生成関数（新規追加）
        generation_types.yamlのlora_settingsに基づいてLoRAプロンプトを生成
        """
        if not hasattr(gen_type, 'lora_settings') or not gen_type.lora_settings:
            return ""
        
        lora_prompts = []
        for lora_setting in gen_type.lora_settings:
            lora_id = lora_setting.get('lora_id')
            strength_range = lora_setting.get('strength_range', [0.5, 1.0])
            
            if not lora_id:
                continue
            
            # 範囲内で0.01刻みの完全ランダム選択
            min_strength, max_strength = strength_range
            # 0.01刻みで生成
            steps = int((max_strength - min_strength) / 0.01) + 1
            strength = min_strength + (self.enhanced_random.rng.randint(0, steps - 1) * 0.01)
            # 小数点以下2桁に丸める
            strength = round(strength, 2)
            
            # LoRAプロンプト形式で追加
            lora_prompt = f"<lora:{lora_id}:{strength}>"
            lora_prompts.append(lora_prompt)
        
        # 全てのLoRAプロンプトを結合
        return ", " + ", ".join(lora_prompts) if lora_prompts else ""
    
    def generate_all_timeslot_comments(self, image_metadata):
        """全時間帯のコメント一括生成（Bedrock Lambda呼び出し）"""
        if self.local_mode or not self.bedrock_enabled:
            self.logger.print_status("ローカルモードまたはBedrock無効のためコメント生成をスキップします")
            return {}
        
        try:
            self.logger.print_status("Bedrockで全時間帯コメントを生成中...")
            
            # APIリミット制限対策：生成前に短時間待機
            time.sleep(1)
            
            # Bedrock Lambda関数を呼び出し
            response = self.lambda_client.invoke(
                FunctionName=self.bedrock_lambda_function,
                InvocationType='RequestResponse',
                Payload=json.dumps({
                    'generation_mode': 'all_timeslots',
                    'image_metadata': image_metadata
                })
            )
            
            result = json.loads(response['Payload'].read())
            body = json.loads(result['body'])
            
            if body.get('success'):
                all_comments = body.get('all_comments', {})
                self.logger.print_success(f"全時間帯コメント生成完了: {len(all_comments)}件")
                
                # 生成成功後も短時間待機（連続呼び出し制限対策）
                time.sleep(2)
                return all_comments
            else:
                self.logger.print_warning(f"Bedrockコメント生成失敗: {body.get('error')}")
                return {}
        
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'ThrottlingException':
                self.logger.print_warning("Bedrock API制限に達しました。画像生成は継続します。")
                time.sleep(5)  # スロットリング時は長めに待機
            elif error_code == 'TooManyRequestsException':
                self.logger.print_warning("Lambda同時実行制限に達しました。画像生成は継続します。")
                time.sleep(3)
            else:
                self.logger.print_error(f"Bedrock ClientError: {error_code}")
            return {}
        
        except Exception as e:
            self.logger.print_error(f"Bedrockコメント生成エラー: {e}")
            # エラーが発生しても画像生成は継続
            return {}
    
    def select_random_input_image(self):
        """改良版入力画像選択（毎回スキャン対応）"""
        if not self.input_image_pool:
            self.setup_enhanced_randomness()
        
        self.logger.print_status("🔒 拡張セキュアランダム画像選択中...")
        selected_image = self.input_image_pool.get_next_image()
        self.logger.print_success(f"🔒 拡張選択完了: {os.path.basename(selected_image)}")
        self.logger.print_status(f"画像ファイル名: {os.path.basename(selected_image)}")
        
        # 使用統計のログ出力（10枚ごと）
        total_usage = sum(self.input_image_pool.usage_counter.values())
        if total_usage % 10 == 0:
            stats = self.input_image_pool.get_usage_stats()
            self.logger.print_status(f"📊 画像使用統計: {stats}")
        
        return selected_image
    
    def generate_random_elements(self, gen_type):
        """改良版ランダム要素生成（完全重複回避・永続化対応）"""
        if not self.random_element_generator:
            self.setup_enhanced_randomness()
        
        # ポーズモードをgen_typeに設定（新規追加）
        gen_type.pose_mode = getattr(self, 'pose_mode', 'detection')
        
        additional_prompt = self.random_element_generator.generate_elements(gen_type)
        
        # 使用統計のログ出力（20枚ごと）
        total_generations = sum(
            sum(counter.values())
            for counter in self.random_element_generator.enhanced_random.counters.values()
        )
        if total_generations % 20 == 0:
            stats = self.random_element_generator.get_usage_stats()
            self.logger.print_status(f"📊 ランダム要素使用統計: {stats}")
        
        return additional_prompt
    
    # ========== メモリ管理強化版 ==========
    
    def check_memory_usage(self, force_cleanup=False):
        """VRAM使用量の監視（強化版）"""
        if not torch.cuda.is_available():
            return True
        
        try:
            allocated = torch.cuda.memory_allocated() / 1024**3  # GB
            cached = torch.cuda.memory_reserved() / 1024**3  # GB
            total = torch.cuda.get_device_properties(0).total_memory / 1024**3
            usage_percent = (allocated / total) * 100
            
            if self.memory_monitoring_enabled:
                self.logger.print_status(f"🧠 VRAM使用量: {allocated:.2f}GB / {total:.2f}GB ({usage_percent:.1f}%)")
            
            # 強制クリーンアップが要求された場合
            if force_cleanup:
                self.perform_aggressive_memory_cleanup()
                return False
            
            # 閾値を超えた場合の処理
            if usage_percent > self.memory_threshold:
                self.logger.print_warning(f"⚠️ VRAM使用量が{self.memory_threshold}%を超えています ({usage_percent:.1f}%)")
                
                # 積極的なメモリクリーンアップ
                self.perform_aggressive_memory_cleanup()
                
                # 自動調整が有効な場合は設定を調整
                if self.auto_adjustment_enabled:
                    adjusted = self.escalate_memory_adjustment()
                    if adjusted:
                        self.logger.print_warning("📉 設定を段階的に調整しました")
                
                return False
            
            return True
        
        except Exception as e:
            self.logger.print_error(f"❌ メモリ監視エラー: {e}")
            return True
    
    def perform_aggressive_memory_cleanup(self):
        """積極的なメモリクリーンアップの実行"""
        try:
            self.logger.print_status("🧹 積極的メモリクリーンアップ開始")
            
            # 複数回のPyTorchメモリクリーンアップ
            if torch.cuda.is_available():
                for i in range(3):  # 3回実行
                    torch.cuda.empty_cache()
                    torch.cuda.synchronize()
                    time.sleep(1)
            
            # 複数回のPythonガベージコレクション
            for i in range(3):
                gc.collect()
                time.sleep(0.5)
            
            # 長時間待機でメモリ安定化
            time.sleep(self.memory_recovery_delay)
            
            self.logger.print_success("✅ 積極的メモリクリーンアップ完了")
        
        except Exception as e:
            self.logger.print_error(f"❌ 積極的メモリクリーンアップエラー: {e}")
    
    def escalate_memory_adjustment(self):
        """段階的メモリ調整のエスカレーション（SDXL対応）"""
        if not hasattr(self, 'sdxl_config'):
            return False
        
        # フォールバック解像度を段階的に適用
        self.current_fallback_level += 1
        
        if self.current_fallback_level >= len(self.fallback_resolutions):
            self.logger.print_error("❌ 最小解像度に到達しました。これ以上調整できません")
            return False
        
        fallback = self.fallback_resolutions[self.current_fallback_level]
        
        # SDXL解像度の調整
        self.sdxl_config['width'] = fallback['width']
        self.sdxl_config['height'] = fallback['height']
        
        self.logger.print_warning(f"📉 SDXL解像度をフォールバックレベル{self.current_fallback_level + 1}に調整: {fallback['width']}x{fallback['height']}")
        
        return True
    
    def execute_with_ultra_memory_safety(self, func, operation_name, max_retries=None):
        """ウルトラメモリセーフティ付きで関数実行"""
        if max_retries is None:
            max_retries = self.max_memory_retries
        
        for attempt in range(max_retries):
            try:
                # 事前メモリチェックと強制クリーンアップ
                if self.ultra_safe_mode:
                    self.logger.print_status(f"🛡️ {operation_name} 事前安全チェック")
                    self.check_memory_usage(force_cleanup=True)
                
                # 実際の処理実行
                result = func()
                
                # 実行後のメモリクリーンアップ
                self.perform_aggressive_memory_cleanup()
                
                return result
            
            except RuntimeError as e:
                if "CUDA out of memory" in str(e) and attempt < max_retries - 1:
                    self.logger.print_warning(f"⚠️ {operation_name}でメモリ不足により再試行 ({attempt + 1}/{max_retries})")
                    
                    # 強制的な積極的メモリクリーンアップ
                    self.perform_aggressive_memory_cleanup()
                    
                    # 設定の段階的調整
                    if self.auto_adjustment_enabled:
                        adjusted = self.escalate_memory_adjustment()
                        if adjusted:
                            self.logger.print_warning("📉 設定を段階的に調整しました")
                    
                    # 長時間待機してからリトライ
                    self.logger.print_status(f"⏳ メモリ回復のため{self.memory_recovery_delay}秒待機...")
                    time.sleep(self.memory_recovery_delay)
                    continue
                else:
                    raise e
            except Exception as e:
                raise e
        
        raise HybridGenerationError(f"{operation_name}: メモリエラーによる最大リトライ回数に到達")
    
    def preprocess_input_image(self, image_path):
        """入力画像の前処理（SDXL用リサイズ、品質調整・ポーズ指定モード対応）"""
        # ポーズ指定モードの場合は前処理をスキップ
        if self.pose_mode == "specification":
            self.logger.print_status("🎯 ポーズ指定モード: 入力画像前処理をスキップします")
            return None
        
        self.logger.print_status("ControlNet-SDXL用画像リサイズ中...")
        
        # SDXL設定の解像度を取得
        target_width = self.sdxl_config['width']
        target_height = self.sdxl_config['height']
        
        image = Image.open(image_path)
        image = image.resize((target_width, target_height), Image.LANCZOS)
        
        # 高品質PNG保存
        resized_path = os.path.join(self.temp_dir, "resized_sdxl_input.png")
        image.save(resized_path, "PNG", optimize=True, quality=self.input_images_config.get('resize_quality', 95))
        
        file_size = os.path.getsize(resized_path)
        self.logger.print_success(f"SDXL画像リサイズ完了: {file_size} bytes")
        
        return resized_path
    
    def encode_image_to_base64(self, image_path):
        """画像をBase64エンコード（ポーズ指定モード対応）"""
        # ポーズ指定モードの場合はNoneを返す
        if self.pose_mode == "specification" or image_path is None:
            return None
        
        with open(image_path, 'rb') as img_file:
            img_data = img_file.read()
            b64_data = base64.b64encode(img_data).decode('utf-8')
            self.logger.print_status(f"Base64エンコードサイズ: {len(b64_data)} 文字")
            return b64_data
    
    def execute_generation(self, gen_type, input_b64, sdxl_prompt, negative_prompt, adetailer_negative):
        """SDXL統合生成実行（統合プロンプト対応版・ポーズ指定モード対応・モデル切り替え対応）"""
        def sdxl_generation():
            generation_timer = ProcessTimer(self.logger)
            generation_timer.start("SDXL統合プロンプト生成")
            
            mode_text = "ポーズ指定モード" if self.pose_mode == "specification" else "ポーズ検出モード"
            self.logger.print_stage(f"🎨 SDXL統合プロンプト生成：Phase1+Phase2品質統合 + ControlNet-SDXL + ADetailer開始 ({mode_text})")
            
            sdxl_config = self.sdxl_config
            controlnet_config = self.controlnet_config
            adetailer_config = self.adetailer_config
            
            self.logger.print_status(f"- 解像度: {sdxl_config['width']}x{sdxl_config['height']}")
            self.logger.print_status(f"- 重点: 統合プロンプト（Phase1+Phase2品質統合）+ ControlNet-SDXL + ADetailer ({mode_text})")
            self.logger.print_status(f"- モデル: {gen_type.model_name}")  # 修正：gen_typeのmodel_nameを表示
            self.logger.print_status("- プロンプト: SDXL統合版（SD15品質強化要素統合済み）")
            
            if self.hand_foot_enhancement_enabled:
                self.logger.print_status("🔧 手足品質強化モード適用（統合版）")
            
            if self.fast_mode:
                self.logger.print_warning("⚡ 高速化モード適用中")
            
            if self.ultra_safe_mode:
                self.logger.print_status("🛡️ ウルトラセーフモード適用中")
            
            # ADetailer用の最終プロンプト構築（統合版）
            final_adetailer_prompt = self.face_prompts.get('adetailer_face', '')
            if self.hand_foot_enhancement_enabled:
                adetailer_hand_prompt = adetailer_config.get('hand_enhancement_prompt', '')
                if adetailer_hand_prompt:
                    final_adetailer_prompt = f"{final_adetailer_prompt}, {adetailer_hand_prompt}"
            
            final_adetailer_negative = adetailer_negative
            if self.hand_foot_enhancement_enabled:
                adetailer_hand_negative = adetailer_config.get('hand_enhancement_negative', '')
                if adetailer_hand_negative:
                    final_adetailer_negative = f"{adetailer_negative}, {adetailer_hand_negative}"
            
            # ペイロード構築（batch_size=1を強制）
            payload = {
                "prompt": sdxl_prompt,
                "negative_prompt": negative_prompt,
                "steps": sdxl_config['steps'],
                "sampler_name": sdxl_config['sampler_name'],
                "cfg_scale": sdxl_config['cfg_scale'],
                "width": sdxl_config['width'],
                "height": sdxl_config['height'],
                "batch_size": 1,  # 強制的に1に設定
                "override_settings": {
                    "sd_model_checkpoint": gen_type.model_name  # 修正：gen_typeのmodel_nameを使用
                },
                "alwayson_scripts": {}
            }
            
            # ControlNet設定（ポーズモードに応じて制御）
            if self.pose_mode == "detection" and input_b64:
                payload["alwayson_scripts"]["controlnet"] = {
                    "args": [
                        {
                            "input_image": input_b64,
                            "module": controlnet_config['openpose']['module'],
                            "model": controlnet_config['openpose']['model'],
                            "weight": controlnet_config['openpose']['weight'],
                            "resize_mode": controlnet_config['openpose']['resize_mode'],
                            "processor_res": controlnet_config['openpose']['processor_res'],
                            "threshold_a": controlnet_config['openpose']['threshold_a'],
                            "threshold_b": controlnet_config['openpose']['threshold_b'],
                            "guidance_start": controlnet_config['openpose']['guidance_start'],
                            "guidance_end": controlnet_config['openpose']['guidance_end'],
                            "pixel_perfect": controlnet_config['openpose']['pixel_perfect'],
                            "control_mode": controlnet_config['openpose']['control_mode'],
                            "enabled": controlnet_config['openpose']['enabled']
                        },
                        {
                            "input_image": input_b64,
                            "module": controlnet_config['depth']['module'],
                            "model": controlnet_config['depth']['model'],
                            "weight": controlnet_config['depth']['weight'],
                            "resize_mode": controlnet_config['depth']['resize_mode'],
                            "processor_res": controlnet_config['depth']['processor_res'],
                            "threshold_a": controlnet_config['depth']['threshold_a'],
                            "threshold_b": controlnet_config['depth']['threshold_b'],
                            "guidance_start": controlnet_config['depth']['guidance_start'],
                            "guidance_end": controlnet_config['depth']['guidance_end'],
                            "pixel_perfect": controlnet_config['depth']['pixel_perfect'],
                            "control_mode": controlnet_config['depth']['control_mode'],
                            "enabled": controlnet_config['depth']['enabled']
                        }
                    ]
                }
            else:
                # ポーズ指定モードの場合はControlNetを無効化
                self.logger.print_status("🎯 ポーズ指定モード: ControlNetを無効化します")
            
            # ADetailer設定（両モード共通）
            payload["alwayson_scripts"]["adetailer"] = {
                "args": [{
                    "ad_model": adetailer_config['model'],
                    "ad_prompt": final_adetailer_prompt,
                    "ad_negative_prompt": final_adetailer_negative,
                    "ad_confidence": adetailer_config['confidence'],
                    "ad_mask_blur": adetailer_config['mask_blur'],
                    "ad_denoising_strength": adetailer_config['denoising_strength'],
                    "ad_inpaint_only_masked": adetailer_config['inpaint_only_masked'],
                    "ad_inpaint_only_masked_padding": adetailer_config['inpaint_only_masked_padding'],
                    "ad_inpaint_width": adetailer_config['inpaint_width'],
                    "ad_inpaint_height": adetailer_config['inpaint_height'],
                    "ad_use_steps": adetailer_config['use_steps'],
                    "ad_steps": adetailer_config['steps'],
                    "ad_use_cfg_scale": adetailer_config['use_cfg_scale'],
                    "ad_cfg_scale": adetailer_config['cfg_scale'],
                    "is_api": []
                }]
            }
            
            try:
                api_start = time.time()
                generation_method = "txt2img" if self.pose_mode == "specification" else "txt2img with ControlNet"
                self.logger.print_status(f"🎨 SDXL統合プロンプト生成中（{generation_method}）...")
                
                response = requests.post(
                    f"{self.config['stable_diffusion']['api_url']}/sdapi/v1/txt2img",
                    json=payload,
                    timeout=self.config['stable_diffusion']['timeout'],
                    verify=self.config['stable_diffusion']['verify_ssl']
                )
                
                api_time = time.time() - api_start
                generation_timer.mark_phase(f"SDXL統合API呼び出し ({ProcessTimer.format_duration(api_time)})")
                
                response.raise_for_status()
                result = response.json()
                
                if 'error' in result:
                    raise HybridGenerationError(f"SDXL統合APIエラー: {result['error']}")
                
                if 'images' not in result or not result['images']:
                    raise HybridGenerationError("SDXL統合生成で画像生成に失敗")
                
                # SDXL統合画像を保存
                save_start = time.time()
                sdxl_b64 = result['images'][0]
                sdxl_path = os.path.join(self.temp_dir, f"sdxl_unified_{int(time.time())}.png")
                
                with open(sdxl_path, 'wb') as f:
                    f.write(base64.b64decode(sdxl_b64))
                
                save_time = time.time() - save_start
                generation_timer.mark_phase(f"画像保存 ({ProcessTimer.format_duration(save_time)})")
                
                total_time = generation_timer.end_and_report()
                
                mode_text = "ポーズ指定モード" if self.pose_mode == "specification" else "ポーズ検出モード"
                self.logger.print_success(f"🎨 SDXL統合プロンプト生成完了: Phase1+Phase2品質統合 + ControlNet + ADetailer完了 ({mode_text})")
                
                return sdxl_path, result
            
            except requests.RequestException as e:
                raise HybridGenerationError(f"SDXL統合API呼び出しエラー: {e}")
            except Exception as e:
                raise HybridGenerationError(f"SDXL統合生成実行エラー: {e}")
        
        # ウルトラメモリセーフティ付きでSDXL統合生成実行
        return self.execute_with_ultra_memory_safety(sdxl_generation, "SDXL統合プロンプト生成")
    
    def apply_final_enhancement(self, image_path):
        """最終仕上げ処理（シェルスクリプト完全再現）"""
        self.logger.print_status("最終仕上げ処理中（顔品質特化）...")
        
        # ImageMagickのconvertコマンドが利用可能かチェック
        if shutil.which('convert'):
            try:
                # シェルスクリプトと同じconvertコマンドを実行
                cmd = [
                    'convert', image_path,
                    '-unsharp', '1.2x1.0+1.0+0.02',
                    '-contrast-stretch', '0.03%x0.03%',
                    '-modulate', '102,110,100',
                    '-define', 'png:compression-level=0',
                    image_path
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                
                if result.returncode == 0:
                    self.logger.print_success("✅ ImageMagick最終仕上げ処理完了")
                    return
                else:
                    self.logger.print_warning(f"⚠️ ImageMagick処理エラー: {result.stderr}")
            
            except subprocess.TimeoutExpired:
                self.logger.print_warning("⚠️ ImageMagick処理タイムアウト")
            except Exception as e:
                self.logger.print_warning(f"⚠️ ImageMagick処理エラー: {e}")
        
        # PIL代替処理
        self.apply_pil_enhancement(image_path)
    
    def apply_pil_enhancement(self, image_path):
        """PIL代替処理（ImageMagick不使用時）"""
        try:
            image = Image.open(image_path)
            
            # アンシャープマスク: -unsharp 1.2x1.0+1.0+0.02 相当
            image = image.filter(ImageFilter.UnsharpMask(
                radius=1.2, percent=100, threshold=1))
            
            # コントラスト調整: -contrast-stretch 0.03%x0.03% 相当
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(1.05)
            
            # 色彩調整: -modulate 102,110,100 相当
            # 明度102%
            brightness = ImageEnhance.Brightness(image)
            image = brightness.enhance(1.02)
            
            # 彩度110%
            color = ImageEnhance.Color(image)
            image = color.enhance(1.10)
            
            # 高品質PNG保存
            image.save(image_path, "PNG", optimize=True, compress_level=0)
            
            self.logger.print_success("✅ PIL代替仕上げ処理完了")
        
        except Exception as e:
            self.logger.print_error(f"❌ PIL仕上げ処理エラー: {e}")
    
    def cleanup_temp_files(self):
        """一時ファイル整理"""
        try:
            cleanup_config = self.config.get('temp_files', {})
            cleanup_on_success = cleanup_config.get('cleanup_on_success', True)
            
            if cleanup_on_success:
                import glob
                temp_files = glob.glob(os.path.join(self.temp_dir, "*"))
                for temp_file in temp_files:
                    if os.path.isfile(temp_file):
                        os.remove(temp_file)
                self.logger.print_status("🧹 一時ファイル整理完了")
        
        except Exception as e:
            self.logger.print_warning(f"⚠️ 一時ファイル整理エラー: {e}")
    def generate_hybrid_image(self, gen_type, count=1):
        """SDXL統合画像生成（モデル切り替え対応・完全版）"""
        overall_timer = ProcessTimer(self.logger)
        overall_timer.start(f"SDXL統合画像生成バッチ（{count}枚）")
        
        # モデル切り替え実行（新規追加）
        try:
            self.ensure_model_for_generation_type(gen_type)
        except HybridGenerationError as e:
            self.logger.print_error(f"❌ モデル切り替え失敗: {e}")
            return 0
        
        success_count = 0
        max_retries = self.error_handling_config.get('max_retries', 5)
        
        pose_text = getattr(self, 'pose_mode', 'detection')
        self.logger.print_stage(f"=== {gen_type.name} SDXL統合画像生成開始 ({pose_text}モード・モデル切り替え対応) ===")
        
        for i in range(count):
            image_timer = ProcessTimer(self.logger)
            image_timer.start(f"画像{i+1}/{count}")
            
            retry_count = 0
            
            while retry_count <= max_retries:
                try:
                    self.logger.print_stage(f"🎨 画像{i+1}/{count}生成開始 (モデル: {gen_type.model_name})")
                    
                    # 入力画像選択と前処理
                    input_image_path = self.select_random_input_image()
                    resized_image_path = self.preprocess_input_image(input_image_path)
                    input_b64 = self.encode_image_to_base64(resized_image_path)
                    
                    # プロンプト構築
                    sdxl_prompt, negative_prompt, adetailer_negative = self.build_prompts(gen_type, mode="auto")
                    
                    # SDXL統合生成実行
                    generation_path, generation_response = self.execute_generation(
                        gen_type, input_b64, sdxl_prompt, negative_prompt, adetailer_negative
                    )
                    
                    # 最終仕上げ処理
                    self.apply_final_enhancement(generation_path)
                    
                    # ファイルサイズ確認
                    final_size = os.path.getsize(generation_path)
                    
                    completion_text = f"SDXL統合"
                    if self.fast_mode:
                        completion_text += "高速化"
                    completion_text += f" + ADetailer統合処理完成（Bedrock対応・ウルトラセーフ・{pose_text}モード・モデル切り替え対応）"
                    
                    self.logger.print_success(f"{completion_text}: {final_size} bytes")
                    
                    # 保存処理（ローカルモードかAWSモードかで分岐）
                    save_start = time.time()
                    if self.local_mode:
                        save_success = self.save_image_locally(generation_path, i, generation_response, gen_type, input_image_path)
                    else:
                        save_success = self.save_image_to_s3_and_dynamodb(generation_path, i, generation_response, gen_type, input_image_path)
                    
                    save_time = time.time() - save_start
                    image_timer.mark_phase(f"保存処理 ({ProcessTimer.format_duration(save_time)})")
                    
                    if save_success:
                        success_count += 1
                        image_timer.end_and_report()
                        break
                    else:
                        raise Exception("保存処理に失敗")
                
                except Exception as e:
                    retry_count += 1
                    self.logger.print_error(f"❌ SDXL統合生成エラー (試行{retry_count}): {e}")
                    
                    # メモリエラーの場合は特別処理
                    if "CUDA out of memory" in str(e):
                        self.logger.print_warning("🧠 メモリ不足エラーを検出しました")
                        self.perform_aggressive_memory_cleanup()
                        
                        if self.auto_adjustment_enabled:
                            adjusted = self.escalate_memory_adjustment()
                            if adjusted:
                                self.logger.print_warning("📉 設定を段階的に調整しました")
                    
                    if retry_count > max_retries:
                        self.logger.print_error(f"❌ 最大リトライ回数({max_retries})に到達。画像{i+1}をスキップします")
                        break
                    
                    # リトライ間隔（メモリエラー時は長時間）
                    retry_delay = self.memory_recovery_delay if "CUDA out of memory" in str(e) else self.error_handling_config.get('retry_delay', 5)
                    self.logger.print_status(f"⏳ {retry_delay}秒後にリトライします...")
                    time.sleep(retry_delay)
            
            # 画像間の処理間隔とメモリクリーンアップ
            if i < count - 1:
                # API間隔制御
                rate_limit = max(10, self.config.get('performance', {}).get('api_rate_limit', 10))
                self.logger.print_status(f"⏳ API間隔制御: {rate_limit}秒待機")
                time.sleep(rate_limit)
                
                # 強制的な積極的メモリクリーンアップ
                if self.memory_monitoring_enabled:
                    self.logger.print_status("🧠 画像間強制メモリクリーンアップ実行中...")
                    self.perform_aggressive_memory_cleanup()
            
            # 一時ファイル削除
            if not self.local_execution_config.get('keep_temp_files', False):
                self.cleanup_temp_files()
            else:
                self.logger.print_status("📁 一時ファイル保持（デバッグ用）")
        
        # 全体の処理時間表示
        total_time = overall_timer.end_and_report(success_count)
        
        self.logger.print_stage(f"=== {gen_type.name} SDXL統合画像生成完了 ===")
        bedrock_text = "Bedrock対応" if self.bedrock_enabled else "Bedrock無効"
        pose_text = getattr(self, 'pose_mode', 'detection')
        self.logger.print_status(f"📊 成功: {success_count}/{count}枚 (SDXL統合・{bedrock_text}・{pose_text}モード・モデル切り替え対応)")
        
        return success_count
    
    def save_image_locally(self, final_image_path, image_index, generation_response, generation_type, original_input_path):
        """ローカル保存専用メソッド（モデル切り替え対応）"""
        # 画像ID生成
        now = datetime.now()
        formatted_time = now.strftime("%Y%m%d%H%M%S")
        fast_suffix = "_fast" if self.fast_mode else ""
        ultra_suffix = "_ultra_safe"
        bedrock_suffix = "_bedrock" if self.bedrock_enabled else ""
        pose_suffix = f"_{self.pose_mode}" if hasattr(self, 'pose_mode') and self.pose_mode else ""
        
        model_suffix = f"_{generation_type.name}_{generation_type.model_name.replace('.safetensors', '').replace(' [', '_').replace(']', '')}"  # 修正
        image_id = f"local_sdxl{model_suffix}{fast_suffix}{ultra_suffix}{bedrock_suffix}{pose_suffix}_{formatted_time}_{image_index:03d}"

        # 保存先決定
        if self.local_execution_config.get('create_subdirs', True):
            save_dir = os.path.join(self.local_output_dir, generation_type.name)
        else:
            save_dir = self.local_output_dir
        
        # 最終画像保存
        final_save_path = os.path.join(save_dir, f"{image_id}.png")
        shutil.copy2(final_image_path, final_save_path)
        
        file_size = os.path.getsize(final_save_path)
        self.logger.print_success(f"📁 ローカル保存完了: {final_save_path} ({file_size} bytes)")
        
        # メタデータ保存
        if self.local_execution_config.get('save_metadata', True):
            metadata = self.prepare_local_metadata(image_index, generation_response, generation_type, original_input_path, image_id)
            metadata_path = os.path.join(save_dir, f"{image_id}_metadata.json")
            
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            self.logger.print_status(f"📄 メタデータ保存: {metadata_path}")
        
        return True
    
    def prepare_local_metadata(self, image_index, generation_response, generation_type, original_input_path, image_id):
        """ローカル保存用メタデータ準備（モデル切り替え対応）"""
        now = datetime.now()
        
        # パラメータ取得
        generation_params = generation_response.get('parameters', {})
        
        metadata = {
            "image_id": image_id,
            "generation_mode": "local_test_sdxl_unified_ultra_safe_bedrock_pose_mode_model_switching",
            "created_at": now.isoformat(),
            "genre": generation_type.name,
            "model_name": generation_type.model_name,  # 追加
            "input_image": os.path.basename(original_input_path) if original_input_path else "pose_specification_mode",
            "pose_mode": getattr(self, 'pose_mode', 'detection'),
            "fast_mode_enabled": self.fast_mode,
            "secure_random_enabled": True,
            "ultra_memory_safe_enabled": self.ultra_safe_mode,
            "bedrock_enabled": self.bedrock_enabled,
            "fallback_level": getattr(self, 'current_fallback_level', -1),
            "memory_management": {
                "enabled": self.memory_monitoring_enabled,
                "threshold_percent": self.memory_threshold,
                "auto_adjustment": self.auto_adjustment_enabled
            },
            "sdxl_unified_generation": {
                "model": generation_type.model_name,  # 修正
                "prompt": generation_params.get('prompt', ''),
                "negative_prompt": generation_params.get('negative_prompt', ''),
                "steps": self.sdxl_config['steps'],
                "cfg_scale": self.sdxl_config['cfg_scale'],
                "width": self.sdxl_config['width'],
                "height": self.sdxl_config['height']
            },
            "controlnet": {
                "enabled": self.pose_mode == "detection",
                "openpose": {
                    "enabled": self.controlnet_config['openpose']['enabled'],
                    "weight": self.controlnet_config['openpose']['weight']
                },
                "depth": {
                    "enabled": self.controlnet_config['depth']['enabled'],
                    "weight": self.controlnet_config['depth']['weight']
                }
            },
            "adetailer": {
                "enabled": self.adetailer_config['enabled']
            }
        }
        
        return metadata
    
    def save_image_to_s3_and_dynamodb(self, final_image_path, image_index, generation_response, generation_type, original_input_path):
        """画像をS3とDynamoDBに保存（SDXL統合対応・Bedrock対応・ウルトラセーフ対応・ポーズ指定モード対応・モデル切り替え対応）"""
        
        image_id, dynamodb_item = self.prepare_metadata_and_dynamodb_item(
            image_index, generation_response, generation_type, original_input_path)

        s3_key = dynamodb_item['s3Key']

        try:
            # S3アップロード
            self.logger.print_status(f"📤 S3アップロード中... s3://{self.config['aws']['s3_bucket']}/{s3_key}")
            with open(final_image_path, 'rb') as f:
                self.s3_client.upload_fileobj(
                    f,
                    self.config['aws']['s3_bucket'],
                    s3_key,
                    ExtraArgs={'ContentType': 'image/png'}
                )

            self.logger.print_success(f"✅ S3アップロード完了: s3://{self.config['aws']['s3_bucket']}/{s3_key}")

            # DynamoDB保存
            try:
                self.logger.print_status(f"📝 DynamoDB保存中... imageId: {image_id}")
                self.dynamodb_table.put_item(Item=dynamodb_item)
                self.logger.print_success(f"✅ DynamoDB保存完了: imageId: {image_id}")

                # Bedrockコメントの保存状況をログ出力
                if dynamodb_item.get('preGeneratedComments'):
                    self.logger.print_success(f"🤖 Bedrockコメント保存完了: {len(dynamodb_item['preGeneratedComments'])}件")
                else:
                    self.logger.print_warning("⚠️ Bedrockコメント生成なし（ローカルモードまたはエラー）")

            except ClientError as ddbe:
                self.logger.print_error(f"❌ DynamoDB保存エラー (imageId: {image_id}): {ddbe}")
                self.logger.print_status("🧹 DynamoDB保存失敗のため、S3からファイル削除中...")
                # DynamoDB保存失敗時はS3からも削除
                try:
                    self.s3_client.delete_object(Bucket=self.config['aws']['s3_bucket'], Key=s3_key)
                    self.logger.print_status(f"🗑️ S3ファイル削除完了: s3://{self.config['aws']['s3_bucket']}/{s3_key}")
                except ClientError as s3dele:
                    self.logger.print_error(f"❌ S3ファイル削除エラー: {s3_key} - {s3dele}")
                self.logger.print_error("!!! DynamoDB保存に失敗したため、S3ファイルも削除しました")
                return False

        except ClientError as s3e:
            self.logger.print_error(f"❌ S3アップロードエラー: {s3_key} - {s3e}")
            return False
        except Exception as e:
            self.logger.print_error(f"❌ S3保存エラー (imageId: {image_id}): {e}")
            return False

        return True
    
    def prepare_metadata_and_dynamodb_item(self, image_index, generation_response, generation_type, original_input_path):
        """メタデータとDynamoDBアイテムを準備（SDXL統合対応・Bedrock対応・ウルトラセーフ対応・ポーズ指定モード対応・モデル切り替え対応）"""
        
        # 画像ID生成
        now = datetime.now()
        formatted_time = now.strftime("%Y%m%d%H%M%S")
        fast_suffix = "_fast" if self.fast_mode else ""
        ultra_suffix = "_ultra_safe"
        bedrock_suffix = "_bedrock" if self.bedrock_enabled else ""
        pose_suffix = f"_{self.pose_mode}" if hasattr(self, 'pose_mode') and self.pose_mode else ""
        image_id = f"sdxl_{generation_type.name}{fast_suffix}{ultra_suffix}{bedrock_suffix}{pose_suffix}_{formatted_time}_{image_index:03d}"

        created_at_string = formatted_time

        # パラメータ取得
        generation_params = generation_response.get('parameters', {})

        # ベースパラメータ
        base_params = {
            "generation_method": "sdxl_unified_ultra_safe_bedrock_pose_mode_model_switching",
            "input_image": os.path.basename(original_input_path) if original_input_path else "pose_specification_mode",
            "pose_mode": getattr(self, 'pose_mode', 'detection'),
            "model": generation_type.model_name,  # モデル名を追加
            "fast_mode_enabled": str(self.fast_mode),
            "secure_random_enabled": "true",
            "ultra_memory_safe_enabled": str(self.ultra_safe_mode),
            "bedrock_enabled": str(self.bedrock_enabled),
            "fallback_level": str(getattr(self, 'current_fallback_level', -1))
        }

        # SDXL統合生成パラメータ
        sdxl_structured = {
            "prompt": generation_params.get('prompt', ''),
            "negative_prompt": generation_params.get('negative_prompt', ''),
            "steps": str(self.sdxl_config['steps']),
            "cfg_scale": str(self.sdxl_config['cfg_scale']),
            "sampler": self.sdxl_config['sampler_name'],
            "width": str(self.sdxl_config['width']),
            "height": str(self.sdxl_config['height'])
        }

        # ControlNetパラメータ（ポーズモードに応じて調整）
        controlnet_structured = {
            "enabled": str(self.pose_mode == "detection"),
            "openpose": {
                "enabled": str(self.controlnet_config['openpose']['enabled'] and self.pose_mode == "detection"),
                "weight": str(self.controlnet_config['openpose']['weight']),
                "model": self.controlnet_config['openpose']['model']
            },
            "depth": {
                "enabled": str(self.controlnet_config['depth']['enabled'] and self.pose_mode == "detection"),
                "weight": str(self.controlnet_config['depth']['weight']),
                "model": self.controlnet_config['depth']['model']
            }
        }

        # ADetailerパラメータ
        adetailer_structured = {
            "enabled": str(self.adetailer_config['enabled']),
            "model": self.adetailer_config['model'],
            "denoising_strength": str(self.adetailer_config['denoising_strength'])
        }

        # S3キーとDynamoDBアイテム
        s3_key = f"image-pool/{generation_type.name}/{image_id}.png"

        # Bedrock用画像メタデータ準備
        image_metadata = {
            'genre': generation_type.name,
            'style': 'general',
            'imageId': image_id,
            'prompt': generation_params.get('prompt', ''),
            'pose_mode': getattr(self, 'pose_mode', 'detection'),
            'model_name': generation_type.model_name  # モデル名を追加
        }

        # Bedrockコメント生成（エラーハンドリング強化版）
        pre_generated_comments = self.generate_all_timeslot_comments(image_metadata)
        comment_generated_at = datetime.now(JST).isoformat() if pre_generated_comments else ""

        # Ver9と同じDynamoDB構造を維持
        dynamodb_item = {
            "imageId": image_id,
            "s3Bucket": self.config['aws']['s3_bucket'],
            "s3Key": s3_key,
            "genre": generation_type.name,
            "imageState": "unprocessed",
            "postingStage": "notposted",
            "createdAt": created_at_string,
            "suitableTimeSlots": self.default_suitable_slots,
            "preGeneratedComments": pre_generated_comments,
            "commentGeneratedAt": comment_generated_at,
            "sdParams": {
                "base": base_params,
                "sdxl_unified": sdxl_structured,
                "controlnet": controlnet_structured,
                "adetailer": adetailer_structured
            },
            # X投稿管理用フィールド
            "scheduledPostTime": "",
            "actualPostTime": created_at_string,
            "tweetId": "",
            "postingAttempts": 0,
            "lastErrorMessage": "",
            "movedToArchive": False
        }

        return image_id, dynamodb_item

    
    def generate_hybrid_batch(self, genre, count=1):
        """指定ジャンルのSDXL統合画像をバッチ生成（モデル切り替え対応）"""
        # 該当ジャンルの生成タイプを探す
        gen_type = None
        for gt in self.generation_types:
            if gt.name == genre:
                gen_type = gt
                break
        
        if not gen_type:
            self.logger.print_error(f"❌ ジャンル '{genre}' が見つかりません")
            available_genres = [gt.name for gt in self.generation_types]
            self.logger.print_status(f"利用可能なジャンル: {available_genres}")
            return 0
        
        return self.generate_hybrid_image(gen_type, count)
    
    def generate_daily_hybrid_batch(self):
        """1日分のSDXL統合画像をバッチ生成（モデル切り替え対応）"""
        batch_timer = ProcessTimer(self.logger)
        batch_timer.start("1日分SDXL統合画像生成バッチ（モデル切り替え対応）")
        
        if self.local_mode:
            self.logger.print_warning("⚠️ ローカルモードでは日次バッチ生成は推奨されません")
            confirm = input("続行しますか？ (y/N): ").strip().lower()
            if confirm != 'y':
                self.logger.print_status("バッチ生成をキャンセルしました")
                return
        
        batch_size = self.config['generation']['batch_size']
        genres = self.config['generation']['genres']
        
        mode_text = "ローカルテスト" if self.local_mode else "通常"
        fast_text = "高速化" if self.fast_mode else "通常品質"
        bedrock_text = "Bedrock対応" if self.bedrock_enabled else "Bedrock無効"
        pose_text = getattr(self, 'pose_mode', 'detection')
        
        self.logger.print_stage(f"=== 1日分SDXL統合画像生成バッチ開始 ({mode_text}モード・{fast_text}・{bedrock_text}・{pose_text}モード・モデル切り替え対応) ===")
        self.logger.print_status(f"バッチサイズ: {batch_size}, ジャンル: {genres}")
        self.logger.print_status("🔒 セキュアランダム関数使用")
        self.logger.print_status("🛡️ ウルトラメモリ管理システム有効")
        self.logger.print_status("🔄 モデル自動切り替え機能有効")
        
        total_success = 0
        
        # バッチ処理開始前の強制メモリクリーンアップ
        if self.memory_monitoring_enabled:
            self.logger.print_status("🛡️ バッチ開始前ウルトラ安全チェック")
            self.check_memory_usage(force_cleanup=True)
        
        # ジャンル分散設定に基づく枚数分散
        genre_distribution = self.config['generation'].get('genre_distribution', {})
        
        for genre_index, genre in enumerate(genres):
            genre_start = time.time()
            
            if genre_distribution:
                # 分散比率に基づく枚数計算
                ratio = genre_distribution.get(genre, 1.0 / len(genres))
                images_per_genre = max(1, int(batch_size * ratio))
            else:
                # 均等分散
                images_per_genre = batch_size // len(genres)
                if genre == genres[0]:  # 最初のジャンルに余りを追加
                    images_per_genre += batch_size % len(genres)
            
            self.logger.print_status(f"📋 {genre}: {images_per_genre}枚生成予定")
            
            # ジャンル開始前の強制メモリクリーンアップ
            if self.memory_monitoring_enabled:
                self.logger.print_status("🛡️ ジャンル開始前ウルトラ安全チェック")
                self.check_memory_usage(force_cleanup=True)
            
            success = self.generate_hybrid_batch(genre, images_per_genre)
            total_success += success
            
            genre_time = time.time() - genre_start
            batch_timer.mark_phase(f"{genre}ジャンル ({ProcessTimer.format_duration(genre_time)})")
            
            # ジャンル間の長時間休憩とメモリクリーンアップ
            if genre_index < len(genres) - 1:
                self.logger.print_status("🛡️ ジャンル間長時間休憩とメモリクリーンアップ実行中...")
                self.perform_aggressive_memory_cleanup()
                time.sleep(60)  # 60秒の長時間休憩
        
        # バッチ全体の処理時間表示
        total_time = batch_timer.end_and_report(total_success)
        
        self.logger.print_stage(f"=== 1日分SDXL統合画像生成バッチ完了 ({mode_text}モード・{fast_text}・{bedrock_text}・{pose_text}モード・モデル切り替え対応) ===")
        self.logger.print_status(f"📊 総合成功数: {total_success}枚")
        
        if self.local_mode:
            self.logger.print_status(f"🔍 生成結果確認: {self.local_output_dir}")
        
        # 最終強制メモリクリーンアップ
        if self.memory_monitoring_enabled:
            self.logger.print_status("🛡️ 最終ウルトラメモリクリーンアップ実行中...")
            self.perform_aggressive_memory_cleanup()

def main():
    """メイン関数（モデル切り替え対応）"""
    try:
        print("🚀 美少女画像SDXL統合生成ツール Ver7.0 プロンプト統合対応版 + モデル切り替え機能 開始")
        print("Ctrl+Cで中断できます")
        
        generator = HybridBijoImageGeneratorV7()
        
        # ポーズモード設定を初期化
        generator.setup_pose_mode()
        
        print("\n📋 Ver7.0 SDXL統合プロンプト対応版 + モデル切り替え機能:")
        print("✨ SDXL統合生成: Phase1削除、SDXL直接生成")
        print("✨ プロンプト統合: Phase1+Phase2品質要素統合")
        print("✨ 高速化: 25分 → 8-10分/枚")
        print("✨ 品質維持: ControlNet-SDXL + ADetailer統合")
        print("🔄 v6全機能保持: バッチ・ローカル・Bedrock対応")
        print("🔒 セキュアランダム: 暗号学的に安全な乱数生成")
        print("🛡️ ウルトラメモリ管理: 段階的解像度調整と積極的クリーンアップ")
        print("🧠 メモリ監視: リアルタイムVRAM使用量監視")
        print("📉 自動調整: メモリ不足時の自動設定調整")
        print("🤖 Bedrock対応: 時間帯別コメント自動生成（AWS連携時）")
        print("📝 プロンプト統合: Phase1+Phase2品質要素を完全統合")
        print("🎯 ランダム性強化: 重複回避・履歴永続化による真のバリエーション実現")
        print("🔧 LoRA対応: generation_types.yamlでのlora_settings対応")
        print("🎭 ポーズ指定モード: プロンプトベースポーズ指定対応")
        print("🔄 モデル自動切り替え: generation_types.yamlのmodel_name最優先")
        
        if generator.local_mode:
            print("🔧 現在：ローカルテストモード（S3/DynamoDB保存なし）")
            if generator.bedrock_enabled:
                print("⚠️ ローカルモードのため Bedrock機能は無効化されています")
        else:
            print("🔧 現在：通常モード（S3/DynamoDB保存あり）")
            print(f"🤖 Bedrock機能: {'有効' if generator.bedrock_enabled else '無効'}")
        
        if generator.fast_mode:
            print(f"⚡ 高速化モード有効: 軽量化設定")
        else:
            print("🔧 通常品質モード")
        
        print(f"🛡️ ウルトラセーフモード: {'有効' if generator.ultra_safe_mode else '無効'}")
        print(f"🧠 メモリ管理: {'有効' if generator.memory_monitoring_enabled else '無効'}")
        print(f"⚙️ 自動調整: {'有効' if generator.auto_adjustment_enabled else '無効'}")
        
        # インタラクティブモード
        while True:
            print("\n" + "="*80)
            print("📋 メインメニュー（SDXL統合プロンプト対応・Bedrock対応・Ultra Memory Safe・ポーズ指定モード・モデル切り替え対応版）")
            print("="*80)
            print("1. 単発SDXL統合生成（モデル自動切り替え）")
            print("2. 日次SDXL統合バッチ生成（完全安全モード・モデル自動切り替え）")
            if not generator.local_mode:
                print("3. ローカルテストモードに切り替え")
            else:
                print("3. 通常モードに切り替え")
            print("4. 終了")
            print("="*80)
            
            try:
                choice = input("選択 (1-4): ").strip()
                
                if choice == '1':
                    # ポーズモード選択
                    generator.select_pose_mode()
                    
                    # ジャンル選択
                    available_genres = [gt.name for gt in generator.generation_types]
                    print(f"\n利用可能なジャンル: {available_genres}")
                    print("各ジャンルのモデル:")
                    for gt in generator.generation_types:
                        print(f"  {gt.name}: {gt.model_name}")
                    
                    genre = input("ジャンル: ").strip().lower()
                    if genre not in available_genres:
                        print("❌ 無効なジャンルです")
                        continue
                    
                    count = int(input("枚数: "))
                    if count <= 0:
                        print("❌ 無効な枚数です")
                        continue
                    
                    generator.generate_hybrid_batch(genre, count)
                
                elif choice == '2':
                    # ポーズモード選択
                    generator.select_pose_mode()
                    
                    print("\n⚠️ 日次SDXL統合バッチ生成（Bedrock対応・ウルトラセーフモード・ポーズ指定モード・モデル自動切り替え対応）")
                    print("このモードは最も安全で安定した設定で動作しますが、時間がかかります。")
                    print("ジャンルごとに適切なモデルに自動切り替えされます。")
                    pose_text = generator.pose_mode if hasattr(generator, 'pose_mode') else 'detection'
                    print(f"選択されたポーズモード: {pose_text}")
                    
                    confirm = input("続行しますか？ (y/N): ").strip().lower()
                    if confirm == 'y':
                        generator.generate_daily_hybrid_batch()
                
                elif choice == '3':
                    # モード切り替え
                    if generator.local_mode:
                        print("⚠️ 通常モードに切り替えるには設定ファイルのlocal_execution.enabledをfalseに変更してツールを再起動してください")
                    else:
                        print("⚠️ ローカルテストモードに切り替えるには設定ファイルのlocal_execution.enabledをtrueに変更してツールを再起動してください")
                
                elif choice == '4':
                    break
                
                else:
                    print("❌ 無効な選択です")
            
            except ValueError:
                print("❌ 無効な入力です")
            except KeyboardInterrupt:
                print("\n🛑 操作が中断されました")
                break
    
    except KeyboardInterrupt:
        print("\n🛑 ユーザーによる中断")
    except Exception as e:
        print(f"❌ エラー: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("👋 プログラム終了")

if __name__ == "__main__":
    main()
