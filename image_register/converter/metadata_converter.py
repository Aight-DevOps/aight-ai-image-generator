#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MetadataConverter - ローカルメタデータ→AWS用変換
- convert_metadata_for_aws
- extract_sd_params
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from common.logger import ColorLogger

JST = timezone(timedelta(hours=9))

class MetadataConverter:
    """メタデータ変換クラス"""

    def __init__(self, logger):
        self.logger = logger

    def convert_metadata_for_aws(self, local):
        """ローカルメタデータをAWS用に変換"""
        orig = local['image_id']
        new_id = orig.replace('local_', 'sdxl_',1)
        created = local.get('created_at', datetime.now().isoformat())
        try:
            dt = datetime.fromisoformat(created)
            created_str = dt.strftime("%Y%m%d%H%M%S")
        except:
            created_str = datetime.now(JST).strftime("%Y%m%d%H%M%S")
        genre = local['genre']
        s3_key = f"image-pool/{genre}/{new_id}.png"
        sd_params = self.extract_sd_params(local)
        item = {
            "imageId": new_id,
            "s3Bucket": self.logger and "",  # 設定側上書き
            "s3Key": s3_key,
            "genre": genre,
            "imageState": "unprocessed",
            "postingStage": "notposted",
            "createdAt": created_str,
            "suitableTimeSlots": self.default_slots(),
            "preGeneratedComments": {},
            "commentGeneratedAt": "",
            "sdParams": sd_params,
            "scheduledPostTime": "",
            "actualPostTime": created_str,
            "tweetId": "",
            "postingAttempts": 0,
            "lastErrorMessage": "",
            "movedToArchive": False
        }
        return item

    def extract_sd_params(self, local):
        """SD パラメータ抽出"""
        params = {}
        base = {
            "generation_mode": local.get('generation_mode',''),
            "input_image": local.get('input_image',''),
            "pose_mode": local.get('pose_mode',''),
            "fast_mode_enabled": str(local.get('fast_mode_enabled',False))
        }
        params['base'] = base
        if 'sdxl_unified_generation' in local:
            s = local['sdxl_unified_generation']
            params['sdxl_unified'] = {
                'prompt': s.get('prompt',''),
                'negative_prompt': s.get('negative_prompt',''),
                'steps': int(s.get('steps',30)),
                'cfg_scale': Decimal(str(s.get('cfg_scale',7.0))),
                'width': int(s.get('width',896)),
                'height': int(s.get('height',1152)),
                'model': s.get('model','')
            }
        return params

    def default_slots(self):
        """適合スロットデフォルト"""
        return ["general"]
