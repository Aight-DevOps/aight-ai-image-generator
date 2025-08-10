#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
UIComponents - Streamlit UI コンポーネント
- LoRA 情報表示
- DataFrame 表示補助 etc.
"""

import streamlit as st
import pandas as pd
from common.logger import ColorLogger

class UIComponents:
    """UI コンポーネント統合クラス"""

    def __init__(self, data_parser, logger):
        """
        Args:
            data_parser: DataParser インスタンス
            logger: ColorLogger インスタンス
        """
        self.parser = data_parser
        self.logger = logger

    def display_lora_info(self, sd_params):
        """
        LoRA 使用情報をテーブル表示
        Args:
            sd_params: DynamoDB から取得した sdParams データ
        """
        prompts = self.parser.extract_prompt_from_nested_structure(sd_params)
        all_lora = []
        for source, prompt in prompts.items():
            if prompt:
                matches = self.parser.extract_lora_from_prompt(prompt)
                for name, strength in matches:
                    all_lora.append({
                        'LoRA名': name,
                        '強度': strength,
                        '取得元': source
                    })
        st.subheader("🔧 使用 LoRA 詳細")
        if all_lora:
            df = pd.DataFrame(all_lora)
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.write(f"**総 LoRA 数**: {len(all_lora)} 個")
        else:
            st.write("LoRA 使用なし")

    def display_dataframe(self, data, columns=None):
        """
        DataFrame を Streamlit で表示
        Args:
            data: リスト or dict から変換可能
            columns: 表示カラム指定リスト
        """
        df = pd.DataFrame(data)
        if columns:
            df = df[columns]
        st.dataframe(df, use_container_width=True)

    def display_metrics(self, stats):
        """
        統計情報を Streamlit メトリクス形式で表示
        Args:
            stats: StatsAnalyzer からの統計 dict
        """
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("総画像数", stats.get('total_count', 0))
        with col2:
            approved = stats.get('status_counts', {}).get('reviewed_approved', 0)
            st.metric("承認済み", approved)
        with col3:
            pending = stats.get('status_counts', {}).get('pending', 0) + stats.get('status_counts', {}).get('unprocessed', 0)
            st.metric("検品待ち", pending)
        with col4:
            rejected = stats.get('status_counts', {}).get('rejected', 0)
            st.metric("却下済み", rejected)

    def display_bar_chart(self, data_dict, key_label, value_label):
        """
        dict データをバーグラフで表示
        Args:
            data_dict: {key: count}
            key_label: x軸ラベル
            value_label: y軸ラベル
        """
        if not data_dict:
            st.info(f"{key_label} データがありません")
            return
        df = pd.DataFrame([{key_label: k, value_label: v} for k, v in data_dict.items()])
        st.bar_chart(df.set_index(key_label))
