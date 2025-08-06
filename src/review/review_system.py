#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Image Review System - 検品システムのコアロジック
"""

import boto3
import pandas as pd
from PIL import Image
import io
import base64
from datetime import datetime, timedelta
import json
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError, NoCredentialsError
import time
import re
from typing import Dict, Any, List, Optional

# AWS設定
AWS_REGION = 'ap-northeast-1'
S3_BUCKET = 'aight-media-images'
DYNAMODB_TABLE = 'AightMediaImageData'

class ImageReviewSystem:
    """検品システムのコアロジック"""
    
    def __init__(self):
        """検品システム初期化"""
        try:
            self.s3_client = boto3.client('s3', region_name=AWS_REGION)
            self.dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
            self.table = self.dynamodb.Table(DYNAMODB_TABLE)
            self.connection_status = "✅ AWS接続成功"
        except NoCredentialsError:
            self.connection_status = "❌ AWS接続失敗: 認証情報が設定されていません"
        except Exception as e:
            self.connection_status = f"❌ AWS接続失敗: {e}"

    def parse_dynamodb_attribute_value(self, value):
        """DynamoDB AttributeValue形式を通常の値に変換"""
        if isinstance(value, dict):
            if 'S' in value:  # String
                return value['S']
            elif 'N' in value:  # Number
                return float(value['N']) if '.' in value['N'] else int(value['N'])
            elif 'BOOL' in value:  # Boolean
                return value['BOOL']
            elif 'M' in value:  # Map
                return {k: self.parse_dynamodb_attribute_value(v) for k, v in value['M'].items()}
            elif 'L' in value:  # List
                return [self.parse_dynamodb_attribute_value(item) for item in value['L']]
            elif 'SS' in value:  # String Set
                return value['SS']
            elif 'NS' in value:  # Number Set
                return [float(n) if '.' in n else int(n) for n in value['NS']]
            elif 'NULL' in value:  # Null
                return None
        return value

    def get_single_image_latest_data(self, image_id: str) -> Optional[Dict[str, Any]]:
        """個別画像の最新データをDynamoDBから取得"""
        try:
            response = self.table.get_item(Key={'imageId': image_id})
            
            if 'Item' not in response:
                return None

            item = response['Item']
            
            # データ変換（最新データ用）
            processed_item = {
                'imageId': item.get('imageId', ''),
                'genre': item.get('genre', ''),
                'status': item.get('imageState', item.get('status', 'unknown')),
                'created_at': item.get('createdAt', item.get('created_at', '')),
                's3_key': item.get('s3Key', item.get('s3_key', '')),
                'highres_mode': item.get('highres_mode', item.get('HIGHRES_MODE', 'SD15')),
                'generation_mode': item.get('generation_mode', ''),
                'file_size': item.get('file_size', 0),
                'phase1_time': item.get('phase1_time', 0),
                'phase2_time': item.get('phase2_time', 0),
                'total_time': item.get('total_time', 0),
                'phase1_prompt': item.get('phase1_prompt', item.get('PROMPT', '')),
                'phase2_prompt': item.get('phase2_prompt', ''),
                'negative_prompt': item.get('negative_prompt', item.get('NEGATIVE_PROMPT', '')),
                'review_score': item.get('review_score', 0),
                'review_comment': item.get('review_comment', ''),
                'reviewer': item.get('reviewer', ''),
                'reviewed_at': item.get('reviewed_at', ''),
                'postingStage': item.get('postingStage', 'notposted'),
                'preGeneratedComments': item.get('preGeneratedComments', {}),
                'commentGeneratedAt': item.get('commentGeneratedAt', ''),
                'suitableTimeSlots': item.get('suitableTimeSlots', []),
                'recommendedTimeSlot': item.get('recommendedTimeSlot', 'general'),
                'sdParams': item.get('sdParams', {}),
                'raw_item': item
            }

            return processed_item

        except Exception as e:
            return None

    def load_images_efficiently(self, status_filter=None, genre_filter=None, 
                              highres_mode_filter=None, days_back=7) -> List[Dict[str, Any]]:
        """効率的な画像データ読み込み（GSI使用）"""
        try:
            # GSIを使用した効率的な検索
            if status_filter and status_filter != "全て":
                try:
                    # ImageStateIndexを使用
                    response = self.table.query(
                        IndexName='ImageStateIndex',
                        KeyConditionExpression=Key('imageState').eq(status_filter)
                    )
                    items = response.get('Items', [])
                except Exception:
                    # フォールバック：通常のスキャン
                    response = self.table.scan(Limit=100)
                    items = response.get('Items', [])
            else:
                # 全件検索（制限付き）
                response = self.table.scan(Limit=100)
                items = response.get('Items', [])

            # クライアントサイドフィルタリング
            filtered_items = []
            for item in items:
                # 日付フィルタ
                if days_back == 0:
                    today = datetime.now().strftime('%Y%m%d')
                    if today not in item.get('imageId', ''):
                        continue
                elif days_back > 0:
                    # 指定日数以内かチェック
                    found_in_range = False
                    for i in range(days_back + 1):
                        target_date = datetime.now() - timedelta(days=i)
                        date_str = target_date.strftime('%Y%m%d')
                        if date_str in item.get('imageId', ''):
                            found_in_range = True
                            break
                    if not found_in_range:
                        continue

                # ジャンルフィルタ
                if genre_filter and genre_filter != "全て":
                    if item.get('genre') != genre_filter:
                        continue

                # 高画質化モードフィルタ
                if highres_mode_filter and highres_mode_filter != "全て":
                    item_mode = item.get('highres_mode', item.get('HIGHRES_MODE', 'SD15'))
                    if item_mode != highres_mode_filter:
                        continue

                filtered_items.append(item)

            # データ変換（フィールド名の違いに対応）
            processed_items = []
            for item in filtered_items:
                # ステータス値の正規化
                if 'imageState' in item:
                    status_value = item['imageState']
                elif 'status' in item:
                    status_value = item['status']
                else:
                    status_value = 'unknown'

                # S3キーの正規化
                s3_key_value = item.get('s3Key', item.get('s3_key', ''))

                # 作成日時の正規化
                created_at_value = item.get('createdAt', item.get('created_at', ''))

                processed_item = {
                    'imageId': item.get('imageId', ''),
                    'genre': item.get('genre', ''),
                    'status': status_value,
                    'created_at': created_at_value,
                    's3_key': s3_key_value,
                    'highres_mode': item.get('highres_mode', item.get('HIGHRES_MODE', 'SD15')),
                    'generation_mode': item.get('generation_mode', ''),
                    'file_size': item.get('file_size', 0),
                    'phase1_time': item.get('phase1_time', 0),
                    'phase2_time': item.get('phase2_time', 0),
                    'total_time': item.get('total_time', 0),
                    'phase1_prompt': item.get('phase1_prompt', item.get('PROMPT', '')),
                    'phase2_prompt': item.get('phase2_prompt', ''),
                    'negative_prompt': item.get('negative_prompt', item.get('NEGATIVE_PROMPT', '')),
                    'review_score': item.get('review_score', 0),
                    'review_comment': item.get('review_comment', ''),
                    'reviewer': item.get('reviewer', ''),
                    'reviewed_at': item.get('reviewed_at', ''),
                    'postingStage': item.get('postingStage', 'notposted'),
                    'preGeneratedComments': item.get('preGeneratedComments', {}),
                    'commentGeneratedAt': item.get('commentGeneratedAt', ''),
                    'suitableTimeSlots': item.get('suitableTimeSlots', []),
                    'recommendedTimeSlot': item.get('recommendedTimeSlot', ''),
                    'sdParams': item.get('sdParams', {}),
                    'raw_item': item  # 元のアイテムを保持
                }

                processed_items.append(processed_item)

            return processed_items

        except Exception as e:
            return []

    def get_image_from_s3(self, s3_key: str) -> Optional[Image.Image]:
        """S3から画像を取得"""
        try:
            response = self.s3_client.get_object(Bucket=S3_BUCKET, Key=s3_key)
            image_data = response['Body'].read()
            return Image.open(io.BytesIO(image_data))
        except Exception:
            return None

    def extract_prompt_from_nested_structure(self, sd_params: Dict[str, Any]) -> Dict[str, str]:
        """ネストしたsdParams構造からプロンプトを抽出"""
        prompts = {}

        # 複数のプロンプトソースを確認
        possible_sources = [
            # 直接的なフィールド
            ('direct_prompt', sd_params.get('prompt', '')),
            ('direct_PROMPT', sd_params.get('PROMPT', '')),
            # sdxl_unified構造
            ('sdxl_unified', self._extract_from_sdxl_unified(sd_params)),
            # 他の可能な構造
            ('base_prompt', self._extract_from_base_structure(sd_params)),
            ('generation_prompt', self._extract_from_generation_structure(sd_params))
        ]

        for source_name, content in possible_sources:
            if content and isinstance(content, str) and len(content.strip()) > 0:
                prompts[source_name] = content.strip()

        return prompts

    def _extract_from_sdxl_unified(self, sd_params: Dict[str, Any]) -> str:
        """sdxl_unified構造からプロンプトを抽出"""
        try:
            # sdxl_unified -> M -> prompt -> S の階層構造に対応
            sdxl_data = sd_params.get('sdxl_unified', {})
            
            # DynamoDB AttributeValue形式の場合
            if isinstance(sdxl_data, dict) and 'M' in sdxl_data:
                parsed_sdxl = self.parse_dynamodb_attribute_value(sdxl_data)
                return parsed_sdxl.get('prompt', '')
            # 通常の辞書形式の場合
            elif isinstance(sdxl_data, dict):
                return sdxl_data.get('prompt', '')
        except Exception:
            pass
        return ""

    def _extract_from_base_structure(self, sd_params: Dict[str, Any]) -> str:
        """base構造からプロンプトを抽出"""
        try:
            base_data = sd_params.get('base', {})
            if isinstance(base_data, dict) and 'M' in base_data:
                parsed_base = self.parse_dynamodb_attribute_value(base_data)
                return parsed_base.get('prompt', '')
            elif isinstance(base_data, dict):
                return base_data.get('prompt', '')
        except Exception:
            pass
        return ""

    def _extract_from_generation_structure(self, sd_params: Dict[str, Any]) -> str:
        """generation構造からプロンプトを抽出"""
        try:
            # 他の可能な構造パターンを確認
            for key in ['generation', 'params', 'config']:
                if key in sd_params:
                    data = sd_params[key]
                    if isinstance(data, dict) and 'M' in data:
                        parsed_data = self.parse_dynamodb_attribute_value(data)
                        prompt = parsed_data.get('prompt', '')
                        if prompt:
                            return prompt
                    elif isinstance(data, dict):
                        prompt = data.get('prompt', '')
                        if prompt:
                            return prompt
        except Exception:
            pass
        return ""

    def extract_negative_prompt_from_nested_structure(self, sd_params: Dict[str, Any]) -> Dict[str, str]:
        """ネガティブプロンプトを抽出"""
        negative_prompts = {}

        # sdxl_unified構造から抽出
        try:
            sdxl_data = sd_params.get('sdxl_unified', {})
            if isinstance(sdxl_data, dict) and 'M' in sdxl_data:
                parsed_sdxl = self.parse_dynamodb_attribute_value(sdxl_data)
                neg_prompt = parsed_sdxl.get('negative_prompt', '')
                if neg_prompt:
                    negative_prompts['sdxl_unified'] = neg_prompt
        except Exception:
            pass

        # 直接的なフィールドも確認
        direct_neg = sd_params.get('negative_prompt', '') or sd_params.get('NEGATIVE_PROMPT', '')
        if direct_neg:
            negative_prompts['direct'] = direct_neg

        return negative_prompts

    def extract_lora_from_prompt(self, prompt: str) -> List[tuple]:
        """プロンプトからLoRA情報を抽出"""
        if not prompt:
            return []

        try:
            # 修正された正規表現：<lora:name:strength>の形式に対応
            pattern = r'<lora:([^:]+):([^>]+)>'
            matches = re.findall(pattern, prompt)

            # 結果をクリーンアップ
            lora_list = []
            for name, strength in matches:
                clean_name = name.strip()
                clean_strength = strength.strip()
                
                # 空の値や無効な値をスキップ
                if clean_name and clean_strength:
                    try:
                        # 強度が数値として有効か確認
                        float(clean_strength)
                        lora_list.append((clean_name, clean_strength))
                    except ValueError:
                        continue

            return lora_list

        except Exception:
            return []

    def update_image_status(self, image_id: str, status: str, rejection_reasons=None, 
                          other_reason=None, reviewer=None, comments=None, 
                          suitable_slots=None, recommended_slot=None) -> bool:
        """画像ステータス更新（コメント設定自動保存対応版）"""
        try:
            res = self.table.get_item(Key={'imageId': image_id})
            if 'Item' not in res:
                return False

            item = res['Item']

            # GSIキー属性の安全化
            created_at = str(item.get('createdAt', datetime.now().strftime('%Y%m%d%H%M%S')))
            actual_post_time = created_at
            now_iso = datetime.now().isoformat()

            update_expr = "SET imageState = :state, postingStage = :ps, createdAt = :ca, actualPostTime = :apt, reviewed_at = :reviewed"
            expr_vals = {
                ':state': "rejected" if status == "rejected" else ("reviewed_approved" if status == "reviewed_approved" else status),
                ':ps': "notposted" if status == "rejected" else ("ready_for_posting" if status == "reviewed_approved" else item.get('postingStage', 'notposted')),
                ':ca': created_at,
                ':apt': actual_post_time,
                ':reviewed': now_iso
            }

            expr_names = {}

            # コメント・スロット設定を自動保存
            if comments or suitable_slots or recommended_slot:
                if comments:
                    update_expr += ", preGeneratedComments = :comments"
                    expr_vals[':comments'] = comments
                if suitable_slots:
                    update_expr += ", suitableTimeSlots = :slots"
                    expr_vals[':slots'] = suitable_slots
                if recommended_slot:
                    update_expr += ", recommendedTimeSlot = :recommended"
                    expr_vals[':recommended'] = recommended_slot
                
                update_expr += ", commentGeneratedAt = :comment_time"
                expr_vals[':comment_time'] = now_iso

            # 却下理由の処理
            if status == "rejected":
                reasons = []
                if rejection_reasons and len(rejection_reasons) > 0:
                    reasons.extend(rejection_reasons)
                if other_reason and other_reason.strip():
                    reasons.append(other_reason.strip())

                if reasons:
                    update_expr += ", rejectionReasons = :reasons"
                    expr_vals[':reasons'] = reasons

            # TTL設定
            ttl_ts = int(datetime.now().timestamp()) + 30 * 24 * 60 * 60
            update_expr += ", #ttl = :ttl"
            expr_vals[':ttl'] = ttl_ts
            expr_names['#ttl'] = 'TTL'

            # レビュー者
            if reviewer:
                update_expr += ", reviewer = :rv"
                expr_vals[':rv'] = reviewer

            params = {
                'Key': {'imageId': image_id},
                'UpdateExpression': update_expr,
                'ExpressionAttributeValues': expr_vals
            }

            if expr_names:
                params['ExpressionAttributeNames'] = expr_names

            self.table.update_item(**params)

            return True

        except Exception:
            return False

    def get_statistics(self, days_back=7) -> Optional[Dict[str, Any]]:
        """統計情報取得"""
        try:
            response = self.table.scan(Limit=500)
            items = response['Items']
            total_count = len(items)

            status_counts = {}
            highres_mode_counts = {}
            genre_counts = {}
            ttl_items_count = 0

            for item in items:
                # ステータス統計
                status = item.get('imageState', item.get('status', 'unknown'))
                status_counts[status] = status_counts.get(status, 0) + 1

                # モード統計
                mode = item.get('highres_mode', item.get('HIGHRES_MODE', 'SD15'))
                highres_mode_counts[mode] = highres_mode_counts.get(mode, 0) + 1

                # ジャンル統計
                genre = item.get('genre', 'unknown')
                genre_counts[genre] = genre_counts.get(genre, 0) + 1

                # TTL設定済み画像の統計
                if 'TTL' in item:
                    ttl_items_count += 1

            return {
                'total_count': total_count,
                'status_counts': status_counts,
                'highres_mode_counts': highres_mode_counts,
                'genre_counts': genre_counts,
                'ttl_items_count': ttl_items_count,
                'period_days': days_back
            }

        except Exception:
            return None
