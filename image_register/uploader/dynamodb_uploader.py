#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
DynamoDBUploader - DynamoDB登録機能（完全版）
"""

from botocore.exceptions import ClientError
from common.logger import ColorLogger

class DynamoDBUploader:
    """DynamoDBアップローダー（完全版）"""
    
    def __init__(self, dynamodb_table, logger):
        self.dynamodb_table = dynamodb_table
        self.logger = logger
    
    def register_to_dynamodb(self, aws_metadata) -> bool:
        """DynamoDB登録（完全版）"""
        image_id = aws_metadata['imageId']
        
        try:
            self.logger.print_status(f"📝 DynamoDB登録中: {image_id}")
            
            # DynamoDB登録（boto3のResourceを使用）
            self.dynamodb_table.put_item(Item=aws_metadata)
            self.logger.print_success(f"✅ DynamoDB登録完了: {image_id}")

            return True

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            self.logger.print_error(f"❌ DynamoDB登録エラー ({image_id}): {error_code}")
            return False
        except Exception as e:
            self.logger.print_error(f"❌ DynamoDB登録エラー ({image_id}): {e}")
            return False
