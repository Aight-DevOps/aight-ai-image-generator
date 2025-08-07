#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MetadataManager - DynamoDB用メタデータ構築機能
- prepare_metadata_and_dynamodb_item: S3キー・DynamoDBアイテム準備
"""

import os
import json
from datetime import datetime, timezone, timedelta
from common.logger import ColorLogger

# JST タイムゾーン
JST = timezone(timedelta(hours=9))

class MetadataManager:
    """DynamoDBメタデータ構築クラス"""

    def __init__(self, config, default_slots):
        """
        Args:
            config: 設定 dict
            default_slots: 適合時間帯スロット一覧
        """
        self.config = config
        self.default_slots = default_slots
        self.logger = ColorLogger()

    def prepare_metadata_and_dynamodb_item(self, final_image_path: str, index: int,
                                           generation_response: dict, gen_type,
                                           original_input_path: str):
        """
        S3キーと DynamoDB アイテムを準備
        Returns: image_id, dynamodb_item
        """
        # 画像ID生成
        now = datetime.now(JST).strftime("%Y%m%d%H%M%S")
        fast_suffix = "_fast" if gen_type.fast_mode else ""
        ultra_suffix = "_ultra_safe"
        bedrock_suffix = "_bedrock" if gen_type.bedrock_enabled else ""
        pose_suffix = f"_{gen_type.pose_mode}" if hasattr(gen_type, 'pose_mode') else ""
        image_id = f"sdxl_{gen_type.name}{fast_suffix}{ultra_suffix}{bedrock_suffix}{pose_suffix}_{now}_{index:03d}"

        # S3キー
        s3_key = f"image-pool/{gen_type.name}/{image_id}.png"

        # SD パラメータ取得
        params = generation_response.get('parameters', {})

        # Bedrock コメント
        pre_comments = {}
        comment_ts = ""
        if hasattr(gen_type, 'bedrock_comments'):
            pre_comments = gen_type.bedrock_comments
            comment_ts = datetime.now(JST).isoformat()

        # DynamoDB アイテム
        item = {
            "imageId": image_id,
            "s3Bucket": self.config['aws']['s3_bucket'],
            "s3Key": s3_key,
            "genre": gen_type.name,
            "imageState": "unprocessed",
            "postingStage": "notposted",
            "createdAt": now,
            "suitableTimeSlots": self.default_slots,
            "preGeneratedComments": pre_comments,
            "commentGeneratedAt": comment_ts,
            "sdParams": {
                "prompt": params.get('prompt', ''),
                "negative_prompt": params.get('negative_prompt', ''),
                "steps": params.get('steps', self.config['sdxl_generation']['steps']),
                "cfg_scale": params.get('cfg_scale', self.config['sdxl_generation']['cfg_scale']),
                "sampler": params.get('sampler', self.config['sdxl_generation']['sampler_name']),
                "width": params.get('width', self.config['sdxl_generation']['width']),
                "height": params.get('height', self.config['sdxl_generation']['height']),
                "model": gen_type.model_name
            },
            # X 投稿管理フィールド
            "scheduledPostTime": "",
            "actualPostTime": now,
            "tweetId": "",
            "postingAttempts": 0,
            "lastErrorMessage": "",
            "movedToArchive": False
        }

        self.logger.print_status(f"📝 メタデータ準備完了: {image_id}")
        return image_id, item
