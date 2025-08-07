#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
S3Uploader - S3 アップロード機能
- upload_to_s3: 画像アップロード
"""

import time
from common.logger import ColorLogger
from botocore.exceptions import ClientError

class S3Uploader:
    """S3 アップロード管理クラス"""

    def __init__(self, s3_client, bucket, logger):
        self.s3 = s3_client
        self.bucket = bucket
        self.logger = logger

    def upload_to_s3(self, image_path, s3_key):
        """S3 ファイルアップロード"""
        try:
            self.logger.print_status(f"📤 S3アップロード: {s3_key}")
            # 重複チェック
            try:
                self.s3.head_object(Bucket=self.bucket, Key=s3_key)
                self.logger.print_warning("既存ファイル、スキップ")
                return True
            except ClientError as e:
                if e.response['Error']['Code'] != '404':
                    raise
            with open(image_path,'rb') as f:
                self.s3.upload_fileobj(f, self.bucket, s3_key,
                                       ExtraArgs={'ContentType':'image/png',
                                                  'Metadata':{'upload-source':'register_v9',
                                                             'upload-timestamp':time.strftime("%Y-%m-%dT%H:%M:%S")}})
            self.logger.print_success("✅ S3アップロード完了")
            return True
        except Exception as e:
            self.logger.print_error(f"S3アップロードエラー: {e}")
            return False
