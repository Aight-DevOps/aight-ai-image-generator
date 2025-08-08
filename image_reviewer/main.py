#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Streamlit ベース 画像検品システム メインファイル（完全機能版）
"""

import streamlit as st
import pandas as pd
import time
from image_reviewer.core.review_system import ImageReviewSystem

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

                # 画像切り替え検知と最新データ自動取得
                if 'previous_image_id' not in st.session_state:
                    st.session_state.previous_image_id = current_image_id
                elif st.session_state.previous_image_id != current_image_id:
                    st.info(f"🔄 画像が切り替わりました: {current_image_id}")
                    st.info("📡 最新のコメント・スロット設定を自動取得中...")
                    
                    review_system.clear_comment_settings_on_image_change()
                    st.session_state.previous_image_id = current_image_id

                # 選択された画像の最新データを取得
                selected_image = review_system.get_single_image_latest_data(current_image_id)
                
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
                    review_system.display_enhanced_image_metadata(selected_image)

                # 統合された時間帯別コメント・スロット設定エリア
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
            "AWS リージョン": "ap-northeast-1",
            "S3 バケット": "aight-media-images",
            "DynamoDB テーブル": "AightMediaImageData",
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
