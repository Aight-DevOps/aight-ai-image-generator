#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Streamlit ベース 画像検品システム メインファイル
- タブ切り替え: 画像検品, 統計情報, システム情報
"""

import streamlit as st
import time
from image_reviewer.core.review_system import ImageReviewSystem
from image_reviewer.display.ui_components import UIComponents

def main():
    """Streamlit メイン関数"""
    st.set_page_config(page_title="美少女画像検品システム Ver7.2", layout="wide")
    st.title("🖼️ 美少女画像検品システム Ver7.2")
    
    review_system = ImageReviewSystem()
    st.sidebar.write(review_system.connection_status)
    
    # フィルタ
    st.sidebar.header("🔍 検索フィルタ")
    status = st.sidebar.selectbox("ステータス", ["全て", "unprocessed", "pending", "reviewed_approved", "rejected"], index=1)
    genre = st.sidebar.selectbox("ジャンル", ["全て", "normal", "gyal_black", "gyal_natural", "seiso", "teen"])
    mode = st.sidebar.selectbox("高画質モード", ["全て", "SDXL", "SD15"])
    days = st.sidebar.slider("日数", 0, 30, 0)
    if st.sidebar.button("🔄 フィルタ適用"):
        st.experimental_rerun()
    
    # タブ
    tab1, tab2, tab3 = st.tabs(["📝 検品", "📊 統計", "ℹ️ システム情報"])
    ui = UIComponents(None, review_system.logger)
    
    with tab1:
        st.header("画像検品")
        with st.spinner("データ読み込み中..."):
            images = review_system.load_images_efficiently(
                None if status=="全て" else status,
                None if genre=="全て" else genre,
                None if mode=="全て" else mode,
                days
            )
        if not images:
            st.warning("対象データがありません")
            return
        
        df = images  # Streamlit 自動テーブル化
        display_cols = ['imageId', 'genre', 'imageState', 'highres_mode', 'createdAt']
        st.dataframe({k:v for k,v in images[0].items() if k in display_cols})
        
        idx = st.selectbox("画像選択", range(len(images)), format_func=lambda i: images[i]['imageId'])
        selected = images[idx]
        
        # 最新データ取得
        item = review_system.get_single_image_latest_data(selected['imageId']) or selected
        
        col1, col2 = st.columns(2)
        with col1:
            img = review_system.get_image_from_s3(item.get('s3Key',''))
            if img:
                st.image(img, use_column_width=True)
            else:
                st.error("画像取得失敗")
        with col2:
            review_system.display_enhanced_image_metadata(item)
        
        comments, slots, rec = review_system.render_integrated_comment_timeslot_area(item)
        reasons, other = review_system.render_rejection_reason_tags(item)
        
        reviewer = st.text_input("検品者名", value="検品者")
        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            if st.button("✅ 承認"):
                success = review_system.update_image_status(
                    item['imageId'], "reviewed_approved",
                    reviewer=reviewer
                )
                if success:
                    st.success("承認完了")
                    time.sleep(1)
                    st.experimental_rerun()
        with btn_col2:
            if st.button("❌ 却下"):
                if not reasons and not other:
                    st.warning("却下理由を選択してください")
                else:
                    review_system.update_image_status(
                        item['imageId'], "rejected",
                        rejection_reasons=reasons,
                        other_reason=other,
                        reviewer=reviewer
                    )
                    st.success("却下完了")
                    time.sleep(1)
                    st.experimental_rerun()

    with tab2:
        st.header("統計情報")
        stats = review_system.get_statistics(days)
        if stats:
            ui.display_metrics(stats)
            ui.display_bar_chart(stats['status_counts'], "ステータス", "件数")
            ui.display_bar_chart(stats['highres_mode_counts'], "モード", "件数")
            ui.display_bar_chart(stats['genre_counts'], "ジャンル", "件数")
            if stats['ttl_items_count'] > 0:
                st.info(f"TTL設定済み: {stats['ttl_items_count']}件")
        else:
            st.error("統計取得失敗")

    with tab3:
        st.header("システム情報")
        st.write("バージョン: 7.2")
        st.write(f"検索期間: {days}日")
        st.write(f"AWS リージョン: {review_system.aws_manager.config['aws']['region']}")
        st.write(f"S3 バケット: {review_system.aws_manager.config['aws']['s3_bucket']}")
        st.write(f"DynamoDB テーブル: {review_system.aws_manager.config['aws']['dynamodb_table']}")
        st.write("UI: Streamlit")
        st.write("TTL: 30日自動削除設定")

if __name__ == "__main__":
    main()
