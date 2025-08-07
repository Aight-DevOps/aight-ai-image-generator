import streamlit as st
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

# AWS設定
AWS_REGION = 'ap-northeast-1'
S3_BUCKET = 'aight-media-images'
DYNAMODB_TABLE = 'AightMediaImageData'

class ImageReviewSystem:
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
        """個別画像の最新データをDynamoDBから取得（新機能）"""
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
        """効率的な画像データ読み込み（GSI使用）- 検索期間変更専用"""
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

            st.success(f"✅ 検索完了: {len(processed_items)}件")
            return processed_items

        except Exception as e:
            st.error(f"❌ 検索エラー: {e}")
            st.exception(e)
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
        """ネストしたsdParams構造からプロンプトを抽出（DynamoDB AttributeValue対応）"""
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

    def _extract_from_sdxl_unified(self, sd_params):
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
        except Exception as e:
            st.warning(f"generation構造の解析エラー: {e}")
        
        return ""

    def extract_negative_prompt_from_nested_structure(self, sd_params):
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
        except Exception as e:
            st.warning(f"ネガティブプロンプト抽出エラー: {e}")
        
        # 直接的なフィールドも確認
        direct_neg = sd_params.get('negative_prompt', '') or sd_params.get('NEGATIVE_PROMPT', '')
        if direct_neg:
            negative_prompts['direct'] = direct_neg
        
        return negative_prompts

    def extract_lora_from_prompt(self, prompt):
        """プロンプトからLoRA情報を抽出（修正版）"""
        if not prompt:
            return []
        
        try:
            # 修正された正規表現： <lora:name:strength> の形式に対応
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
            
        except Exception as e:
            st.error(f"LoRA抽出エラー: {e}")
            return []

    def display_lora_info(self, sd_params, all_prompts):
        """LoRA情報をテーブル形式で表示（複数プロンプトソース対応）"""
        st.subheader("🔧 使用LoRA詳細")
        
        # 全てのプロンプトソースからLoRAを検索
        all_lora_matches = []
        lora_sources = []
        
        for source_name, prompt in all_prompts.items():
            if prompt:
                lora_matches = self.extract_lora_from_prompt(prompt)
                if lora_matches:
                    all_lora_matches.extend(lora_matches)
                    lora_sources.extend([source_name] * len(lora_matches))
        
        if all_lora_matches:
            # テーブル用データの準備
            table_data = {
                "LoRA名": [name for name, strength in all_lora_matches],
                "強度": [strength for name, strength in all_lora_matches],
                "取得元": lora_sources
            }
            
            # DataFrameを作成
            df = pd.DataFrame(table_data)
            
            # Streamlitのst.dataframeを使用
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            # 詳細情報も表示
            st.write(f"**総LoRA数**: {len(all_lora_matches)}個")
            
        else:
            st.text("LoRA使用なし")
            # デバッグ情報を表示
            if st.checkbox("🔍 LoRA検出デバッグ情報を表示"):
                st.write("**利用可能なプロンプトソース:**")
                for source_name, prompt in all_prompts.items():
                    st.write(f"- {source_name}: {'あり' if prompt else 'なし'} ({len(prompt) if prompt else 0}文字)")
                    if prompt and st.checkbox(f"{source_name}の内容を表示", key=f"debug_show_{source_name}"):
                        st.text_area(f"{source_name} 内容", value=prompt[:500] + "..." if len(prompt) > 500 else prompt, height=100, disabled=True, key=f"debug_content_{source_name}")
                
                st.write("**検索パターン:** `<lora:name:strength>`")
                
                # DynamoDB生データも表示
                if st.checkbox("🔍 DynamoDB生データを表示"):
                    st.json(sd_params)

    def display_enhanced_image_metadata(self, image_data):
        """拡張された画像メタデータの表示（基本パラメータ表示修正版）"""
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
        
        # 画像生成パラメータ（修正版）
        sd_params = image_data.get('sdParams', {})
        if sd_params:
            st.write("**🎯 画像生成パラメータ**")
            
            # 基本パラメータの抽出（DynamoDB AttributeValue対応・修正版）
            try:
                # sdxl_unified構造から基本パラメータを抽出
                sdxl_data = sd_params.get('sdxl_unified', {})
                
                # DynamoDB AttributeValue形式の場合
                if isinstance(sdxl_data, dict) and 'M' in sdxl_data:
                    parsed_sdxl = self.parse_dynamodb_attribute_value(sdxl_data)
                    
                    # 基本パラメータの表示
                    steps = parsed_sdxl.get('steps', 'unknown')
                    cfg_scale = parsed_sdxl.get('cfg_scale', 'unknown') 
                    sampler = parsed_sdxl.get('sampler', 'unknown')
                    width = parsed_sdxl.get('width', 'unknown')
                    height = parsed_sdxl.get('height', 'unknown')
                    
                    st.write(f"ステップ数: {steps}")
                    st.write(f"CFG Scale: {cfg_scale}")
                    st.write(f"Sampler: {sampler}")
                    st.write(f"解像度: {width}x{height}")
                    
                # 通常の辞書形式の場合（フォールバック）
                elif isinstance(sdxl_data, dict):
                    st.write(f"ステップ数: {sdxl_data.get('steps', 'unknown')}")
                    st.write(f"CFG Scale: {sdxl_data.get('cfg_scale', 'unknown')}")
                    st.write(f"Sampler: {sdxl_data.get('sampler', 'unknown')}")
                    st.write(f"解像度: {sdxl_data.get('width', 'unknown')}x{sdxl_data.get('height', 'unknown')}")
                
                # 直接フィールドからの取得（さらなるフォールバック）
                else:
                    st.write(f"ステップ数: {sd_params.get('steps', 'unknown')}")
                    st.write(f"CFG Scale: {sd_params.get('cfg_scale', 'unknown')}")
                    st.write(f"Sampler: {sd_params.get('sampler', 'unknown')}")
                    
            except Exception as e:
                st.warning(f"パラメータ抽出エラー: {e}")
                # エラー時のフォールバック表示
                st.write(f"ステップ数: {sd_params.get('steps', 'unknown')}")
                st.write(f"CFG Scale: {sd_params.get('cfg_scale', 'unknown')}")
                st.write(f"Sampler: {sd_params.get('sampler', 'unknown')}")
                
                # デバッグ情報の表示
                if st.checkbox("🔍 パラメータ解析デバッグ情報を表示"):
                    st.write("**sdParams構造の詳細:**")
                    st.json(sd_params)
        
        # 改良されたプロンプト抽出
        all_prompts = self.extract_prompt_from_nested_structure(sd_params)
        
        # LoRA情報の表示（改良版）
        self.display_lora_info(sd_params, all_prompts)
        
        # プロンプト情報（展開可能・全量表示対応）
        if st.expander("📝 生成プロンプト詳細（全量表示・マルチソース対応）"):
            if all_prompts:
                # 最も長いプロンプトを特定
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
                    
                    # 他のプロンプトソースも表示
                    if len(all_prompts) > 1:
                        st.write("**その他のプロンプトソース:**")
                        for source, content in all_prompts.items():
                            if content and content != main_prompt:
                                st.write(f"- {source}: {len(content)}文字")
                                if st.checkbox(f"{source}を表示", key=f"show_{source}"):
                                    st.text_area(f"{source}", value=content, height=100, disabled=True, key=f"display_{source}")
                else:
                    st.warning("プロンプトが見つかりません")
            else:
                st.warning("プロンプトが見つかりません")
                if st.checkbox("🔍 プロンプト検索デバッグ情報を表示"):
                    st.write("**sdParams構造:**")
                    st.json(sd_params)
            
            # ネガティブプロンプト
            all_negative_prompts = self.extract_negative_prompt_from_nested_structure(sd_params)
            
            if all_negative_prompts:
                # 最も長いネガティブプロンプトを特定
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
        """統合された時間帯別コメント・スロット設定エリア（最新データ自動反映版）"""
        # リセット状態管理用のキー
        if 'reset_trigger' not in st.session_state:
            st.session_state.reset_trigger = 0

        # 全体を1つの折りたたみにする
        with st.expander("🕐 時間帯別コメント・スロット設定", expanded=False):
            time_slots = {
                "early_morning": "早朝 (6:00-8:00)",
                "morning": "朝 (8:00-9:00)", 
                "lunch": "昼 (11:00-13:00)",
                "evening": "夕方 (13:00-21:00)",
                "night": "夜 (21:00-22:30)",  # 修正：00:59 → 22:30
                "mid_night": "深夜 (22:30-00:59)",  # 新規追加
                "general": "一般時間帯"
}

            # 最新データから取得（重要：毎回最新データを使用）
            pre_comments = image_data.get('preGeneratedComments', {})
            suitable_slots = image_data.get('suitableTimeSlots', [])
            recommended_slot = image_data.get('recommendedTimeSlot', 'general')

            # セッション状態の初期化（最新データで上書き）
            current_image_id = image_data.get('imageId', '')
            
            # 画像が切り替わった場合は最新データで初期化
            if ('current_editing_image_id' not in st.session_state or 
                st.session_state.current_editing_image_id != current_image_id):
                
                st.session_state.current_editing_image_id = current_image_id
                st.session_state.updated_comments = pre_comments.copy()
                st.session_state.updated_suitable = suitable_slots.copy()
                st.session_state.updated_recommended = recommended_slot
                
                st.info(f"✨ 画像 {current_image_id} の最新コメント・スロット設定を読み込みました")

            # 時間帯別の設定エリア
            for slot_key, slot_name in time_slots.items():
                st.write(f"### {slot_name}")
                col1, col2, col3 = st.columns([3, 1, 1])

                with col2:
                    # 適合スロット（タグ風UI）
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
                    # 推奨スロット（単一選択）
                    recommended_key = f"recommended_{slot_key}"
                    recommended_selected = st.button(
                        "✓推奨" if slot_key == st.session_state.updated_recommended else "推奨",
                        key=recommended_key,
                        type="primary" if slot_key == st.session_state.updated_recommended else "secondary"
                    )

                    if recommended_selected:
                        st.session_state.updated_recommended = slot_key
                        st.rerun()

                # コメント編集エリア（最新データ反映版）
                current_comment = st.session_state.updated_comments.get(slot_key, "")
                
                # リセット時は空文字を初期値として使用
                initial_value = "" if st.session_state.get('pending_reset', False) else current_comment
                
                updated_comment = st.text_area(
                    f"{slot_name}用コメント",
                    value=initial_value,
                    height=80,
                    key=f"comment_{slot_key}_{current_image_id}_{st.session_state.reset_trigger}",  # 画像IDを含める
                    label_visibility="collapsed"
                )

                # セッション状態の更新
                st.session_state.updated_comments[slot_key] = updated_comment

                st.divider()

            # リセット処理後のフラグクリア
            if st.session_state.get('pending_reset', False):
                st.session_state.pending_reset = False

            # リセットボタン
            if st.button("🔄 設定をリセット", use_container_width=True):
                # セッション状態のリセット
                st.session_state.updated_comments = {}
                st.session_state.updated_suitable = []
                st.session_state.updated_recommended = 'general'
                
                # 画像固有の保留データもクリア
                image_id = image_data['imageId']
                if 'pending_updates' in st.session_state:
                    if image_id in st.session_state.pending_updates:
                        del st.session_state.pending_updates[image_id]
                
                # リセットトリガーを更新（新しいウィジェットキーを生成）
                st.session_state.reset_trigger += 1
                st.session_state.pending_reset = True
                
                st.success("✅ すべての設定をリセットしました")
                st.rerun()

            # 自動保存についての説明
            st.success("✨ 設定は承認・却下ボタン押下時に自動保存されます")

            # 現在の設定状況を表示
            if (st.session_state.updated_comments or 
                st.session_state.updated_suitable or 
                st.session_state.updated_recommended != 'general'):
                
                st.write("**📝 現在の設定:**")
                if st.session_state.updated_comments:
                    comment_count = sum(1 for v in st.session_state.updated_comments.values() if v.strip())
                    if comment_count > 0:
                        st.write(f"- コメント: {comment_count}個の時間帯で入力済み")
                
                if st.session_state.updated_suitable:
                    st.write(f"- 適合スロット: {', '.join(st.session_state.updated_suitable)}")
                
                if st.session_state.updated_recommended != 'general':
                    slot_names = {
                        "early_morning": "早朝",
                        "morning": "朝", 
                        "lunch": "昼",
                        "evening": "夕方",
                        "night": "夜",
                        "general": "一般"
                    }
                    recommended_name = slot_names.get(st.session_state.updated_recommended, st.session_state.updated_recommended)
                    st.write(f"- 推奨スロット: {recommended_name}")

        return st.session_state.updated_comments, st.session_state.updated_suitable, st.session_state.updated_recommended

    def clear_comment_settings_on_image_change(self):
        """画像切り替え時のコメント設定クリア（改良版）"""
        # 編集中画像IDもクリア
        if 'current_editing_image_id' in st.session_state:
            del st.session_state.current_editing_image_id

        # コメント関連のセッション状態をクリア
        if 'updated_comments' in st.session_state:
            st.session_state.updated_comments = {}

        # コメント入力フィールドのセッション状態をクリア
        keys_to_clear = []
        for key in list(st.session_state.keys()):
            if key.startswith('comment_'):
                keys_to_clear.append(key)
        
        for key in keys_to_clear:
            del st.session_state[key]

        # 保留中のコメントデータもクリア
        if 'pending_updates' in st.session_state:
            for image_id in list(st.session_state.pending_updates.keys()):
                pending_data = st.session_state.pending_updates[image_id]
                if 'preGeneratedComments' in pending_data:
                    del pending_data['preGeneratedComments']
                if 'commentGeneratedAt' in pending_data:
                    del pending_data['commentGeneratedAt']
                
                # 空になった保留データを削除
                if not pending_data:
                    del st.session_state.pending_updates[image_id]

        # リセットトリガーを更新（ウィジェット更新用）
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

        # セッション状態の初期化
        if 'selected_reasons' not in st.session_state:
            st.session_state.selected_reasons = []

        # タグ選択UI（2行5列）
        cols = st.columns(5)
        for i, reason in enumerate(REJECTION_REASONS):
            col = cols[i % 5]
            with col:
                # タグ風ボタン
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

        # 自由入力エリア
        st.write("**その他理由：**")
        other_reason = st.text_input(
            "その他の却下理由",
            key="other_reason",
            label_visibility="collapsed",
            placeholder="選択肢にない場合は自由入力してください"
        )

        # 選択状態の表示
        if st.session_state.selected_reasons or other_reason:
            st.write("**選択された却下理由：**")
            all_reasons = st.session_state.selected_reasons.copy()
            if other_reason:
                all_reasons.append(other_reason)
            for reason in all_reasons:
                st.markdown(f"- {reason}")

        return st.session_state.selected_reasons, other_reason

    def update_image_status(self, image_id, status, rejection_reasons=None, other_reason=None, reviewer=None):
        """画像ステータス更新（コメント設定自動保存対応版）"""
        try:
            # デバッグ情報の表示
            st.write("🔍 **却下理由デバッグ情報**")
            st.write(f"- rejection_reasons: {rejection_reasons}")
            st.write(f"- other_reason: {other_reason}")
            st.write(f"- status: {status}")

            res = self.table.get_item(Key={'imageId': image_id})
            if 'Item' not in res:
                st.error('画像データが見つかりません')
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

            # 却下理由の処理（改善版）
            if status == "rejected":
                reasons = []
                if rejection_reasons and len(rejection_reasons) > 0:
                    reasons.extend(rejection_reasons)
                    st.write(f"✅ 選択された却下理由: {rejection_reasons}")
                
                if other_reason and other_reason.strip():
                    reasons.append(other_reason.strip())
                    st.write(f"✅ その他の却下理由: {other_reason}")

                # 却下理由が1つでもある場合のみ保存
                if reasons:
                    update_expr += ", rejectionReasons = :reasons"
                    expr_vals[':reasons'] = reasons
                    st.success(f"✅ 却下理由を保存します: {reasons}")
                else:
                    # 却下理由が空の場合は警告
                    st.warning("⚠️ 却下理由が選択されていませんが、処理を続行します")

            # TTL設定
            ttl_ts = int(datetime.now().timestamp()) + 30 * 24 * 60 * 60
            update_expr += ", #ttl = :ttl"
            expr_vals[':ttl'] = ttl_ts
            expr_names['#ttl'] = 'TTL'

            # レビュー者
            if reviewer:
                update_expr += ", reviewer = :rv"
                expr_vals[':rv'] = reviewer

            # デバッグ：最終的なUpdateExpressionを表示
            st.write("📝 **DynamoDB更新情報**")
            st.write(f"UpdateExpression: {update_expr}")
            st.write(f"AttributeValues: {expr_vals}")

            params = {'Key': {'imageId': image_id},
                     'UpdateExpression': update_expr,
                     'ExpressionAttributeValues': expr_vals}
            
            if expr_names:
                params['ExpressionAttributeNames'] = expr_names

            self.table.update_item(**params)

            # 承認・却下後のコメント設定クリア
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
        """統計情報取得（拡張版）"""
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

        except Exception as e:
            st.error(f"❌ 統計取得エラー: {e}")
            return None

def create_safe_dataframe(data_dict, key_column, value_column):
    """安全なDataFrame作成"""
    if not data_dict:
        return pd.DataFrame({key_column: ["データなし"], value_column: [0]})
    
    return pd.DataFrame([
        {key_column: k, value_column: v} 
        for k, v in data_dict.items()
    ])

def main():
    """メイン画面（画像切り替え時自動データ更新対応版）"""
    st.set_page_config(
        page_title="美少女画像検品システム Ver7.0 - 自動データ更新対応版",
        page_icon="🖼️",
        layout="wide"
    )

    st.title("🖼️ 美少女画像検品システム Ver7.2")
    st.caption("自動データ更新対応版 - 画像切り替え時にコメント・スロット設定も自動更新")

    # システム初期化
    review_system = ImageReviewSystem()
    st.sidebar.write(review_system.connection_status)

    # サイドバー：フィルタ設定
    st.sidebar.header("🔍 検索期間変更")

    # ステータスフィルタ
    status_options = ["全て", "unprocessed", "pending", "reviewed_approved", "rejected"]
    status_filter = st.sidebar.selectbox("ステータス", status_options, index=1)

    # ジャンルフィルタ
    genre_options = ["全て", "normal", "gyal_black", "gyal_natural", "seiso", "teen"]
    genre_filter = st.sidebar.selectbox("ジャンル", genre_options)

    # 高画質化モードフィルタ
    highres_mode_options = ["全て", "SDXL", "SD15"]
    highres_mode_filter = st.sidebar.selectbox("高画質化モード", highres_mode_options)

    # 期間フィルタ（検索期間変更専用）
    days_back = st.sidebar.slider("検索期間（日）", 0, 30, 0)
    if days_back == 0:
        st.sidebar.info("📅 今日のみを対象とします")
    else:
        st.sidebar.info(f"📅 過去{days_back}日間（今日を含む）を対象とします")

    # データ更新ボタン（検索期間変更専用）
    if st.sidebar.button("🔍 検索期間でデータ更新", type="primary"):
        # 検索期間変更時のみセッション状態をクリア
        if 'updated_comments' in st.session_state:
            del st.session_state.updated_comments
        if 'updated_suitable' in st.session_state:
            del st.session_state.updated_suitable
        if 'updated_recommended' in st.session_state:
            del st.session_state.updated_recommended
        if 'selected_reasons' in st.session_state:
            del st.session_state.selected_reasons
        if 'current_editing_image_id' in st.session_state:
            del st.session_state.current_editing_image_id
        st.rerun()

    # メインコンテンツ
    tab1, tab2, tab3 = st.tabs(["📝 画像検品", "📊 統計情報", "ℹ️ システム情報"])

    with tab1:
        st.header("画像検品作業（自動データ更新対応）")

        # データ読み込み（検索期間変更時のみ）
        with st.spinner("データ読み込み中..."):
            images_data = review_system.load_images_efficiently(
                status_filter=status_filter if status_filter != "全て" else None,
                genre_filter=genre_filter if genre_filter != "全て" else None,
                highres_mode_filter=highres_mode_filter if highres_mode_filter != "全て" else None,
                days_back=days_back
            )

        if images_data:
            st.success(f"✅ {len(images_data)}件の画像データを読み込みました")

            # データフレーム表示
            df = pd.DataFrame(images_data)
            
            # 表示用データの整形
            display_columns = ['imageId', 'genre', 'status', 'highres_mode', 'created_at', 'postingStage']
            if 'file_size' in df.columns:
                display_columns.append('file_size')
            
            display_df = df[display_columns].copy()
            if 'file_size' in display_df.columns:
                display_df['file_size_mb'] = (display_df['file_size'] / 1024 / 1024).round(2)
                display_df = display_df.drop('file_size', axis=1)

            st.dataframe(display_df, use_container_width=True)

            # 個別画像検品
            st.subheader("個別画像検品")

            if len(images_data) > 0:
                # 画像選択
                selected_idx = st.selectbox(
                    "検品する画像を選択",
                    range(len(images_data)),
                    format_func=lambda x: f"{images_data[x]['imageId']} ({images_data[x]['highres_mode']}モード)"
                )

                base_selected_image = images_data[selected_idx]
                current_image_id = base_selected_image['imageId']

                # 画像切り替え検知と最新データ自動取得（重要な改善点）
                if 'previous_image_id' not in st.session_state:
                    st.session_state.previous_image_id = current_image_id
                elif st.session_state.previous_image_id != current_image_id:
                    # 画像が変更された場合は最新データを自動取得
                    st.info(f"🔄 画像が切り替わりました: {current_image_id}")
                    st.info("📡 最新のコメント・スロット設定を自動取得中...")
                    
                    # 前の画像の設定をクリア
                    review_system.clear_comment_settings_on_image_change()
                    st.session_state.previous_image_id = current_image_id

                # 選択された画像の最新データを取得
                selected_image = review_system.get_single_image_latest_data(current_image_id)
                
                # 最新データ取得に失敗した場合は基本データを使用
                if selected_image is None:
                    st.warning("⚠️ 最新データ取得に失敗しました。基本データを使用します。")
                    selected_image = base_selected_image

                # 画像表示エリア
                col1, col2 = st.columns([1, 1])

                with col1:
                    st.subheader("画像プレビュー")
                    if selected_image['s3_key']:
                        image = review_system.get_image_from_s3(selected_image['s3_key'])
                        if image:
                            st.image(image, use_container_width=True)
                        else:
                            st.error("画像の読み込みに失敗しました")
                    else:
                        st.warning("S3キーが設定されていません")

                with col2:
                    # 拡張された画像メタデータの表示
                    review_system.display_enhanced_image_metadata(selected_image)

                # 統合された時間帯別コメント・スロット設定エリア（自動最新データ反映）
                st.divider()
                comments, suitable_slots, recommended_slot = review_system.render_integrated_comment_timeslot_area(selected_image)

                # 却下理由選択エリア
                st.divider()
                selected_reasons, other_reason = review_system.render_rejection_reason_tags(selected_image)

                # 検品操作ボタン
                st.divider()
                st.subheader("検品操作")

                reviewer_name = st.text_input("検品者名", value="検品者")

                # ステータス更新ボタン
                button_col1, button_col2 = st.columns(2)

                with button_col1:
                    if st.button("✅ 承認", type="primary", use_container_width=True):
                        st.info("🔄 承認処理を開始します...")
                        st.info("📝 設定予定: imageState=reviewed_approved, postingStage=ready_for_posting")
                        if review_system.update_image_status(
                            selected_image['imageId'],
                            "reviewed_approved",
                            reviewer=reviewer_name
                        ):
                            st.balloons()
                            st.success("🎉 承認完了！X投稿システムで自動投稿されます")
                            time.sleep(2)
                            st.rerun()

                with button_col2:
                    if st.button("❌ 却下", type="secondary", use_container_width=True):
                        if not selected_reasons and not other_reason:
                            st.warning("却下理由を選択してください")
                        else:
                            st.info("🔄 却下処理を開始します...")
                            st.info("📝 設定予定: imageState=rejected, postingStage=archived, TTL=30日")
                            if review_system.update_image_status(
                                selected_image['imageId'],
                                "rejected",
                                rejection_reasons=selected_reasons,
                                other_reason=other_reason,
                                reviewer=reviewer_name
                            ):
                                st.success("❌ 却下しました（30日後に自動削除されます）")
                                time.sleep(1)
                                st.rerun()
        else:
            st.warning("⚠️ 条件に合致する画像データが見つかりませんでした")

    with tab2:
        st.header("📊 統計情報")

        # 統計データ取得
        with st.spinner("統計データ取得中..."):
            stats = review_system.get_statistics(days_back)

        if stats:
            # 基本統計
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("総画像数", stats['total_count'])

            with col2:
                approved_count = stats['status_counts'].get('reviewed_approved', 0) + stats['status_counts'].get('approved', 0)
                st.metric("承認済み", approved_count)

            with col3:
                pending_count = stats['status_counts'].get('pending', 0) + stats['status_counts'].get('unprocessed', 0)
                st.metric("検品待ち", pending_count)

            with col4:
                rejected_count = stats['status_counts'].get('rejected', 0)
                st.metric("却下済み", rejected_count)

            # TTL設定済み画像の統計
            if stats['ttl_items_count'] > 0:
                st.info(f"🗑️ TTL設定済み画像: {stats['ttl_items_count']}件（自動削除対象）")

            # ステータス別詳細
            st.subheader("ステータス別内訳")
            try:
                status_df = create_safe_dataframe(stats['status_counts'], "ステータス", "件数")
                if len(status_df) > 0 and "ステータス" in status_df.columns:
                    st.bar_chart(status_df.set_index('ステータス'))
                else:
                    st.info("ステータス別データがありません")
            except Exception as e:
                st.error(f"ステータス別グラフ表示エラー: {e}")
                st.write("データ詳細:")
                st.write(stats['status_counts'])

            # 高画質化モード別統計
            st.subheader("高画質化モード別内訳")
            try:
                highres_df = create_safe_dataframe(stats['highres_mode_counts'], "モード", "件数")
                if len(highres_df) > 0 and "モード" in highres_df.columns:
                    st.bar_chart(highres_df.set_index('モード'))
                else:
                    st.info("高画質化モード別データがありません")
            except Exception as e:
                st.error(f"高画質化モード別グラフ表示エラー: {e}")
                st.write("データ詳細:")
                st.write(stats['highres_mode_counts'])

            # ジャンル別統計
            st.subheader("ジャンル別内訳")
            try:
                genre_df = create_safe_dataframe(stats['genre_counts'], "ジャンル", "件数")
                if len(genre_df) > 0 and "ジャンル" in genre_df.columns:
                    st.bar_chart(genre_df.set_index('ジャンル'))
                else:
                    st.info("ジャンル別データがありません")
            except Exception as e:
                st.error(f"ジャンル別グラフ表示エラー: {e}")
                st.write("データ詳細:")
                st.write(stats['genre_counts'])

        else:
            st.error("❌ 統計データの取得に失敗しました")

    with tab3:
        st.header("ℹ️ システム情報")

        st.subheader("🔧 Ver7.2 自動データ更新対応版の特徴")

        st.write("""
        **🎯 主要な改善点（Ver7.2）**
        - 画像切り替え時の自動最新データ取得
        - コメント・スロット設定の自動更新
        - 検品ワークフローの中断解消
        - データ更新ボタンの機能限定（検索期間変更専用）
        - 完全自動化された検品プロセス

        **🚀 新機能（Ver7.2）**
        - `get_single_image_latest_data()` 関数追加
        - 画像選択時の自動最新データ反映
        - 編集中画像ID管理機能
        - 自動データ更新通知機能
        - 検索期間変更専用データ更新

        **✨ 運用改善（Ver7.2）**
        - 検品→承認/却下→次画像の自動データ更新
        - ワークフロー中断の完全解消
        - データ更新ボタンの用途明確化
        - より直感的な操作性
        - 検品効率の大幅向上

        **🔄 ワークフロー**
        1. 画像を選択 → 自動的に最新コメント・スロット情報を取得
        2. 検品作業 → 最新データで作業可能
        3. 承認/却下 → 次の画像へ移動時に再度自動更新
        4. 検索期間変更時のみ「検索期間でデータ更新」ボタンを使用
        """)

        st.subheader("🗂️ システム設定")
        settings_data = {
            "AWS リージョン": AWS_REGION,
            "S3 バケット": S3_BUCKET,
            "DynamoDB テーブル": DYNAMODB_TABLE,
            "検索期間": f"{days_back}日",
            "対応モード": "SDXL, SD15",
            "バージョン": "7.2",
            "UI設計": "自動データ更新対応",
            "TTL機能": "30日自動削除対応",
            "データ更新": "画像切り替え時自動実行",
            "時間帯管理": "最新データ自動反映",
            "却下理由": "タグ選択方式",
            "ワークフロー": "完全自動化対応"
        }

        for key, value in settings_data.items():
            st.write(f"**{key}**: `{value}`")

        st.subheader("📈 統計情報")
        if stats:
            st.write(f"**データ期間**: {stats['period_days']}日")
            st.write(f"**総画像数**: {stats['total_count']}件")
            st.write(f"**TTL設定済み**: {stats['ttl_items_count']}件")
        else:
            st.write("統計データの取得に失敗しました")

if __name__ == "__main__":
    main()
