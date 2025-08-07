#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CommentManager - 統合コメント・時間帯設定管理
- render_integrated_comment_timeslot_area
- clear_comment_settings_on_image_change
"""

import streamlit as st
from common.logger import ColorLogger

class CommentManager:
    """コメント・時間帯設定管理クラス"""

    TIME_SLOTS = {
        "early_morning": "早朝 (6:00-8:00)",
        "morning": "朝 (8:00-9:00)",
        "lunch": "昼 (11:00-13:00)",
        "evening": "夕方 (13:00-21:00)",
        "night": "夜 (21:00-22:30)",
        "mid_night": "深夜 (22:30-00:59)",
        "general": "一般時間帯"
    }

    def __init__(self, logger):
        self.logger = logger

    def render_integrated_comment_timeslot_area(self, image_data):
        """
        統合コメント・時間帯設定エリアを表示
        Returns:
            (comments, suitable_slots, recommended_slot)
        """
        st.subheader("🕐 時間帯別コメント・スロット設定")
        # 最新データ取得
        comments = image_data.get('preGeneratedComments', {})
        suitable = image_data.get('suitableTimeSlots', [])
        recommended = image_data.get('recommendedTimeSlot', 'general')

        # 初期化
        if 'updated_comments' not in st.session_state or st.session_state.get('current_image_id') != image_data.get('imageId'):
            st.session_state['current_image_id'] = image_data.get('imageId')
            st.session_state['updated_comments'] = comments.copy()
            st.session_state['updated_suitable'] = suitable.copy()
            st.session_state['updated_recommended'] = recommended

        for key, label in self.TIME_SLOTS.items():
            st.markdown(f"### {label}")
            col1, col2, col3 = st.columns([3,1,1])

            # 適合スロット
            with col2:
                selected = key in st.session_state['updated_suitable']
                if st.button("✓適合" if selected else "適合", key=f"suitable_{key}", type="primary" if selected else "secondary"):
                    if selected:
                        st.session_state['updated_suitable'].remove(key)
                    else:
                        st.session_state['updated_suitable'].append(key)
                    st.experimental_rerun()

            # 推奨スロット
            with col3:
                rec = (st.session_state['updated_recommended'] == key)
                if st.button("✓推奨" if rec else "推奨", key=f"recommended_{key}", type="primary" if rec else "secondary"):
                    st.session_state['updated_recommended'] = key
                    st.experimental_rerun()

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
            st.experimental_rerun()

        current = (st.session_state['updated_comments'], st.session_state['updated_suitable'], st.session_state['updated_recommended'])
        return current
