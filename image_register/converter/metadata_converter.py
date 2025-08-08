#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MetadataConverter - ローカルメタデータ→AWS用変換（完全版）
リファクタリング前の全機能を再現
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from common.logger import ColorLogger

JST = timezone(timedelta(hours=9))

class MetadataConverter:
    """メタデータ変換クラス（完全版）"""

    def __init__(self, logger):
        self.logger = logger

    def convert_metadata_for_aws(self, local_metadata):
        """ローカルメタデータをAWS用に変換（完全版）"""
        # image_idを変換（local_sdxl_* → sdxl_*）
        original_id = local_metadata['image_id']
        if original_id.startswith('local_sdxl_'):
            new_id = original_id.replace('local_sdxl_', 'sdxl_', 1)
        else:
            new_id = original_id

        # 基本情報取得
        genre = local_metadata['genre']
        created_at_iso = local_metadata.get('created_at', datetime.now().isoformat())

        # created_atから日時文字列生成
        try:
            dt = datetime.fromisoformat(created_at_iso.replace('Z', '+00:00'))
            created_at_string = dt.strftime("%Y%m%d%H%M%S")
        except:
            created_at_string = datetime.now().strftime("%Y%m%d%H%M%S")

        # S3キー生成
        s3_key = f"image-pool/{genre}/{new_id}.png"

        # 適合時間帯スロット
        suitable_slots = ["early_morning", "morning", "lunch", "evening", "night", "mid_night", "general"]

        # DynamoDBアイテム構築（完全版）
        aws_metadata = {
            "imageId": new_id,
            "s3Bucket": "",  # 設定側で上書き
            "s3Key": s3_key,
            "genre": genre,
            "imageState": "unprocessed",
            "postingStage": "notposted",
            "createdAt": created_at_string,
            "suitableTimeSlots": suitable_slots,
            "preGeneratedComments": {},
            "commentGeneratedAt": "",
            "recommendedTimeSlot": "general",
            "sdParams": self.extract_sd_params(local_metadata),
            
            # X投稿管理用フィールド
            "scheduledPostTime": "",
            "actualPostTime": created_at_string,
            "tweetId": "",
            "postingAttempts": 0,
            "lastErrorMessage": "",
            "movedToArchive": False,
        }

        return aws_metadata

    def extract_sd_params(self, local_metadata):
        """SDパラメータ抽出（完全版）"""
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
        
        # ベースパラメータ
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

        # SDXL統合生成パラメータ（Decimal型対応）
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

        # ControlNetパラメータ（Decimal型対応）
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

        # ADetailerパラメータ
        if 'adetailer' in local_metadata:
            ad = local_metadata['adetailer']
            sd_params['adetailer'] = {
                'enabled': ad.get('enabled', True)
            }

        return sd_params
