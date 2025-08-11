#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
BedrockManager - Bedrockコメント生成専用クラス
"""

import json
import time
from typing import Dict, List, Optional

from common.logger import ColorLogger
from common.config_manager import ConfigManager

class BedrockManager:
    """Bedrockコメント生成管理クラス"""

    def __init__(self, lambda_client, logger: ColorLogger, config: dict, config_manager: ConfigManager):
        self.lambda_client = lambda_client
        self.logger = logger
        self.config = config
        self.config_manager = config_manager
        self.lambda_function_name = config.get('bedrock_features', {}).get('lambda_function_name', 'aight_bedrock_comment_generator')

        # デバッグログ追加
        self.logger.print_status(f"🔍 BedrockManager DEBUG: lambda_function_name = {self.lambda_function_name}")
        self.logger.print_status(f"🔍 BedrockManager DEBUG: lambda_client = {lambda_client is not None}")
        self.logger.print_status(f"🔍 BedrockManager DEBUG: config_manager = {config_manager is not None}")

    def generate_all_timeslot_comments(self, image_metadata: dict) -> Dict[str, str]:
        """全時間帯のコメントを生成"""
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
            
            # レスポンスの読み取りと検証
            response_payload_raw = response['Payload'].read()
            response_payload = json.loads(response_payload_raw)
            
            # デバッグ用：レスポンス全体をログ出力
            self.logger.print_status(f"🔍 Lambda response keys: {list(response_payload.keys())}")
            
            # 'body'キーの存在確認
            if 'body' not in response_payload:
                self.logger.print_error("❌ Lambda response missing 'body' key")
                self.logger.print_error(f"🔍 Full response: {response_payload}")
                return {}
                
            body = json.loads(response_payload['body'])
            
            if body.get('success'):
                comments = body.get('all_comments', {})
                self.logger.print_success(f"🤖 Bedrock全時間帯コメント生成完了: {len(comments)}件")
                return comments
            else:
                self.logger.print_warning(f"⚠️ Bedrock生成失敗: {body.get('error')}")
                return {}
                
        except json.JSONDecodeError as e:
            self.logger.print_error(f"❌ JSON parsing error: {e}")
            return {}
        except KeyError as e:
            self.logger.print_error(f"❌ Missing key in response: {e}")
            return {}
        except Exception as e:
            self.logger.print_error(f"❌ Bedrock呼び出しエラー: {e}")
            return {}


    def generate_single_comment(self, image_metadata: dict, time_slot: str) -> str:
        """単一時間帯コメント生成"""
        try:
            self.logger.print_status(f"🤖 Bedrock単一スロットコメント生成開始: {time_slot}")

            response = self.lambda_client.invoke(
                FunctionName=self.lambda_function_name,
                InvocationType='RequestResponse',
                Payload=json.dumps({
                    'generation_mode': 'single',
                    'time_slot': time_slot,
                    'image_metadata': image_metadata
                })
            )

            result = json.loads(response['Payload'].read())
            body = json.loads(result['body'])

            if body.get('success'):
                comment = body.get('comment', '')
                self.logger.print_success(f"🤖 Bedrock単一スロットコメント生成完了: {time_slot}")
                return comment
            else:
                self.logger.print_warning(f"⚠️ Bedrock単一スロット生成失敗: {body.get('error')}")
                return ''

        except Exception as e:
            self.logger.print_error(f"❌ Bedrock単一スロット呼び出しエラー ({time_slot}): {e}")
            return ''

    def get_available_time_slots(self) -> List[str]:
        """利用可能な時間帯スロット一覧を取得"""
        try:
            return self.config_manager.get_all_time_slots()
        except Exception as e:
            self.logger.print_error(f"❌ 利用可能スロット取得エラー: {e}")
            # フォールバック：静的な11スロット
            return [
                'early_morning', 'morning', 'late_morning', 'lunch',
                'afternoon', 'pre_evening', 'evening', 'night',
                'late_night', 'mid_night', 'general'
            ]

    def validate_time_slot(self, time_slot: str) -> bool:
        """時間帯スロットの妥当性チェック"""
        try:
            available_slots = self.get_available_time_slots()
            return time_slot in available_slots
        except Exception as e:
            self.logger.print_error(f"❌ スロット妥当性チェックエラー: {e}")
            return False
