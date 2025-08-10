#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MetadataConverter - ローカルメタデータ→AWS用変換（11スロット対応・S3動的取得版）
リファクタリング前の全機能を再現 + S3からスロット情報を動的取得
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from common.logger import ColorLogger
from common.config_manager import ConfigManager

JST = timezone(timedelta(hours=9))

class MetadataConverter:
    """メタデータ変換クラス（11スロット対応・S3動的取得版）"""

    def __init__(self, logger):
        self.logger = logger
        
        # ===============================================
        # 11スロット対応：S3からスロット情報を動的取得
        # ===============================================
        try:
            cfg_mgr = ConfigManager(self.logger)
            self.posting_schedule_mgr = cfg_mgr.get_posting_schedule_manager()
            
            # S3から全スロット情報を取得
            self.all_time_slots = cfg_mgr.get_all_time_slots()
            self.default_suitable_slots = cfg_mgr.get_default_suitable_slots()
            
            self.logger.print_success(f"✅ MetadataConverter: S3から11スロット情報取得完了 ({len(self.all_time_slots)}スロット)")
            
        except Exception as e:
            # S3取得失敗時のフォールバック（ハードコード値）
            self.logger.print_warning(f"⚠️ S3スロット情報取得失敗、フォールバック値使用: {e}")
            self.posting_schedule_mgr = None
            self.all_time_slots = []
            self.default_suitable_slots = [
                "early_morning", "morning", "late_morning", "lunch", 
                "afternoon", "pre_evening", "evening", "night", 
                "late_night", "mid_night", "general"
            ]

    def get_suitable_time_slots(self):
        """
        適合時間帯スロットを取得（S3動的取得またはフォールバック）
        
        Returns:
            list: 適合時間帯スロットのリスト
        """
        if self.posting_schedule_mgr and self.all_time_slots:
            # S3から取得したスロット情報を使用
            suitable_slots = self.all_time_slots.copy()
            
            # 'general'が含まれていない場合は追加（フォールバック用として必須）
            if 'general' not in suitable_slots:
                suitable_slots.append('general')
                
            self.logger.print_status(f"📋 S3から取得したスロット使用: {len(suitable_slots)}スロット")
            return suitable_slots
        else:
            # フォールバック：ハードコード値使用
            self.logger.print_warning("⚠️ フォールバックスロット使用（S3取得失敗のため）")
            return self.default_suitable_slots.copy()

    def convert_metadata_for_aws(self, local_metadata):
        """ローカルメタデータをAWS用に変換（既存機能完全保持 + S3動的スロット取得）"""
        # image_idを変換（local_sdxl_* → sdxl_*）（既存機能保持）
        original_id = local_metadata['image_id']
        if original_id.startswith('local_sdxl_'):
            new_id = original_id.replace('local_sdxl_', 'sdxl_', 1)
        else:
            new_id = original_id

        # 基本情報取得（既存機能保持）
        genre = local_metadata['genre']
        created_at_iso = local_metadata.get('created_at', datetime.now().isoformat())

        # created_atから日時文字列生成（既存機能保持）
        try:
            dt = datetime.fromisoformat(created_at_iso.replace('Z', '+00:00'))
            created_at_string = dt.strftime("%Y%m%d%H%M%S")
        except:
            created_at_string = datetime.now().strftime("%Y%m%d%H%M%S")

        # S3キー生成（既存機能保持）
        s3_key = f"image-pool/{genre}/{new_id}.png"

        # ===============================================
        # 11スロット対応：S3から動的に適合時間帯スロットを取得
        # ===============================================
        suitable_slots = self.get_suitable_time_slots()

        # DynamoDBアイテム構築（既存機能保持 + 11スロット対応フィールド追加）
        aws_metadata = {
            "imageId": new_id,
            "s3Bucket": "",  # 設定側で上書き
            "s3Key": s3_key,
            "genre": genre,
            "imageState": "unprocessed",
            "postingStage": "notposted",
            "createdAt": created_at_string,
            # --- 11スロット対応フィールド（S3から動的取得） ---
            "suitableTimeSlots": suitable_slots,
            "recommendedTimeSlot": "general",  # デフォルト値、後で更新される
            "slotConfigVersion": self._get_slot_config_version(),  # S3設定バージョン情報
            # --- 既存フィールド（完全保持） ---
            "preGeneratedComments": {},
            "commentGeneratedAt": "",
            "sdParams": self.extract_sd_params(local_metadata),
            # X投稿管理用フィールド（既存機能保持）
            "scheduledPostTime": "",
            "actualPostTime": created_at_string,
            "tweetId": "",
            "postingAttempts": 0,
            "lastErrorMessage": "",
            "movedToArchive": False,
        }

        return aws_metadata

    def _get_slot_config_version(self):
        """
        スロット設定バージョンを取得
        
        Returns:
            str: 設定バージョン文字列
        """
        if self.posting_schedule_mgr:
            try:
                return self.posting_schedule_mgr.get_config_version()
            except:
                return "unknown"
        else:
            return "fallback"

    def extract_sd_params(self, local_metadata):
        """SDパラメータ抽出（既存機能完全保持）"""
        def safe_decimal_convert(value):
            """float値をDecimalに安全に変換"""
            if isinstance(value, float):
                return Decimal(str(value))
            elif isinstance(value, (int, str)):
                try:
                    return Decimal(str(value))
                except:
                    return value
            return value

        sd_params = {}

        # ベースパラメータ（既存機能保持）
        if 'genre' in local_metadata:
            sd_params['base'] = {
                'generation_method': local_metadata.get('generation_mode', ''),
                'input_image': local_metadata.get('input_image', ''),
                'pose_mode': local_metadata.get('pose_mode', 'detection'),
                'fast_mode_enabled': str(local_metadata.get('fast_mode_enabled', False)),
                'secure_random_enabled': 'true',
                'ultra_memory_safe_enabled': str(local_metadata.get('ultra_memory_safe_enabled', False)),
                'bedrock_enabled': str(local_metadata.get('bedrock_enabled', False))
            }

        # SDXL統合生成パラメータ（Decimal型対応）（既存機能保持）
        if 'sdxl_unified_generation' in local_metadata:
            sdxl_gen = local_metadata['sdxl_unified_generation']
            sd_params['sdxl_unified'] = {
                'prompt': sdxl_gen.get('prompt', ''),
                'negative_prompt': sdxl_gen.get('negative_prompt', ''),
                'steps': int(sdxl_gen.get('steps', 30)),
                'cfg_scale': safe_decimal_convert(sdxl_gen.get('cfg_scale', 7.0)),
                'width': int(sdxl_gen.get('width', 896)),
                'height': int(sdxl_gen.get('height', 1152)),
                'model': sdxl_gen.get('model', ''),
                'sampler': sdxl_gen.get('sampler', 'DPM++ 2M Karras')
            }

        # ControlNetパラメータ（Decimal型対応）（既存機能保持）
        if 'controlnet' in local_metadata:
            cn = local_metadata['controlnet']
            sd_params['controlnet'] = {
                'enabled': cn.get('enabled', False),
                'openpose': {
                    'enabled': cn.get('openpose', {}).get('enabled', False),
                    'weight': safe_decimal_convert(cn.get('openpose', {}).get('weight', 0.8))
                },
                'depth': {
                    'enabled': cn.get('depth', {}).get('enabled', False),
                    'weight': safe_decimal_convert(cn.get('depth', {}).get('weight', 0.3))
                }
            }

        # ADetailerパラメータ（既存機能保持）
        if 'adetailer' in local_metadata:
            ad = local_metadata['adetailer']
            sd_params['adetailer'] = {
                'enabled': ad.get('enabled', True)
            }

        return sd_params
