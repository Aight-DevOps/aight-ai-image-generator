#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ImageSaver - 生成画像の保存機能
"""

import os
import time
import json
import shutil
from datetime import datetime, timezone, timedelta
from common.logger import ColorLogger
from common.aws_client import AWSClientManager
from common.types import HybridGenerationError

# JST
JST = timezone(timedelta(hours=9))

class ImageSaver:
    """画像保存管理クラス"""

    def __init__(self, config: dict, aws_client: AWSClientManager, temp_dir: str, local_mode: bool=False):
        self.config = config
        self.s3 = aws_client.s3_client if aws_client else None
        self.dynamodb_table = aws_client.dynamodb_table if aws_client else None
        self.lambda_client = getattr(aws_client, 'lambda_client', None) if aws_client else None
        self.logger = ColorLogger()
        self.temp_dir = temp_dir
        self.local_mode = local_mode

    def save_image_locally(self, image_path: str, index: int, response: dict, gen_type, input_path: str):
        """ローカル保存処理（メタデータ強化版）"""
        now = datetime.now(JST).strftime("%Y%m%d%H%M%S")
        fast = "_fast" if getattr(gen_type, 'fast_mode', False) else ""
        ultra = "_ultra_safe" if getattr(gen_type, 'ultra_safe_mode', False) else ""
        bedrock = "_bedrock" if getattr(gen_type, 'bedrock_enabled', False) else ""
        pose = f"_{getattr(gen_type, 'pose_mode', 'detection')}" if hasattr(gen_type, 'pose_mode') else ""
        model = getattr(gen_type, 'model_name', 'unknown').replace('.safetensors','').replace(' ', '_')
        image_id = f"local_sdxl_{gen_type.name}_{model}{fast}{ultra}{bedrock}{pose}_{now}_{index:03d}"

        out_dir = self.config.get('local_execution', {}).get('output_directory', './output_test_images')
        if self.config.get('local_execution', {}).get('create_subdirs', True):
            out_dir = os.path.join(out_dir, gen_type.name)
        os.makedirs(out_dir, exist_ok=True)

        dst = os.path.join(out_dir, f"{image_id}.png")
        shutil.copy2(image_path, dst)
        self.logger.print_success(f"📁 ローカル保存完了: {dst} ({os.path.getsize(dst)} bytes)")

        # 強化されたメタデータ
        params = response.get('parameters', {})
        
        # generation_mode の決定
        generation_mode = 'sdxl_unified'
        if getattr(gen_type, 'fast_mode', False):
            generation_mode = 'fast'
        elif getattr(gen_type, 'bedrock_enabled', False):
            generation_mode = 'bedrock'
        elif getattr(gen_type, 'ultra_safe_mode', False):
            generation_mode = 'ultra_safe'
        
        metadata = {
            # 必須フィールド
            "image_id": image_id,
            "genre": gen_type.name,
            "generation_mode": generation_mode,
            "created_at": now,
            "model_name": getattr(gen_type, 'model_name', 'unknown'),
            
            # 詳細フィールド
            "input_image": os.path.basename(input_path) if input_path else None,
            "pose_mode": getattr(gen_type, 'pose_mode', 'detection'),
            "fast_mode_enabled": getattr(gen_type, 'fast_mode', False),
            "bedrock_enabled": getattr(gen_type, 'bedrock_enabled', False),
            "ultra_memory_safe_enabled": getattr(gen_type, 'ultra_safe_mode', False),
            
            # SDXL統合生成パラメータ
            "sdxl_unified_generation": {
                "prompt": params.get('prompt', ''),
                "negative_prompt": params.get('negative_prompt', ''),
                "steps": self.config.get('sdxl_generation', {}).get('steps', 30),
                "cfg_scale": self.config.get('sdxl_generation', {}).get('cfg_scale', 7.0),
                "width": self.config.get('sdxl_generation', {}).get('width', 1024),
                "height": self.config.get('sdxl_generation', {}).get('height', 1024),
                "sampler_name": self.config.get('sdxl_generation', {}).get('sampler_name', 'DPM++ 2M Karras')
            },
            
            # Register用フィールド
            "s3Key": f"image-pool/{gen_type.name}/{image_id}.png",
            "imageState": "unprocessed",
            "postingStage": "notposted"
        }
        
        meta_path = os.path.join(out_dir, f"{image_id}_metadata.json")
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        self.logger.print_status(f"📄 メタデータ保存: {meta_path}")
        return True

    def save_image_to_s3_and_dynamodb(self, image_path: str, index: int, response: dict, gen_type, input_path: str):
        """S3 と DynamoDB 保存処理"""
        # メタデータ準備
        now = datetime.now(JST).strftime("%Y%m%d%H%M%S")
        fast = "_fast" if gen_type.fast_mode else ""
        ultra = "_ultra_safe"
        bedrock = "_bedrock" if getattr(gen_type, 'bedrock_enabled', False) else ""
        pose = f"_{gen_type.pose_mode}" if getattr(gen_type, 'pose_mode', None) else ""
        image_id = f"sdxl_{gen_type.name}_{now}_{index:03d}{fast}{ultra}{bedrock}{pose}"
        s3_key = f"image-pool/{gen_type.name}/{image_id}.png"

        # S3 アップロード
        try:
            self.logger.print_status(f"📤 S3 アップロード: s3://{self.config['aws']['s3_bucket']}/{s3_key}")
            with open(image_path, 'rb') as f:
                self.s3.upload_fileobj(
                    f,
                    self.config['aws']['s3_bucket'],
                    s3_key,
                    ExtraArgs={'ContentType': 'image/png'}
                )
            self.logger.print_success("✅ S3 アップロード完了")
        except Exception as e:
            self.logger.print_error(f"❌ S3 アップロード失敗: {e}")
            return False

        # DynamoDB アイテム構築
        params = response.get('parameters', {})
        base = {
            "generation_method": "sdxl_unified",
            "input_image": os.path.basename(input_path) if input_path else None,
            "pose_mode": getattr(gen_type, 'pose_mode', None),
            "fast_mode_enabled": gen_type.fast_mode
        }
        sdxl = {
            "prompt": params.get('prompt', ''),
            "negative_prompt": params.get('negative_prompt', ''),
            "steps": str(self.config['sdxl_generation']['steps']),
            "cfg_scale": str(self.config['sdxl_generation']['cfg_scale']),
            "sampler": self.config['sdxl_generation']['sampler_name'],
            "width": str(self.config['sdxl_generation']['width']),
            "height": str(self.config['sdxl_generation']['height']),
            "model": gen_type.model_name
        }
        control = {
            "enabled": gest[self.pose_mode]=="detection",
            "openpose": {"enabled": str(self.config['controlnet']['openpose']['enabled']),
                         "weight": str(self.config['controlnet']['openpose']['weight'])},
            "depth":   {"enabled": str(self.config['controlnet']['depth']['enabled']),
                        "weight": str(self.config['controlnet']['depth']['weight'])}
        }
        adetail = {
            "enabled": str(self.config['adetailer']['enabled']),
            "model": self.config['adetailer']['model'],
            "denoising_strength": str(self.config['adetailer']['denoising_strength'])
        }
        metadata_item = {
            "imageId": image_id,
            "s3Bucket": self.config['aws']['s3_bucket'],
            "s3Key": s3_key,
            "genre": gen_type.name,
            "imageState": "unprocessed",
            "postingStage": "notposted",
            "createdAt": now,
            "suitableTimeSlots": self.config.get('default_suitable_slots', []),
            "preGeneratedComments": {},  # Bedrock 省略可
            "commentGeneratedAt": "",
            "sdParams": {
                "base": base,
                "sdxl_unified": sdxl,
                "controlnet": control,
                "adetailer": adetail
            },
            "scheduledPostTime": "",
            "actualPostTime": now,
            "tweetId": "",
            "postingAttempts": 0,
            "lastErrorMessage": "",
            "movedToArchive": False
        }

        # DynamoDB 登録
        try:
            self.logger.print_status(f"📝 DynamoDB 登録: {image_id}")
            self.dynamodb_table.put_item(Item=metadata_item)
            self.logger.print_success("✅ DynamoDB 登録完了")
        except Exception as e:
            self.logger.print_error(f"❌ DynamoDB 保存失敗: {e}")
            return False

        return True
