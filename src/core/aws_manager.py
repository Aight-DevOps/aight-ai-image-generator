#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AWS Manager - AWS操作を統括するクラス
"""

import boto3
import json
import time
from datetime import datetime, timezone, timedelta
from botocore.exceptions import ClientError, NoCredentialsError
from botocore.config import Config
from typing import Any, Dict, Optional
from decimal import Decimal
from .exceptions import AWSConnectionError

# JST タイムゾーン定義
JST = timezone(timedelta(hours=9))

class AWSManager:
    """AWS操作を統括するクラス"""

    def __init__(self, config_manager):
        """
        Args:
            config_manager: ConfigManager インスタンス
        """
        self.aws_config: Dict[str, Any] = config_manager.get_aws_config()
        self.local_mode: bool = config_manager.is_local_mode()
        self.bedrock_config: Dict[str, Any] = config_manager.get_bedrock_config()
        self.s3_client = None
        self.dynamodb = None
        self.dynamodb_table = None
        self.lambda_client = None
        if not self.local_mode:
            self._setup_clients()

    def _setup_clients(self):
        """AWSクライアントの初期化"""
        try:
            boto_cfg = Config(
                retries={"max_attempts": 3},
                read_timeout=180,
                connect_timeout=60
            )
            # S3
            self.s3_client = boto3.client(
                "s3",
                region_name=self.aws_config["region"],
                config=boto_cfg
            )
            # DynamoDB
            self.dynamodb = boto3.resource(
                "dynamodb",
                region_name=self.aws_config["region"],
                config=boto_cfg
            )
            self.dynamodb_table = self.dynamodb.Table(self.aws_config["dynamodb_table"])
            # Lambda (Bedrock)
            if self.bedrock_config.get("enabled", False):
                self.lambda_client = boto3.client(
                    "lambda",
                    region_name=self.aws_config["region"],
                    config=boto_cfg
                )
            print(f"✅ AWSクライアント初期化完了: region={self.aws_config['region']}")
        except NoCredentialsError:
            raise AWSConnectionError("AWS認証情報が設定されていません")
        except Exception as e:
            raise AWSConnectionError(f"AWS接続エラー: {e}")

    def upload_to_s3(self, file_path: str, s3_key: str, content_type: str = "image/png") -> bool:
        """
        S3アップロード
        """
        if self.local_mode:
            print("⚠️ ローカルモード: S3アップロードをスキップ")
            return True
        try:
            # 既存オブジェクトチェック
            try:
                self.s3_client.head_object(Bucket=self.aws_config["s3_bucket"], Key=s3_key)
                print(f"⚠️ s3://{self.aws_config['s3_bucket']}/{s3_key} は既に存在するためスキップ")
                return True
            except ClientError as e:
                if e.response["Error"]["Code"] != "404":
                    raise
            # アップロード実行
            with open(file_path, "rb") as f:
                self.s3_client.upload_fileobj(
                    f,
                    self.aws_config["s3_bucket"],
                    s3_key,
                    ExtraArgs={
                        "ContentType": content_type,
                        "Metadata": {
                            "upload-source": "aight-ai-image-generator",
                            "upload-timestamp": datetime.now(JST).isoformat()
                        }
                    }
                )
            print(f"✅ S3アップロード完了: s3://{self.aws_config['s3_bucket']}/{s3_key}")
            return True
        except Exception as e:
            print(f"❌ S3アップロードエラー: {e}")
            return False

    def save_to_dynamodb(self, item: Dict[str, Any]) -> bool:
        """
        DynamoDB保存（float→Decimal 変換含む）
        """
        if self.local_mode:
            print("⚠️ ローカルモード: DynamoDB保存をスキップ")
            return True

        def _convert(o: Any, path="root") -> Any:
            if isinstance(o, float):
                return Decimal(str(o))
            if isinstance(o, dict):
                return {k: _convert(v, f"{path}.{k}") for k, v in o.items()}
            if isinstance(o, list):
                return [_convert(v, f"{path}[{i}]") for i, v in enumerate(o)]
            return o

        try:
            clean_item = _convert(item)
            self.dynamodb_table.put_item(Item=clean_item)
            print(f"✅ DynamoDB保存完了: imageId={item.get('imageId','unknown')}")
            return True
        except Exception as e:
            print(f"❌ DynamoDB保存エラー: {e}")
            return False

    def get_from_dynamodb(self, image_id: str) -> Optional[Dict[str, Any]]:
        """DynamoDB から単一アイテム取得"""
        if self.local_mode:
            return None
        try:
            resp = self.dynamodb_table.get_item(Key={"imageId": image_id})
            return resp.get("Item")
        except Exception as e:
            print(f"❌ DynamoDB取得エラー: {e}")
            return None
