#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ImageViewer - 画像取得・メタデータ表示機能
- get_image_from_s3: S3 から画像取得
- display_enhanced_image_metadata: 拡張メタデータ表示
"""

import io
import base64
from PIL import Image
import streamlit as st
from common.logger import ColorLogger

class ImageViewer:
    """画像取得・メタデータ表示クラス"""

    def __init__(self, s3_client, bucket, logger):
        """
        Args:
            s3_client: boto3 S3 client
            bucket: S3 バケット名
        """
        self.s3 = s3_client
        self.bucket = bucket
        self.logger = logger

    def get_image_from_s3(self, s3_key):
        """S3 から画像を取得"""
        try:
            obj = self.s3.get_object(Bucket=self.bucket, Key=s3_key)
            img_data = obj['Body'].read()
            return Image.open(io.BytesIO(img_data))
        except Exception as e:
            self.logger.print_error(f"S3画像取得エラー: {e}")
            return None

    def display_enhanced_image_metadata(self, image_data):
        """
        拡張メタデータを Streamlit 表示
        """
        st.subheader("📊 画像メタデータ")
        created = image_data.get('createdAt') or image_data.get('created_at','')
        st.write(f"生成日時: {created}")
        st.write(f"ジャンル: {image_data.get('genre','')}")
        st.write("**🎯 生成パラメータ**")
        params = image_data.get('sdParams', {})
        # sdxl_unified優先
        sdxl = params.get('sdxl_unified') or params.get('sdxl')
        if isinstance(sdxl, dict):
            st.write(f"ステップ数: {sdxl.get('steps','')}")
            st.write(f"CFG Scale: {sdxl.get('cfg_scale','')}")
            st.write(f"解像度: {sdxl.get('width','')}x{sdxl.get('height','')}")
        else:
            st.write("パラメータ情報なし")
