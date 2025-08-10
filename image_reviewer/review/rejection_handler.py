#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RejectionHandler - 却下理由タグ選択管理
- render_rejection_reason_tags
"""

import streamlit as st

class RejectionHandler:
    """却下理由管理クラス"""

    REASONS = [
        "四肢欠損", "骨格崩れ", "手指崩れ", "足崩れ",
        "生成失敗", "顔面崩壊", "構図不良", "服装不適切",
        "露出過度", "色彩異常"
    ]

    def __init__(self, logger):
        self.logger = logger

    def render_rejection_reason_tags(self, selected_image):
        """
        却下理由タグ選択UI
        Returns: (selected_reasons, other_reason)
        """
        st.subheader("🏷️ 却下理由選択")
        if 'selected_reasons' not in st.session_state:
            st.session_state['selected_reasons'] = []
        for i, reason in enumerate(self.REASONS):
            selected = reason in st.session_state['selected_reasons']
            if st.button(reason, key=f"reason_{i}", type="primary" if selected else "secondary"):
                if selected:
                    st.session_state['selected_reasons'].remove(reason)
                else:
                    st.session_state['selected_reasons'].append(reason)
                st.experimental_rerun()
        other = st.text_input("その他の却下理由", key="other_reason")
        return st.session_state['selected_reasons'], other
