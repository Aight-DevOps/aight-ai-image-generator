#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AWSClientManager - AWS クライアント初期化統合管理
全ツール共通のAWS接続管理機能
"""

import boto3
from botocore.config import Config
from botocore.exceptions import NoCredentialsError

class AWSClientManager:
    """AWS クライアント初期化統合管理クラス"""
    
    def __init__(self, logger, config):
        self.logger = logger
        self.config = config
        self.s3_client = None
        self.dynamodb = None
        self.dynamodb_table = None
        self.lambda_client = None
    
    def setup_clients(self, include_lambda=False):
        """AWSクライアント初期化"""
        try:
            aws_config = self.config['aws']
            
            # タイムアウト設定
            boto_config = Config(
                retries={'max_attempts': 3},
                read_timeout=self.config.get('performance', {}).get('dynamodb_timeout', 30),
                connect_timeout=30
            )
            
            self.s3_client = boto3.client('s3', region_name=aws_config['region'], config=boto_config)
            self.dynamodb = boto3.resource('dynamodb', region_name=aws_config['region'], config=boto_config)
            self.dynamodb_table = self.dynamodb.Table(aws_config['dynamodb_table'])
            
            # Lambda クライアント（必要に応じて）
            if include_lambda:
                self.lambda_client = boto3.client('lambda', region_name=aws_config['region'], config=boto_config)
                self.logger.print_status("🤖 Lambda クライアント初期化完了")
            
            self.logger.print_status(f"🔧 AWS設定: リージョン={aws_config['region']}, S3={aws_config['s3_bucket']}, DynamoDB={aws_config['dynamodb_table']}")
            return True
            
        except NoCredentialsError:
            self.logger.print_error("❌ AWS認証情報が設定されていません")
            return False
        except Exception as e:
            self.logger.print_error(f"❌ AWS接続エラー: {e}")
            return False
    
    def setup_register_clients(self):
        """登録ツール用AWSクライアント初期化"""
        try:
            aws_config = self.config['aws']
            boto_config = Config(
                retries={'max_attempts': 3},
                read_timeout=180,
                connect_timeout=60
            )
            
            self.s3_client = boto3.client('s3', region_name=aws_config['region'], config=boto_config)
            self.dynamodb = boto3.resource('dynamodb', region_name=aws_config['region'], config=boto_config)
            self.dynamodb_table = self.dynamodb.Table(aws_config['dynamodb_table'])
            
            if self.config.get('bedrock', {}).get('enabled', False):
                self.lambda_client = boto3.client('lambda', region_name=aws_config['region'], config=boto_config)
                self.logger.print_status("🤖 Bedrock Lambda クライアント初期化完了")
            
            self.logger.print_success(f"✅ AWS接続完了: {aws_config['region']}")
            return True
            
        except Exception as e:
            self.logger.print_error(f"❌ AWS接続エラー: {e}")
            return False
    
    def setup_reviewer_clients(self, aws_region, s3_bucket, dynamodb_table):
        """検品ツール用AWSクライアント初期化"""
        try:
            self.s3_client = boto3.client('s3', region_name=aws_region)
            self.dynamodb = boto3.resource('dynamodb', region_name=aws_region)
            self.dynamodb_table = self.dynamodb.Table(dynamodb_table)
            return "✅ AWS接続成功"
        except NoCredentialsError:
            return "❌ AWS認証情報が設定されていません"
        except Exception as e:
            return f"❌ AWS接続エラー: {e}"
