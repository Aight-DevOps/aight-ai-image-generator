#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CommentManager - 統合コメント・時間帯設定管理（11スロット対応版）
- render_integrated_comment_timeslot_area
- clear_comment_settings_on_image_change
"""

import streamlit as st
import boto3
import yaml
from common.logger import ColorLogger

class CommentManager:
    """コメント・時間帯設定管理クラス（11スロット対応版）"""

    def __init__(self, logger):
        self.logger = logger
        self.s3_client = boto3.client('s3', region_name='ap-northeast-1')
        self.s3_bucket = 'aight-media-images'
        
        # ===============================================
        # 11スロット対応：S3から動的にスロット設定を読み込み
        # ===============================================
        self.time_slots = self._load_time_slots_from_s3()

    def _load_time_slots_from_s3(self):
        """
        S3から投稿スケジュール設定を読み込み、11スロット対応の時間帯設定を取得
        
        Returns:
            dict: 時間帯スロット設定
        """
        try:
            self.logger.print_status("🔄 S3から11スロット設定を読み込み中...")
            
            # S3から posting_schedule.yaml を読み込み
            response = self.s3_client.get_object(
                Bucket=self.s3_bucket,
                Key='config/posting_schedule.yaml'
            )
            config_content = response['Body'].read().decode('utf-8')
            schedule_config = yaml.safe_load(config_content)
            
            # スロット情報を抽出してUI表示用に変換
            slots = schedule_config.get('posting_schedule', {}).get('slots', {})
            time_slots_config = {}
            
            for slot_name, slot_data in slots.items():
                if slot_name == 'general':
                    # generalスロットは時間制約なし
                    time_slots_config[slot_name] = "一般時間帯（フォールバック用）"
                else:
                    # 時間帯情報を含む表示名を生成
                    start_time = slot_data.get('start', '00:00')
                    end_time = slot_data.get('end', '23:59')
                    
                    # スロット名の日本語化
                    slot_labels = {
                        'early_morning': '早朝',
                        'morning': '朝',
                        'late_morning': '午前中',
                        'lunch': 'ランチ',
                        'afternoon': '午後',
                        'pre_evening': '夕方前',
                        'evening': '夕方',
                        'night': '夜',
                        'late_night': '深夜',
                        'mid_night': '真夜中'
                    }
                    
                    japanese_name = slot_labels.get(slot_name, slot_name.replace('_', ' ').title())
                    time_slots_config[slot_name] = f"{japanese_name} ({start_time}-{end_time})"
            
            # バージョン情報も取得
            version = schedule_config.get('slot_metadata', {}).get('version', 'unknown')
            total_slots = len(time_slots_config)
            
            self.logger.print_success(f"✅ 11スロット設定読み込み完了 - v{version} ({total_slots}スロット)")
            
            return time_slots_config
            
        except Exception as e:
            self.logger.print_warning(f"⚠️ S3スロット設定読み込み失敗、フォールバック使用: {e}")
            
            # フォールバック：11スロット設定
            return {
                "early_morning": "早朝 (05:00-07:59)",
                "morning": "朝 (08:00-09:59)", 
                "late_morning": "午前中 (10:00-11:59)",
                "lunch": "ランチ (12:00-13:59)",
                "afternoon": "午後 (14:00-15:59)",
                "pre_evening": "夕方前 (16:00-17:59)",
                "evening": "夕方 (18:00-19:59)",
                "night": "夜 (20:00-21:59)",
                "late_night": "深夜 (22:00-23:59)",
                "mid_night": "真夜中 (00:00-04:59)",
                "general": "一般時間帯（フォールバック用）"
            }

    def render_integrated_comment_timeslot_area(self, image_data):
        """
        統合コメント・時間帯設定エリアを表示（11スロット対応版）
        
        Args:
            image_data: 画像データ辞書
            
        Returns:
            tuple: (comments, suitable_slots, recommended_slot)
        """
        st.subheader("🕐 時間帯別コメント・スロット設定（11スロット対応）")
        
        # S3読み込み状況を表示
        total_slots = len(self.time_slots)
        st.info(f"📋 現在の設定: {total_slots}スロット（S3動的読み込み）")

        # 最新データ取得
        comments = image_data.get('preGeneratedComments', {})
        suitable = image_data.get('suitableTimeSlots', [])
        recommended = image_data.get('recommendedTimeSlot', 'general')

        # 初期化
        current_image_id = image_data.get('imageId', '')
        if ('updated_comments' not in st.session_state or 
            st.session_state.get('current_image_id') != current_image_id):
            
            st.session_state['current_image_id'] = current_image_id
            st.session_state['updated_comments'] = comments.copy()
            st.session_state['updated_suitable'] = suitable.copy()
            st.session_state['updated_recommended'] = recommended
            
            st.info(f"✨ 画像 {current_image_id} の最新コメント・スロット設定を読み込みました")

        # 各スロットのUI表示
        for key, label in self.time_slots.items():
            st.markdown(f"### {label}")
            col1, col2, col3 = st.columns([3, 1, 1])

            # 適合スロット
            with col2:
                selected = key in st.session_state['updated_suitable']
                if st.button("✓適合" if selected else "適合", key=f"suitable_{key}", 
                           type="primary" if selected else "secondary"):
                    if selected:
                        st.session_state['updated_suitable'].remove(key)
                    else:
                        st.session_state['updated_suitable'].append(key)
                    st.rerun()

            # 推奨スロット
            with col3:
                rec = (st.session_state['updated_recommended'] == key)
                if st.button("✓推奨" if rec else "推奨", key=f"recommended_{key}",
                           type="primary" if rec else "secondary"):
                    st.session_state['updated_recommended'] = key
                    st.rerun()

            # コメント入力
            comment = st.session_state['updated_comments'].get(key, "")
            updated = st.text_area(f"{label}用コメント", value=comment, height=80, key=f"comment_{key}")
            st.session_state['updated_comments'][key] = updated
            
            st.divider()

        # リセットボタン
        if st.button("🔄 設定をリセット"):
            st.session_state['updated_comments'] = {}
            st.session_state['updated_suitable'] = []
            st.session_state['updated_recommended'] = 'general'
            st.success("✅ すべての設定をリセットしました")
            st.rerun()

        st.success("✨ 設定は承認・却下ボタン押下時に自動保存されます")

        current = (st.session_state['updated_comments'], 
                  st.session_state['updated_suitable'], 
                  st.session_state['updated_recommended'])
        
        return current

    def clear_comment_settings_on_image_change(self):
        """画像切り替え時のコメント設定クリア"""
        if 'current_image_id' in st.session_state:
            del st.session_state['current_image_id']
        if 'updated_comments' in st.session_state:
            del st.session_state['updated_comments']
        if 'updated_suitable' in st.session_state:
            del st.session_state['updated_suitable']
        if 'updated_recommended' in st.session_state:
            del st.session_state['updated_recommended']

        # コメント関連のキーをすべてクリア
        keys_to_clear = []
        for key in list(st.session_state.keys()):
            if key.startswith('comment_') or key.startswith('suitable_') or key.startswith('recommended_'):
                keys_to_clear.append(key)

        for key in keys_to_clear:
            del st.session_state[key]
