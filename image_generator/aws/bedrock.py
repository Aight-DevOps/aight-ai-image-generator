#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
BedrockManager - Bedrockコメント生成機能
- generate_all_timeslot_comments: 全時間帯コメント一括生成
"""

import time
import json
from common.logger import ColorLogger
from botocore.exceptions import ClientError

class BedrockManager:
    """Bedrockコメント生成管理クラス"""

    def __init__(self, lambda_client, function_name, local_mode=False):
        """
        Args:
            lambda_client: boto3.lambda client
            function_name: Bedrock Lambda 関数名
            local_mode: ローカルモード時はスキップ
        """
        self.lambda_client = lambda_client
        self.function_name = function_name
        self.logger = ColorLogger()
        self.local_mode = local_mode

    def generate_all_timeslot_comments(self, image_metadata: dict) -> dict:
        """
        Bedrock Lambda 呼び出しによる全時間帯コメント生成
        Args:
            image_metadata: 画像メタデータ dict
        Returns:
            {timeslot: comment} dict
        """
        if self.local_mode or not self.lambda_client:
            self.logger.print_status("ローカルモードまたはBedrock無効: コメント生成スキップ")
            return {}

        try:
            self.logger.print_status("🤖 Bedrockで全時間帯コメント生成中...")
            time.sleep(1)  # API制限対策
            
            response = self.lambda_client.invoke(
                FunctionName=self.function_name,
                InvocationType='RequestResponse',
                Payload=json.dumps({
                    'generation_mode': 'all_timeslots',
                    'image_metadata': image_metadata
                })
            )
            
            payload = json.loads(response['Payload'].read())
            body = json.loads(payload.get('body', '{}'))
            
            if body.get('success'):
                comments = body.get('all_comments', {})
                self.logger.print_success(f"🤖 コメント生成完了: {len(comments)}件")
                time.sleep(2)  # 連続呼び出し制限対策
                return comments
            else:
                self.logger.print_warning(f"⚠️ コメント生成失敗: {body.get('error')}")
                return {}
                
        except ClientError as e:
            code = e.response.get('Error', {}).get('Code', 'Unknown')
            if code == 'ThrottlingException':
                self.logger.print_warning("⚠️ Bedrock API制限に達しました。画像生成は継続します。")
                time.sleep(5)  # スロットリング時は長めに待機
            elif code == 'TooManyRequestsException':
                self.logger.print_warning("⚠️ Lambda同時実行制限に達しました。画像生成は継続します。")
                time.sleep(3)
            else:
                self.logger.print_warning(f"⚠️ Bedrock ClientError: {code}")
            return {}
            
        except Exception as e:
            self.logger.print_error(f"❌ Bedrockコメント生成エラー: {e}")
            return {}
