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
                
                # ConfigManagerから取得したスロット情報とLambda結果を照合
                try:
                    expected_slots = self.config_manager.get_all_time_slots()
                    self.logger.print_status(f"🔍 ConfigManagerから取得した期待スロット数: {len(expected_slots)}")
                    self.logger.print_status(f"🔍 Lambda から返されたコメント数: {len(comments)}")
                    
                    # 不足しているスロットがあれば警告
                    missing_slots = [slot for slot in expected_slots if slot not in comments]
                    if missing_slots:
                        self.logger.print_warning(f"⚠️ 以下のスロットのコメントが不足しています: {missing_slots}")
                        
                except Exception as e:
                    self.logger.print_warning(f"⚠️ ConfigManagerでのスロット照合エラー: {e}")
                
                return comments
            else:
                self.logger.print_warning(f"⚠️ Bedrock生成失敗: {body.get('error')}")
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
