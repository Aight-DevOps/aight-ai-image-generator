#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ImageReviewSystem - メイン検品システムクラス
完全機能版（リファクタリング前機能復活）
"""

import streamlit as st
import boto3
import pandas as pd
from PIL import Image
import io
import json
import time
import re
from datetime import datetime, timedelta
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError, NoCredentialsError

from common.logger import ColorLogger
from common.aws_client import AWSClientManager

# AWS設定
AWS_REGION = 'ap-northeast-1'
S3_BUCKET = 'aight-media-images'
DYNAMODB_TABLE = 'AightMediaImageData'

class ImageReviewSystem:
    """検品システムメインクラス（完全機能版）"""
    
    def __init__(self):
        """検品システム初期化"""
        try:
            self.s3_client = boto3.client('s3', region_name=AWS_REGION)
            self.dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
            self.table = self.dynamodb.Table(DYNAMODB_TABLE)
            self.connection_status = "✅ AWS接続成功"
        except NoCredentialsError:
            st.error("❌ AWS認証情報が設定されていません")
            self.connection_status = "❌ AWS接続失敗"
        except Exception as e:
            st.error(f"❌ AWS接続エラー: {e}")
            self.connection_status = "❌ AWS接続失敗"
    
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

    def get_single_image_latest_data(self, image_id):
        """個別画像の最新データをDynamoDBから取得"""
        try:
            st.write(f"🔄 画像 {image_id} の最新データを取得中...")
            
            response = self.table.get_item(Key={'imageId': image_id})
            
            if 'Item' not in response:
                st.warning(f"⚠️ 画像 {image_id} がDynamoDBで見つかりません")
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
            
            st.success(f"✅ 最新データ取得完了: {image_id}")
            return processed_item
        
        except Exception as e:
            st.error(f"❌ 個別画像データ取得エラー: {e}")
            return None

    def load_images_efficiently(self, status_filter=None, genre_filter=None, highres_mode_filter=None, days_back=7):
        """効率的な画像データ読み込み（GSI使用）"""
        st.write("---")
        st.write("## 🔍 検索期間変更による画像検索実行")
        
        try:
            # GSIを使用した効率的な検索
            if status_filter and status_filter != "全て":
                try:
                    # ImageStateIndexを使用
                    response = self.table.query(
                        IndexName='ImageStateIndex',
                        KeyConditionExpression=Key('imageState').eq(status_filter)
                    )
                    st.write(f"✅ ImageStateIndex使用: imageState={status_filter}")
                    items = response.get('Items', [])
                    st.write(f"**GSI検索結果**: {len(items)}件")
                except Exception as e:
                    st.error(f"GSI検索エラー: {e}")
                    # フォールバック：通常のスキャン
                    response = self.table.scan(Limit=100)
                    items = response.get('Items', [])
                    st.write(f"**フォールバック結果**: {len(items)}件")
            else:
                # 全件検索（制限付き）
                response = self.table.scan(Limit=100)
                items = response.get('Items', [])
                st.write(f"**全件検索結果**: {len(items)}件")

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

            st.write(f"**フィルタ後結果**: {len(filtered_items)}件")

            # データ変換
            processed_items = []
            for item in filtered_items:
                # ステータス値の正規化
                if 'imageState' in item:
                    status_value = item['imageState']
                elif 'status' in item:
                    status_value = item['status']
                else:
                    status_value = 'unknown'

                processed_item = {
                    'imageId': item.get('imageId', ''),
                    'genre': item.get('genre', ''),
                    'status': status_value,
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
                    'recommendedTimeSlot': item.get('recommendedTimeSlot', ''),
                    'sdParams': item.get('sdParams', {}),
                    'raw_item': item  # 元のアイテムを保持
                }
                processed_items.append(processed_item)

            st.success(f"✅ 検索完了: {len(processed_items)}件")
            return processed_items

        except Exception as e:
            st.error(f"❌ 検索エラー: {e}")
            return []

    def get_image_from_s3(self, s3_key):
        """S3から画像を取得"""
        try:
            response = self.s3_client.get_object(Bucket=S3_BUCKET, Key=s3_key)
            image_data = response['Body'].read()
            return Image.open(io.BytesIO(image_data))
        except Exception as e:
            st.error(f"❌ S3画像取得エラー: {e}")
            return None

    def extract_prompt_from_nested_structure(self, sd_params):
        """ネストしたsdParams構造からプロンプトを抽出"""
        prompts = {}
        
        possible_sources = [
            ('direct_prompt', sd_params.get('prompt', '')),
            ('direct_PROMPT', sd_params.get('PROMPT', '')),
            ('sdxl_unified', self._extract_from_sdxl_unified(sd_params)),
            ('base_prompt', self._extract_from_base_structure(sd_params)),
            ('generation_prompt', self._extract_from_generation_structure(sd_params))
        ]
        
        for source_name, content in possible_sources:
            if content and isinstance(content, str) and len(content.strip()) > 0:
                prompts[source_name] = content.strip()
        
        return prompts

    def _extract_from_sdxl_unified(self, sd_params):
        """sdxl_unified構造からプロンプトを抽出"""
        try:
            sdxl_data = sd_params.get('sdxl_unified', {})
            
            if isinstance(sdxl_data, dict) and 'M' in sdxl_data:
                parsed_sdxl = self.parse_dynamodb_attribute_value(sdxl_data)
                return parsed_sdxl.get('prompt', '')
            elif isinstance(sdxl_data, dict):
                return sdxl_data.get('prompt', '')
        except Exception as e:
            st.warning(f"sdxl_unified構造の解析エラー: {e}")
        
        return ""

    def _extract_from_base_structure(self, sd_params):
        """base構造からプロンプトを抽出"""
        try:
            base_data = sd_params.get('base', {})
            
            if isinstance(base_data, dict) and 'M' in base_data:
                parsed_base = self.parse_dynamodb_attribute_value(base_data)
                return parsed_base.get('prompt', '')
            elif isinstance(base_data, dict):
                return base_data.get('prompt', '')
        except Exception as e:
            st.warning(f"base構造の解析エラー: {e}")
        
        return ""

    def _extract_from_generation_structure(self, sd_params):
        """generation構造からプロンプトを抽出"""
        try:
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
        except Exception as e:
            st.warning(f"generation構造の解析エラー: {e}")
        
        return ""

    def extract_negative_prompt_from_nested_structure(self, sd_params):
        """ネガティブプロンプトを抽出"""
        negative_prompts = {}
        
        try:
            sdxl_data = sd_params.get('sdxl_unified', {})
            if isinstance(sdxl_data, dict) and 'M' in sdxl_data:
                parsed_sdxl = self.parse_dynamodb_attribute_value(sdxl_data)
                neg_prompt = parsed_sdxl.get('negative_prompt', '')
                if neg_prompt:
                    negative_prompts['sdxl_unified'] = neg_prompt
        except Exception as e:
            st.warning(f"ネガティブプロンプト抽出エラー: {e}")
        
        direct_neg = sd_params.get('negative_prompt', '') or sd_params.get('NEGATIVE_PROMPT', '')
        if direct_neg:
            negative_prompts['direct'] = direct_neg
        
        return negative_prompts

    def extract_lora_from_prompt(self, prompt):
        """プロンプトからLoRA情報を抽出"""
        if not prompt:
            return []
        
        try:
            pattern = r'<lora:([^>]+?):([\d.]+)>'
            matches = re.findall(pattern, prompt)
            
            lora_list = []
            for name, strength in matches:
                clean_name = name.strip()
                clean_strength = strength.strip()
                
                if clean_name and clean_strength:
                    try:
                        float(clean_strength)
                        lora_list.append((clean_name, clean_strength))
                    except ValueError:
                        continue
            
            return lora_list
        except Exception as e:
            st.error(f"LoRA抽出エラー: {e}")
            return []

    def display_lora_info(self, sd_params, all_prompts):
        """LoRA情報をテーブル形式で表示"""
        st.subheader("🔧 使用LoRA詳細")
        
        all_lora_matches = []
        lora_sources = []
        
        for source_name, prompt in all_prompts.items():
            if prompt:
                lora_matches = self.extract_lora_from_prompt(prompt)
                if lora_matches:
                    all_lora_matches.extend(lora_matches)
                    lora_sources.extend([source_name] * len(lora_matches))
        
        if all_lora_matches:
            table_data = {
                "LoRA名": [name for name, strength in all_lora_matches],
                "強度": [strength for name, strength in all_lora_matches],
                "取得元": lora_sources
            }
            
            df = pd.DataFrame(table_data)
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.write(f"**総LoRA数**: {len(all_lora_matches)}個")
        else:
            st.text("LoRA使用なし")

    def display_enhanced_image_metadata(self, image_data):
        """拡張された画像メタデータの表示"""
        st.subheader("📊 画像メタデータ")
        
        # 基本情報
        st.write("**📅 基本情報**")
        created_at = image_data.get('created_at', '')
        if created_at:
            try:
                if len(created_at) == 14:  # YYYYMMDDHHmmss format
                    formatted_date = f"{created_at[:4]}/{created_at[4:6]}/{created_at[6:8]} {created_at[8:10]}:{created_at[10:12]}"
                else:
                    formatted_date = created_at
                st.write(f"生成日時: {formatted_date}")
            except:
                st.write(f"生成日時: {created_at}")
        
        st.write(f"ジャンル: {image_data.get('genre', 'unknown')}")
        
        # 画像生成パラメータ
        sd_params = image_data.get('sdParams', {})
        if sd_params:
            st.write("**🎯 画像生成パラメータ**")
            
            try:
                sdxl_data = sd_params.get('sdxl_unified', {})
                
                if isinstance(sdxl_data, dict) and 'M' in sdxl_data:
                    parsed_sdxl = self.parse_dynamodb_attribute_value(sdxl_data)
                    
                    steps = parsed_sdxl.get('steps', 'unknown')
                    cfg_scale = parsed_sdxl.get('cfg_scale', 'unknown')
                    sampler = parsed_sdxl.get('sampler', 'unknown')
                    width = parsed_sdxl.get('width', 'unknown')
                    height = parsed_sdxl.get('height', 'unknown')
                    
                    st.write(f"ステップ数: {steps}")
                    st.write(f"CFG Scale: {cfg_scale}")
                    st.write(f"Sampler: {sampler}")
                    st.write(f"解像度: {width}x{height}")
                
                elif isinstance(sdxl_data, dict):
                    st.write(f"ステップ数: {sdxl_data.get('steps', 'unknown')}")
                    st.write(f"CFG Scale: {sdxl_data.get('cfg_scale', 'unknown')}")
                    st.write(f"Sampler: {sdxl_data.get('sampler', 'unknown')}")
                    st.write(f"解像度: {sdxl_data.get('width', 'unknown')}x{sdxl_data.get('height', 'unknown')}")
                
                else:
                    st.write(f"ステップ数: {sd_params.get('steps', 'unknown')}")
                    st.write(f"CFG Scale: {sd_params.get('cfg_scale', 'unknown')}")
                    st.write(f"Sampler: {sd_params.get('sampler', 'unknown')}")
                
            except Exception as e:
                st.warning(f"パラメータ抽出エラー: {e}")
                st.write(f"ステップ数: {sd_params.get('steps', 'unknown')}")
                st.write(f"CFG Scale: {sd_params.get('cfg_scale', 'unknown')}")
                st.write(f"Sampler: {sd_params.get('sampler', 'unknown')}")
            
            all_prompts = self.extract_prompt_from_nested_structure(sd_params)
            self.display_lora_info(sd_params, all_prompts)
            
            # プロンプト情報
            if st.expander("📝 生成プロンプト詳細（全量表示・マルチソース対応）"):
                if all_prompts:
                    main_prompt = ""
                    main_source = ""
                    for source, content in all_prompts.items():
                        if content and len(content) > len(main_prompt):
                            main_prompt = content
                            main_source = source
                    
                    if main_prompt:
                        st.write(f"**メインプロンプト** (取得元: {main_source})")
                        st.text_area(
                            "プロンプト全量", 
                            value=main_prompt, 
                            height=200, 
                            disabled=True,
                            key="main_prompt_display"
                        )
                        st.write(f"**文字数**: {len(main_prompt)}文字")
                        
                        if len(all_prompts) > 1:
                            st.write("**その他のプロンプトソース:**")
                            for source, content in all_prompts.items():
                                if content and content != main_prompt:
                                    st.write(f"- {source}: {len(content)}文字")
                    else:
                        st.warning("プロンプトが見つかりません")
                else:
                    st.warning("プロンプトが見つかりません")
                
                # ネガティブプロンプト
                all_negative_prompts = self.extract_negative_prompt_from_nested_structure(sd_params)
                if all_negative_prompts:
                    main_negative = ""
                    main_neg_source = ""
                    for source, content in all_negative_prompts.items():
                        if content and len(content) > len(main_negative):
                            main_negative = content
                            main_neg_source = source
                    
                    if main_negative:
                        st.write(f"**ネガティブプロンプト** (取得元: {main_neg_source})")
                        st.text_area(
                            "ネガティブプロンプト全量", 
                            value=main_negative, 
                            height=150, 
                            disabled=True,
                            key="main_negative_display"
                        )
                        st.write(f"**文字数**: {len(main_negative)}文字")

    def render_integrated_comment_timeslot_area(self, image_data):
        """統合された時間帯別コメント・スロット設定エリア"""
        if 'reset_trigger' not in st.session_state:
            st.session_state.reset_trigger = 0

        with st.expander("🕐 時間帯別コメント・スロット設定", expanded=False):
            time_slots = {
                "early_morning": "早朝 (6:00-8:00)",
                "morning": "朝 (8:00-9:00)",
                "lunch": "昼 (11:00-13:00)",
                "evening": "夕方 (13:00-21:00)",
                "night": "夜 (21:00-22:30)",
                "mid_night": "深夜 (22:30-00:59)",
                "general": "一般時間帯"
            }

            pre_comments = image_data.get('preGeneratedComments', {})
            suitable_slots = image_data.get('suitableTimeSlots', [])
            recommended_slot = image_data.get('recommendedTimeSlot', 'general')

            current_image_id = image_data.get('imageId', '')
            
            if ('current_editing_image_id' not in st.session_state or 
                st.session_state.current_editing_image_id != current_image_id):
                
                st.session_state.current_editing_image_id = current_image_id
                st.session_state.updated_comments = pre_comments.copy()
                st.session_state.updated_suitable = suitable_slots.copy()
                st.session_state.updated_recommended = recommended_slot
                
                st.info(f"✨ 画像 {current_image_id} の最新コメント・スロット設定を読み込みました")

            for slot_key, slot_name in time_slots.items():
                st.write(f"### {slot_name}")
                col1, col2, col3 = st.columns([3, 1, 1])

                with col2:
                    suitable_key = f"suitable_{slot_key}"
                    suitable_selected = st.button(
                        "✓適合" if slot_key in st.session_state.updated_suitable else "適合",
                        key=suitable_key,
                        type="primary" if slot_key in st.session_state.updated_suitable else "secondary"
                    )

                    if suitable_selected:
                        if slot_key in st.session_state.updated_suitable:
                            st.session_state.updated_suitable.remove(slot_key)
                        else:
                            st.session_state.updated_suitable.append(slot_key)
                        st.rerun()

                with col3:
                    recommended_key = f"recommended_{slot_key}"
                    recommended_selected = st.button(
                        "✓推奨" if slot_key == st.session_state.updated_recommended else "推奨",
                        key=recommended_key,
                        type="primary" if slot_key == st.session_state.updated_recommended else "secondary"
                    )

                    if recommended_selected:
                        st.session_state.updated_recommended = slot_key
                        st.rerun()

                current_comment = st.session_state.updated_comments.get(slot_key, "")
                initial_value = "" if st.session_state.get('pending_reset', False) else current_comment
                
                updated_comment = st.text_area(
                    f"{slot_name}用コメント",
                    value=initial_value,
                    height=80,
                    key=f"comment_{slot_key}_{current_image_id}_{st.session_state.reset_trigger}",
                    label_visibility="collapsed"
                )

                st.session_state.updated_comments[slot_key] = updated_comment
                st.divider()

            if st.session_state.get('pending_reset', False):
                st.session_state.pending_reset = False

            if st.button("🔄 設定をリセット", use_container_width=True):
                st.session_state.updated_comments = {}
                st.session_state.updated_suitable = []
                st.session_state.updated_recommended = 'general'
                
                image_id = image_data['imageId']
                if 'pending_updates' in st.session_state:
                    if image_id in st.session_state.pending_updates:
                        del st.session_state.pending_updates[image_id]
                
                st.session_state.reset_trigger += 1
                st.session_state.pending_reset = True
                
                st.success("✅ すべての設定をリセットしました")
                st.rerun()

            st.success("✨ 設定は承認・却下ボタン押下時に自動保存されます")

        return st.session_state.updated_comments, st.session_state.updated_suitable, st.session_state.updated_recommended

    def clear_comment_settings_on_image_change(self):
        """画像切り替え時のコメント設定クリア"""
        if 'current_editing_image_id' in st.session_state:
            del st.session_state.current_editing_image_id

        if 'updated_comments' in st.session_state:
            st.session_state.updated_comments = {}

        keys_to_clear = []
        for key in list(st.session_state.keys()):
            if key.startswith('comment_'):
                keys_to_clear.append(key)
        
        for key in keys_to_clear:
            del st.session_state[key]

        if 'reset_trigger' not in st.session_state:
            st.session_state.reset_trigger = 0
        st.session_state.reset_trigger += 1

    def render_rejection_reason_tags(self, selected_image):
        """却下理由選択のタグ風UI"""
        st.subheader("🏷️ 却下理由選択")
        
        REJECTION_REASONS = [
            "四肢欠損", "骨格崩れ", "手指崩れ", "足崩れ",
            "生成失敗", "顔面崩壊", "構図不良", "服装不適切",
            "露出過度", "色彩異常"
        ]

        if 'selected_reasons' not in st.session_state:
            st.session_state.selected_reasons = []

        cols = st.columns(5)
        for i, reason in enumerate(REJECTION_REASONS):
            col = cols[i % 5]
            with col:
                is_selected = reason in st.session_state.selected_reasons
                if st.button(
                    reason,
                    key=f"reason_{i}",
                    type="primary" if is_selected else "secondary",
                    use_container_width=True
                ):
                    if is_selected:
                        st.session_state.selected_reasons.remove(reason)
                    else:
                        st.session_state.selected_reasons.append(reason)
                    st.rerun()

        st.write("**その他理由：**")
        other_reason = st.text_input(
            "その他の却下理由",
            key="other_reason",
            label_visibility="collapsed",
            placeholder="選択肢にない場合は自由入力してください"
        )

        if st.session_state.selected_reasons or other_reason:
            st.write("**選択された却下理由：**")
            all_reasons = st.session_state.selected_reasons.copy()
            if other_reason:
                all_reasons.append(other_reason)
            for reason in all_reasons:
                st.markdown(f"- {reason}")

        return st.session_state.selected_reasons, other_reason

    def update_image_status(self, image_id, status, rejection_reasons=None, other_reason=None, reviewer=None):
        """画像ステータス更新"""
        try:
            res = self.table.get_item(Key={'imageId': image_id})
            if 'Item' not in res:
                st.error('画像データが見つかりません')
                return False

            item = res['Item']
            created_at = str(item.get('createdAt', datetime.now().strftime('%Y%m%d%H%M%S')))
            actual_post_time = created_at
            now_iso = datetime.now().isoformat()

            update_expr = "SET imageState = :state, postingStage = :ps, createdAt = :ca, actualPostTime = :apt, reviewed_at = :reviewed"
            expr_vals = {
                ':state': "rejected" if status == "rejected" else ("reviewed_approved" if status == "reviewed_approved" else status),
                # 却下時はアーカイブ状態に変更
                ':ps': "archived" if status == "rejected" else ("ready_for_posting" if status == "reviewed_approved" else item.get('postingStage', 'notposted')),
                ':ca': created_at,
                ':apt': actual_post_time,
                ':reviewed': now_iso
            }
            expr_names = {}

            # 現在のコメント・スロット設定を自動保存
            current_comments = st.session_state.get('updated_comments', {})
            current_suitable = st.session_state.get('updated_suitable', [])
            current_recommended = st.session_state.get('updated_recommended', 'general')

            if current_comments or current_suitable or current_recommended != 'general':
                update_expr += ", preGeneratedComments = :comments"
                update_expr += ", suitableTimeSlots = :slots"
                update_expr += ", recommendedTimeSlot = :recommended"
                update_expr += ", commentGeneratedAt = :comment_time"
                
                expr_vals.update({
                    ':comments': current_comments,
                    ':slots': current_suitable,
                    ':recommended': current_recommended,
                    ':comment_time': now_iso
                })
                st.success("✅ 現在のコメント・スロット設定を自動保存しました")

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
                    st.success(f"✅ 却下理由を保存します: {reasons}")
                else:
                    st.warning("⚠️ 却下理由が選択されていませんが、処理を続行します")

            # TTL設定
            ttl_ts = int(datetime.now().timestamp()) + 30 * 24 * 60 * 60
            update_expr += ", #ttl = :ttl"
            expr_vals[':ttl'] = ttl_ts
            expr_names['#ttl'] = 'TTL'

            if reviewer:
                update_expr += ", reviewer = :rv"
                expr_vals[':rv'] = reviewer

            params = {'Key': {'imageId': image_id},
                     'UpdateExpression': update_expr,
                     'ExpressionAttributeValues': expr_vals}
            
            if expr_names:
                params['ExpressionAttributeNames'] = expr_names

            self.table.update_item(**params)

            self.clear_comment_settings_on_image_change()
            st.info("🧹 承認・却下処理後にコメント設定をクリアしました")

            # 却下理由の選択状態もクリア
            if 'selected_reasons' in st.session_state:
                del st.session_state.selected_reasons
            if 'other_reason' in st.session_state:
                del st.session_state.other_reason
            st.info("🧹 却下理由の選択状態もクリアしました")

            st.success("更新が完了しました")
            return True

        except Exception as e:
            st.error(f"更新エラー: {e}")
            return False

    def get_statistics(self, days_back=7):
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
                status = item.get('imageState', item.get('status', 'unknown'))
                status_counts[status] = status_counts.get(status, 0) + 1

                mode = item.get('highres_mode', item.get('HIGHRES_MODE', 'SD15'))
                highres_mode_counts[mode] = highres_mode_counts.get(mode, 0) + 1

                genre = item.get('genre', 'unknown')
                genre_counts[genre] = genre_counts.get(genre, 0) + 1

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

        except Exception as e:
            st.error(f"❌ 統計取得エラー: {e}")
            return None
