#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
BedrockManager - Bedrockコメント生成専用クラス
"""

import json
import time
from typing import Dict, List, Optional
from common.logger import ColorLogger

class BedrockManager:
    """Bedrockコメント生成管理クラス"""
    
    def __init__(self, lambda_client, logger: ColorLogger, config: dict):
        self.lambda_client = lambda_client
        self.logger = logger
        self.config = config
        self.lambda_function_name = config.get('bedrock_features', {}).get('lambda_function_name', 'aight_bedrock_comment_generator')
        
        # デバッグログ追加
        self.logger.print_status(f"🔍 BedrockManager DEBUG: lambda_function_name = {self.lambda_function_name}")
        self.logger.print_status(f"🔍 BedrockManager DEBUG: lambda_client = {lambda_client is not None}")

    def generate_all_timeslot_comments(self, image_metadata: dict) -> Dict[str, str]:
        """全時間帯のコメントを生成"""

        # デバッグログ追加
        self.logger.print_status("🔍 BedrockManager.generate_all_timeslot_comments 呼び出し開始")
        self.logger.print_status(f"🔍 image_metadata keys: {list(image_metadata.keys())}")
        
        try:
            self.logger.print_status("🤖 Bedrock全時間帯コメント生成開始...")
            
            response = self.lambda_client.invoke(
                FunctionName=self.lambda_function_name,
                InvocationType='RequestResponse',
                Payload=json.dumps({
                    'generation_mode': 'all_timeslots',
                    'image_metadata': image_metadata
                })
            )
            
            result = json.loads(response['Payload'].read())
            body = json.loads(result['body'])
            
            if body.get('success'):
                comments = body.get('all_comments', {})
                self.logger.print_success(f"🤖 Bedrock全時間帯コメント生成完了: {len(comments)}件")
                return comments
            else:
                self.logger.print_warning(f"⚠️ Bedrock生成失敗: {body.get('error')}")
                return {}
                
        except Exception as e:
            self.logger.print_error(f"❌ Bedrock呼び出しエラー: {e}")
            return {}
    
    def generate_single_comment(self, image_metadata: dict, time_slot: str) -> str:
        """単一時間帯コメント生成"""
        # 実装省略
        pass
