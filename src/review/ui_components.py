#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UI Components - Streamlit UI部品
"""

import streamlit as st
import pandas as pd
from typing import Dict, List, Tuple, Any
from .review_system import ImageReviewSystem

class UIComponents:
    """Streamlit UI部品クラス"""
    
    def __init__(self, review_system: ImageReviewSystem):
        """UI部品初期化"""
        self.review_system = review_system

    def display_enhanced_image_metadata(self, image_data: Dict[str, Any]):
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

            # 基本パラメータの抽出（DynamoDB AttributeValue対応）
            try:
                # sdxl_unified構造から基本パラメータを抽出
                sdxl_data = sd_params.get('sdxl_unified', {})

                # DynamoDB AttributeValue形式の場合
                if isinstance(sdxl_data, dict) and 'M' in sdxl_data:
                    parsed_sdxl = self.review_system.parse_dynamodb_attribute_value(sdxl_data)
                    
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
        all_prompts = self.review_system.extract_prompt_from_nested_structure(sd_params)

        # LoRA情報の表示
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
        all_negative_prompts = self.review_system.extract_negative_prompt_from_nested_structure(sd_params)
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

    def display_lora_info(self, sd_params: Dict[str, Any], all_prompts: Dict[str, str]):
        """LoRA情報をテーブル形式で表示"""
        st.subheader("🔧 使用LoRA詳細")

        # 全てのプロンプトソースからLoRAを検索
        all_lora_matches = []
        lora_sources = []

        for source_name, prompt in all_prompts.items():
            if prompt:
                lora_matches = self.review_system.extract_lora_from_prompt(prompt)
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

    def render_integrated_comment_timeslot_area(self, image_data: Dict[str, Any]) -> Tuple[Dict[str, str], List[str], str]:
        """統合された時間帯別コメント・スロット設定エリア"""
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
                "night": "夜 (21:00-22:30)",
                "mid_night": "深夜 (22:30-00:59)",
                "general": "一般時間帯"
            }

            # 最新データから取得
            pre_comments = image_data.get('preGeneratedComments', {})
            suitable_slots = image_data.get('suitableTimeSlots', [])
            recommended_slot = image_data.get('recommendedTimeSlot', 'general')

            # セッション状態の初期化
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

                # コメント編集エリア
                current_comment = st.session_state.updated_comments.get(slot_key, "")

                # リセット時は空文字を初期値として使用
                initial_value = "" if st.session_state.get('pending_reset', False) else current_comment

                updated_comment = st.text_area(
                    f"{slot_name}用コメント",
                    value=initial_value,
                    height=80,
                    key=f"comment_{slot_key}_{current_image_id}_{st.session_state.reset_trigger}",
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

                # リセットトリガーを更新
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

    def render_rejection_reason_tags(self) -> Tuple[List[str], str]:
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

    def clear_comment_settings_on_image_change(self):
        """画像切り替え時のコメント設定クリア"""
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

        # リセットトリガーを更新
        if 'reset_trigger' not in st.session_state:
            st.session_state.reset_trigger = 0
        st.session_state.reset_trigger += 1

    @staticmethod
    def create_safe_dataframe(data_dict: Dict[str, Any], key_column: str, value_column: str) -> pd.DataFrame:
        """安全なDataFrame作成"""
        if not data_dict:
            return pd.DataFrame({key_column: ["データなし"], value_column: [0]})
        return pd.DataFrame([
            {key_column: k, value_column: v}
            for k, v in data_dict.items()
        ])
