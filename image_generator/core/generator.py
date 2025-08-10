#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hybrid Bijo Image Generator v7.0 - コア画像生成クラス（11スロット対応版）
修正版: bedrock_manager属性エラー対応 + Bedrock呼び出し修正
"""

import os
import time
import base64
import subprocess
import shutil
import requests
import json
import yaml
import torch
import gc
import urllib3
from io import BytesIO
from pathlib import Path
from collections import deque, Counter
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from PIL import Image, ImageFilter, ImageEnhance
from typing import TYPE_CHECKING

from common.logger import ColorLogger
from common.timer import ProcessTimer
from common.types import GenerationType, HybridGenerationError
from common.config_manager import ConfigManager
from common.aws_client import AWSClientManager

# 相対インポートの修正
from ..prompt.builder import PromptBuilder
from ..prompt.lora_manager import LoRAManager
from ..prompt.pose_manager import PoseManager
from ..randomization.secure_random import SecureRandom, EnhancedSecureRandom
from ..randomization.image_pool import InputImagePool
from ..randomization.element_generator import RandomElementGenerator
from ..processing.image_processor import ImageProcessor
from ..processing.generator_engine import GeneratorEngine
from ..processing.saver import ImageSaver
from ..memory.manager import MemoryManager
from ..aws.bedrock_manager import BedrockManager
from ..aws.metadata import MetadataManager

if TYPE_CHECKING:
    from .model_manager import ModelManager

# SSL 警告無視
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# JST タイムゾーン
JST = timezone(timedelta(hours=9))


class HybridBijoImageGeneratorV7:
    """美少女画像SDXL統合生成クラス v7.0（11スロット対応版）"""

    def __init__(self):
        self.logger = ColorLogger()
        self.logger.print_stage("🚀 SDXL統合生成ツール Ver7.0 初期化中...（11スロット対応版）")

        # 設定読み込み
        cfg_mgr = ConfigManager(self.logger)
        self.config = cfg_mgr.load_config(['config/config_v10.yaml'])

        # ===============================================
        # bedrock_manager属性を最初に初期化（修正箇所）
        # ===============================================
        self.bedrock_manager = None

        # デバッグ用ログ追加
        self.logger.print_status(f"🔍 DEBUG: local_execution.enabled = {self.config.get('local_execution', {}).get('enabled', 'NOT_SET')}")
        self.logger.print_status(f"🔍 DEBUG: bedrock_features.enabled = {self.config.get('bedrock_features', {}).get('enabled', 'NOT_SET')}")

        # ===============================================
        # 11スロット対応機能追加（既存機能を維持）
        # ===============================================
        try:
            # 投稿スケジュール管理インスタンス取得
            self.posting_schedule_mgr = cfg_mgr.get_posting_schedule_manager()
            # 全スロット名を取得
            self.all_time_slots = cfg_mgr.get_all_time_slots()
            self.default_suitable_slots = cfg_mgr.get_default_suitable_slots()
            self.logger.print_success(f"✅ 11スロット対応機能初期化完了 - 総スロット数: {len(self.all_time_slots)}")
            self.logger.print_status(f"📋 利用可能スロット: {', '.join(self.all_time_slots)}")
        except Exception as e:
            # フォールバック: 11スロット機能が利用できない場合でも既存機能は動作
            self.logger.print_warning(f"⚠️ 11スロット機能初期化スキップ（既存機能は利用可能）: {e}")
            self.posting_schedule_mgr = None
            self.all_time_slots = []
            self.default_suitable_slots = ['morning', 'lunch', 'evening', 'night', 'general']

        # AWS クライアント初期化（既存機能維持）
        try:
            self.aws = AWSClientManager(self.logger, self.config)
            self.aws.setup_clients(include_lambda=True)
            self.logger.print_status(f"🔍 DEBUG: AWS Lambda client = {hasattr(self.aws, 'lambda_client') if self.aws else False}")
        except Exception as e:
            self.logger.print_warning(f"⚠️ AWS初期化スキップ: {e}")
            self.aws = None

        # メモリ管理（既存機能維持）
        self.memory_manager = MemoryManager(self.config)

        # プロンプト関連設定読み込み（既存機能維持）
        try:
            prompts_data = cfg_mgr.load_yaml(self.config['prompt_files']['prompts'])
            random_data = cfg_mgr.load_yaml(self.config['prompt_files']['random_elements'])
            gen_types_data = cfg_mgr.load_yaml(self.config['prompt_files']['generation_types'])
        except Exception as e:
            self.logger.print_error(f"❌ 設定ファイル読み込みエラー: {e}")
            prompts_data = {}
            random_data = {}
            gen_types_data = {'generation_types': []}

        # 生成タイプ設定（既存機能維持）
        self.generation_types = []
        for t in gen_types_data.get('generation_types', []):
            if t.get('name') in ['teen', 'jk']:
                t['age_range'] = [18, 20]
            gt = GenerationType(
                name=t.get('name', 'default'),
                model_name=t.get('model_name', 'default.safetensors'),
                prompt=t.get('prompt', ''),
                negative_prompt=t.get('negative_prompt', ''),
                random_elements=t.get('random_elements', []),
                age_range=t.get('age_range', [18, 24]),
                lora_settings=t.get('lora_settings', [])
            )
            gt.fast_mode = self.config.get('fast_mode', {}).get('enabled', False)
            gt.bedrock_enabled = self.config.get('bedrock_features', {}).get('enabled', False)
            gt.ultra_safe_mode = self.config.get('memory_management', {}).get('enabled', False)
            self.generation_types.append(gt)

        if not self.generation_types:
            default_gt = GenerationType(
                name='default',
                model_name='default.safetensors',
                prompt='beautiful Japanese woman',
                negative_prompt='low quality',
                random_elements=[],
                age_range=[18, 24],
                lora_settings=[]
            )
            self.generation_types.append(default_gt)

        # 各種マネージャ初期化（既存機能維持）
        self.prompt_builder = PromptBuilder(self.config, prompts_data, gen_types_data)
        self.lora_manager = LoRAManager()
        self.pose_manager = PoseManager(random_data.get('specific_random_elements', {}))
        self.secure_random = SecureRandom()
        self.enhanced_random = EnhancedSecureRandom()

        # 入力プール & 要素（既存機能維持）
        self.input_pool = None
        self.elem_generator = None

        # 一時ディレクトリ（既存機能維持）
        self.temp_dir = self.config.get('temp_files', {}).get('directory', '/tmp/sdprocess')
        os.makedirs(self.temp_dir, exist_ok=True)

        # ===============================================
        # BedrockManager初期化（修正箇所）
        # ===============================================
        try:
            if (self.config.get('bedrock_features', {}).get('enabled', False) and
                self.aws and hasattr(self.aws, 'lambda_client')):
                
                self.bedrock_manager = BedrockManager(
                    self.aws.lambda_client,
                    self.logger,
                    self.config,
                    cfg_mgr  # ConfigManagerインスタンスを渡す
                )
                self.logger.print_success("✅ BedrockManager初期化完了")
            else:
                self.logger.print_status("📋 Bedrock機能は無効または AWS未接続")
                if not self.config.get('bedrock_features', {}).get('enabled', False):
                    self.logger.print_status("📋 Bedrock設定が無効")
                if not self.aws:
                    self.logger.print_status("📋 AWS未接続")
                elif not hasattr(self.aws, 'lambda_client'):
                    self.logger.print_status("📋 Lambda クライアント未初期化")
        except Exception as e:
            self.logger.print_warning(f"⚠️ BedrockManager初期化エラー: {e}")
            self.bedrock_manager = None

        # 初期化完了時のデバッグログ
        self.logger.print_status(f"🔍 DEBUG: bedrock_manager初期化状態 = {self.bedrock_manager is not None}")
        self.logger.print_success("✅ 初期化完了（11スロット対応版）")

    def get_current_time_slot_info(self):
        """
        現在時刻に基づく時間帯スロット情報を取得（11スロット対応新機能）
        Returns:
            tuple: (slot_name, hashtags) または None（エラー時）
        """
        if not self.posting_schedule_mgr:
            self.logger.print_warning("⚠️ 11スロット機能が無効です")
            return None
        try:
            now = datetime.now(JST)
            slot_name, hashtags = self.posting_schedule_mgr.get_current_time_slot_and_hashtags(now)
            self.logger.print_status(f"📅 現在時刻スロット: {slot_name} (JST: {now.strftime('%H:%M')})")
            return slot_name, hashtags
        except Exception as e:
            self.logger.print_error(f"❌ 時間帯スロット判定エラー: {e}")
            return None

    def enhance_metadata_with_time_slots(self, metadata: dict, gen_type):
        """
        メタデータに11スロット対応情報を追加（新機能）
        Args:
            metadata: 既存のメタデータ辞書
            gen_type: GenerationType インスタンス
        Returns:
            dict: 11スロット情報を追加したメタデータ
        """
        if not self.posting_schedule_mgr:
            # 11スロット機能が無効な場合は既存フォーマットを維持
            self.logger.print_status("📋 11スロット機能無効のため、従来メタデータを使用")
            metadata['suitableTimeSlots'] = self.default_suitable_slots
            metadata['recommendedTimeSlot'] = 'general'
            return metadata

        try:
            # 現在時刻に基づく推奨スロット決定
            current_slot_info = self.get_current_time_slot_info()
            if current_slot_info:
                recommended_slot, _ = current_slot_info
            else:
                recommended_slot = 'general'

            # 11スロット対応メタデータ追加
            metadata['suitableTimeSlots'] = self.default_suitable_slots.copy()
            metadata['recommendedTimeSlot'] = recommended_slot

            # スロット設定バージョン情報追加
            try:
                slot_version = self.posting_schedule_mgr.get_config_version()
                metadata['slotConfigVersion'] = slot_version
            except:
                metadata['slotConfigVersion'] = 'unknown'

            self.logger.print_success(f"✅ 11スロット情報追加完了 - 推奨: {recommended_slot}")
            self.logger.print_status(f"📋 適合スロット({len(metadata['suitableTimeSlots'])}個): {', '.join(metadata['suitableTimeSlots'][:3])}...")

        except Exception as e:
            # エラー時はフォールバック
            self.logger.print_warning(f"⚠️ 11スロット情報追加エラー、フォールバック値を使用: {e}")
            metadata['suitableTimeSlots'] = self.default_suitable_slots
            metadata['recommendedTimeSlot'] = 'general'
            metadata['slotConfigVersion'] = 'fallback'

        return metadata

    def generate_hybrid_image(self, gen_type: GenerationType, count: int = 1) -> int:
        """
        ハイブリッド画像生成（既存機能 + 11スロット対応強化）
        """
        overall_timer = ProcessTimer(self.logger)
        overall_timer.start(f"SDXL統合画像生成バッチ（{count}枚）- 11スロット対応版")

        # 既存のモデル管理機能（完全保持）
        try:
            from .model_manager import ModelManager
            ModelManager(self.config).ensure_model_for_generation_type(gen_type)
        except HybridGenerationError as e:
            self.logger.print_error(f"❌ モデル切替失敗: {e}")
            return 0

        success = 0
        for i in range(count):
            img_timer = ProcessTimer(self.logger)
            img_timer.start(f"画像{i+1}/{count}")
            try:
                # 既存の生成ロジック + 11スロット対応
                path, response = self._generate_single(gen_type, i)
                success += 1
                img_timer.end_and_report(1)
            except Exception as e:
                self.logger.print_error(f"❌ 生成エラー: {e}")
                break

        overall_timer.end_and_report(success)
        self.logger.print_stage(f"=== 完了: {success}/{count} 枚（11スロット対応版） ===")
        return success

    def _generate_single(self, gen_type: GenerationType, index: int):
        """
        単発生成ワークフロー（既存機能完全保持 + 11スロット対応強化）
        """
        # ===============================================
        # 既存の入力画像選択ロジック（完全保持）
        # ===============================================
        if not self.input_pool:
            cfg = self.config.get('input_images', {})
            source_dir = cfg.get('source_directory', '/tmp/input')
            formats = cfg.get('supported_formats', ['jpg', 'jpeg', 'png'])
            if not os.path.exists(source_dir):
                os.makedirs(source_dir, exist_ok=True)
                self.logger.print_warning(f"⚠️ 入力ディレクトリを作成しました: {source_dir}")

            self.input_pool = InputImagePool(
                source_dir, formats,
                history_file=os.path.join(self.temp_dir, 'image_history.json')
            )

        # 既存の入力画像取得ロジック（完全保持）
        try:
            input_path = self.input_pool.get_next_image()
            if input_path:
                self.logger.print_status(f"📸 入力画像（ポーズ検出モード用）: {input_path}")
            else:
                self.logger.print_status("🎯 ポーズ指定モード: 入力画像なし")
        except FileNotFoundError:
            self.logger.print_warning("⚠️ 入力画像がないため、プロンプトのみで生成します")
            input_path = None

        # ===============================================
        # 既存の前処理ロジック（完全保持）
        # ===============================================
        proc = ImageProcessor(self.config, self.temp_dir, getattr(self.pose_manager, 'pose_mode', 'detection'))
        if input_path:
            resized = proc.preprocess_input_image(input_path)
            b64 = proc.encode_image_to_base64(resized)
        else:
            resized = None
            b64 = None

        # ===============================================
        # 既存のプロンプト構築ロジック（完全保持）
        # ===============================================
        prompt, neg, ad_neg = self.prompt_builder.build_complete_prompts(
            gen_type,
            mode="auto",
            include_random_elements=True,
            include_lora=True,
            include_pose=True,
            include_age=True
        )

        # ===============================================
        # 既存の生成実行ロジック（完全保持）
        # ===============================================
        engine = GeneratorEngine(self.config, getattr(self.pose_manager, 'pose_mode', 'detection'), self.logger)
        img_path, resp = engine.execute_generation(prompt, neg, ad_neg, input_b64=b64)

        # ===============================================
        # 既存の仕上げ処理ロジック（完全保持）
        # ===============================================
        if img_path and os.path.exists(img_path):
            proc.apply_final_enhancement(img_path)

        # ===============================================
        # 11スロット対応メタデータ強化（新機能追加）
        # ===============================================
        # 既存のレスポンスデータに11スロット情報を追加
        # メタデータ拡張とBedrockコメント生成を分離
        enhanced_resp = self._enhance_metadata_with_bedrock_comments(resp, gen_type, index)

        # ===============================================
        # 既存の保存ロジック（11スロット対応強化）
        # ===============================================
        saver = ImageSaver(self.config, self.aws, self.temp_dir,
                           local_mode=self.config.get('local_execution', {}).get('enabled', True))

        if self.config.get('local_execution', {}).get('enabled', True):
            # ローカル保存（既存機能 + 11スロット対応）
            pose_mode = getattr(gen_type, 'pose_mode', 'detection')  # デフォルト値を設定
            saver.save_image_locally(img_path, index, enhanced_resp, gen_type, input_path, pose_mode)
        else:
            # AWS保存（既存機能 + 11スロット対応）
            pose_mode = getattr(self, 'pose_mode', 'detection')  # pose_modeを取得
            saver.save_image_to_s3_and_dynamodb(img_path, index, enhanced_resp, gen_type, input_path, pose_mode)

        return img_path, enhanced_resp

    def _enhance_metadata_with_bedrock_comments(self, metadata: dict, gen_type, index: int) -> dict:
        """メタデータにBedrockコメントを追加（分離されたメソッド・修正版）"""
        
        # デバッグログ追加
        self.logger.print_status(f"🔍 DEBUG: bedrock_manager存在確認 = {hasattr(self, 'bedrock_manager') and self.bedrock_manager is not None}")
        self.logger.print_status(f"🔍 DEBUG: local_execution.enabled = {self.config.get('local_execution', {}).get('enabled', True)}")
        self.logger.print_status(f"🔍 DEBUG: bedrock_features.enabled = {self.config.get('bedrock_features', {}).get('enabled', False)}")
        
        # bedrock_manager属性の安全な確認
        if not hasattr(self, 'bedrock_manager') or self.bedrock_manager is None:
            self.logger.print_status("📋 BedrockManagerが初期化されていないため、コメント生成をスキップ")
            metadata['comments'] = {}
            metadata['commentGeneratedAt'] = ''
            return metadata

        # 修正：ローカルモードの場合はBedrockを無効にする
        is_local_mode = self.config.get('local_execution', {}).get('enabled', True)
        is_bedrock_enabled = self.config.get('bedrock_features', {}).get('enabled', False)
        
        if is_local_mode:
            self.logger.print_status("📋 ローカルモード: Bedrockコメント生成をスキップ")
            metadata['comments'] = self._get_fallback_comments()
            metadata['commentGeneratedAt'] = datetime.now(JST).isoformat()
            return metadata
        
        if not is_bedrock_enabled:
            self.logger.print_status("📋 Bedrock機能が無効のため、コメント生成をスキップ")
            metadata['comments'] = {}
            metadata['commentGeneratedAt'] = ''
            return metadata

        try:
            self.logger.print_status("🤖 Bedrockコメント生成開始...")
            
            bedrock_metadata = {
                'genre': gen_type.name,
                'style': 'general',
                'imageId': f"temp_{int(time.time())}_{index}",
                'prompt': metadata.get('prompt', '')[:500],
                'pose_mode': getattr(self.pose_manager, 'pose_mode', 'detection')
            }
            
            comments = self.bedrock_manager.generate_all_timeslot_comments(bedrock_metadata)
            metadata['comments'] = comments
            metadata['commentGeneratedAt'] = datetime.now(JST).isoformat() if comments else ''
            
            if comments:
                self.logger.print_success(f"✅ Bedrockコメント生成完了: {len(comments)}件")
            else:
                self.logger.print_warning("⚠️ Bedrockコメント生成結果が空です")
                
        except Exception as e:
            self.logger.print_error(f"❌ Bedrockコメント生成エラー: {e}")
            metadata['comments'] = {}
            metadata['commentGeneratedAt'] = ''

        return metadata

    def _get_fallback_comments(self) -> dict:
        """ローカルモード用のフォールバックコメント"""
        fallback_comments = {
            'early_morning': "おはようございます！今日も素敵な一日になりそうです✨",
            'morning': "今日もお仕事頑張ってください！応援しています📣",
            'late_morning': "午前中お疲れ様！コーヒーブレイクでひと息つこう☕",
            'lunch': "お昼休みですね！何か美味しいものを食べて午後も頑張りましょう🍽️",
            'afternoon': "午後もお疲れ様！ティータイムで気分転換はいかが？🫖",
            'pre_evening': "もうすぐ夕方ですね！今日一日もあと少し頑張って🌅",
            'evening': "今日もお疲れ様でした！これからの予定はあるのかな？🌙",
            'night': "今日もお疲れ様！夜の自分時間を大切に過ごしてね💆♀️",
            'late_night': "深夜だけど今夜はどんな時間を過ごしてる？🌃",
            'mid_night': "今日も一日お疲れ様でした！ゆっくり休んでおやすみなさい🌙✨",
            'general': "素敵な時間をお過ごしください💫"
        }
    
        self.logger.print_status(f"📝 ローカルモード: フォールバックコメント使用（{len(fallback_comments)}件）")
        return fallback_comments

    # ===============================================
    # 11スロット対応ユーティリティメソッド（新機能）
    # ===============================================

    def get_suitable_slots_for_genre(self, genre: str):
        """
        ジャンルに基づく適合スロット推奨（新機能）
        Args:
            genre: 画像ジャンル
        Returns:
            list: 推奨スロットリスト
        """
        if not self.posting_schedule_mgr:
            return self.default_suitable_slots

        try:
            # ジャンル別の推奨ロジック
            if genre in ['gyal_erotic', 'gyal_black']:
                # 成人向けコンテンツは夜間帯優先
                return ['night', 'late_night', 'pre_evening', 'evening', 'general']
            elif genre in ['seiso', 'teen']:
                # 清楚系は日中優先
                return ['morning', 'late_morning', 'lunch', 'afternoon', 'general']
            elif genre == 'normal':
                # 標準ジャンルは全時間帯対応
                return self.default_suitable_slots
            else:
                return self.default_suitable_slots
        except Exception as e:
            self.logger.print_warning(f"⚠️ ジャンル別適合スロット取得エラー: {e}")
            return self.default_suitable_slots

    def validate_time_slots_configuration(self):
        """
        11スロット設定の妥当性検証（新機能）
        Returns:
            bool: 設定が有効な場合True
        """
        if not self.posting_schedule_mgr:
            self.logger.print_warning("⚠️ 11スロット機能が無効です")
            return False

        try:
            # 基本検証
            all_slots = self.posting_schedule_mgr.get_all_slot_names()
            if len(all_slots) != 11:
                self.logger.print_error(f"❌ スロット数エラー: 期待値11、実際{len(all_slots)}")
                return False

            # 設定バージョン確認
            version = self.posting_schedule_mgr.get_config_version()
            self.logger.print_success(f"✅ 11スロット設定検証完了 - バージョン: {version}")
            return True

        except Exception as e:
            self.logger.print_error(f"❌ 11スロット設定検証エラー: {e}")
            return False

    def get_debug_info(self):
        """
        デバッグ情報取得（既存機能 + 11スロット情報追加）
        Returns:
            dict: デバッグ情報
        """
        # 既存デバッグ情報
        debug_info = {
            'version': '7.0_11slot_fixed',
            'local_mode': self.config.get('local_execution', {}).get('enabled', True),
            'fast_mode': self.config.get('fast_mode', {}).get('enabled', False),
            'bedrock_enabled': self.config.get('bedrock_features', {}).get('enabled', False),
            'bedrock_manager_initialized': self.bedrock_manager is not None,
            'aws_region': self.config.get('aws', {}).get('region', 'N/A'),
            'generation_types': len(self.generation_types),
            # 11スロット対応デバッグ情報（新規追加）
            'slot_feature_enabled': self.posting_schedule_mgr is not None,
            'total_slots': len(self.all_time_slots),
            'default_suitable_slots_count': len(self.default_suitable_slots),
        }

        if self.posting_schedule_mgr:
            try:
                current_slot_info = self.get_current_time_slot_info()
                if current_slot_info:
                    debug_info['current_slot'] = current_slot_info[0]
                    debug_info['current_hashtags'] = current_slot_info[1]
                debug_info['slot_config_version'] = self.posting_schedule_mgr.get_config_version()
                debug_info['slot_validation'] = self.validate_time_slots_configuration()
            except Exception as e:
                debug_info['slot_debug_error'] = str(e)

        return debug_info

    # ===============================================
    # 既存メソッド保持用の追加メソッド
    # ===============================================

    def generate_daily_batch(self):
        """日次バッチ生成（既存機能保持）"""
        self.logger.print_stage("🗓️ 日次バッチ生成開始")

        batch_size = self.config.get('generation', {}).get('batch_size', 5)
        total_success = 0

        for gen_type in self.generation_types:
            try:
                success = self.generate_hybrid_image(gen_type, batch_size)
                total_success += success
                self.logger.print_status(f"📊 {gen_type.name}: {success}/{batch_size}枚成功")
            except Exception as e:
                self.logger.print_error(f"❌ {gen_type.name}生成エラー: {e}")
                continue

        self.logger.print_stage(f"🎉 日次バッチ完了: 総計{total_success}枚生成")
        return total_success

    def cleanup_temp_files(self):
        """一時ファイル清理（既存機能保持）"""
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                os.makedirs(self.temp_dir, exist_ok=True)
                self.logger.print_success("✅ 一時ファイル清理完了")
        except Exception as e:
            self.logger.print_warning(f"⚠️ 一時ファイル清理エラー: {e}")
