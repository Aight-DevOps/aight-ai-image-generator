#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
S3Uploader - S3アップロード機能（完全版）
"""

from datetime import datetime, timezone, timedelta
from botocore.exceptions import ClientError
from common.logger import ColorLogger

JST = timezone(timedelta(hours=9))

class S3Uploader:
    """S3アップローダー（完全版）"""
    
    def __init__(self, s3_client, bucket_name, logger):
        self.s3_client = s3_client
        self.bucket_name = bucket_name
        self.logger = logger
    
    def upload_to_s3(self, image_path: str, s3_key: str) -> bool:
        """S3アップロード（完全版）"""
        try:
            self.logger.print_status(f"📤 S3アップロード中: {s3_key}")
            
            # 重複チェック
            try:
                self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
                self.logger.print_warning(f"⚠️ S3に既存ファイルがあるためスキップ: {s3_key}")
                return True  # 既に存在する場合は成功とみなす
            except ClientError as e:
                if e.response['Error']['Code'] != '404':
                    raise  # 404以外のエラーは再度発生させる

            # アップロード実行
            with open(image_path, 'rb') as f:
                self.s3_client.upload_fileobj(
                    f,
                    self.bucket_name,
                    s3_key,
                    ExtraArgs={
                        'ContentType': 'image/png',
                        'Metadata': {
                            'upload-source': 'hybrid-bijo-register-v9',
                            'upload-timestamp': datetime.now(JST).isoformat()
                        }
                    }
                )

            self.logger.print_success(f"✅ S3アップロード完了: {s3_key}")
            return True

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            self.logger.print_error(f"❌ S3アップロードエラー ({s3_key}): {error_code}")
            return False
        except Exception as e:
            self.logger.print_error(f"❌ S3アップロードエラー ({s3_key}): {e}")
            return False
