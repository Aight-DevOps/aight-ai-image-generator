#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ImageSaver - 生成画像の保存機能
- save_image_to_s3_and_dynamodb: AWS 保存処理
- save_image_locally: ローカル保存処理
"""

import os
import shutil
import json
import boto3
from datetime import datetime
from common.logger import ColorLogger

class ImageSaver:
    """画像保存管理クラス"""

    def __init__(self, config, aws_clients, temp_dir, local_mode=False):
        """
        Args:
            config: 設定 dict
            aws_clients: AWSClientManager
            temp_dir: 一時ディレクトリ
            local_mode: bool
        """
        self.config = config
        self.s3 = aws_clients.s3_client
        self.dynamodb_table = aws_clients.dynamodb_table
        self.lambda_client = getattr(aws_clients, 'lambda_client', None)
        self.logger = ColorLogger()
        self.temp_dir = temp_dir
        self.local_mode = local_mode

    def save_image_locally(self, final_image_path, index, response, gen_type, input_path):
        """ローカル保存専用"""
        now = datetime.now().strftime("%Y%m%d%H%M%S")
        image_id = f"local_{gen_type.name}_{now}_{index:03d}"
        out_dir = self.config['local_execution']['output_directory']
        if self.config['local_execution']['create_subdirs']:
            out_dir = os.path.join(out_dir, gen_type.name)
            os.makedirs(out_dir, exist_ok=True)
        dst = os.path.join(out_dir, f"{image_id}.png")
        shutil.copy2(final_image_path, dst)
        self.logger.print_success(f"📁 ローカル保存完了: {dst}")
        # メタデータ保存
        metadata = {
            "image_id": image_id,
            "parameters": response.get('parameters', {}),
            "genre": gen_type.name,
            "model": gen_type.model_name,
            "input_image": os.path.basename(input_path) if input_path else None
        }
        meta_path = os.path.join(out_dir, f"{image_id}_metadata.json")
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        self.logger.print_status(f"📄 メタデータ保存: {meta_path}")
        return True

    def save_image_to_s3_and_dynamodb(self, final_image_path, index, response, gen_type, input_path):
        """S3 と DynamoDB 保存処理"""
        # s3 key, dynamo item 構築
        image_id = f"sdxl_{gen_type.name}_{int(time.time())}_{index:03d}"
        s3_key = f"image-pool/{gen_type.name}/{image_id}.png"
        # S3 アップロード
        with open(final_image_path, 'rb') as f:
            self.s3.upload_fileobj(f, self.config['aws']['s3_bucket'], s3_key,
                                   ExtraArgs={'ContentType': 'image/png'})
        self.logger.print_success(f"✅ S3 アップロード完了: {s3_key}")
        # DynamoDB 保存
        item = {
            "imageId": image_id,
            "s3Bucket": self.config['aws']['s3_bucket'],
            "s3Key": s3_key,
            "genre": gen_type.name,
            "createdAt": datetime.now().strftime("%Y%m%d%H%M%S"),
            "parameters": response.get('parameters', {}),
            "model": gen_type.model_name,
            "inputImage": os.path.basename(input_path) if input_path else None
        }
        self.dynamodb_table.put_item(Item=item)
        self.logger.print_success(f"✅ DynamoDB 保存完了: {image_id}")
        return True
