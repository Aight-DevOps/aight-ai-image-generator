#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
DynamoDBUploader - DynamoDB登録機能
- register_to_dynamodb: アイテム登録
"""

from common.logger import ColorLogger
from botocore.exceptions import ClientError

class DynamoDBUploader:
    """DynamoDB 登録管理クラス"""

    def __init__(self, table, logger):
        self.table = table
        self.logger = logger

    def register_to_dynamodb(self, item):
        """DynamoDB put_item"""
        try:
            self.logger.print_status(f"📝 DynamoDB登録: {item['imageId']}")
            # 重複チェック
            resp = self.table.get_item(Key={'imageId':item['imageId']})
            if 'Item' in resp:
                self.logger.print_warning("既存、スキップ")
                return False
            self.table.put_item(Item=item)
            self.logger.print_success("✅ DynamoDB登録完了")
            return True
        except Exception as e:
            self.logger.print_error(f"DynamoDB登録エラー: {e}")
            return False
