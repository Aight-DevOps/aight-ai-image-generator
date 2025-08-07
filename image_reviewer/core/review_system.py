#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ImageReviewSystem - メイン検品システムクラス
- 初期化・AWS接続管理
- 各モジュールの統合制御
"""

import streamlit as st
from common.logger import ColorLogger
from common.aws_client import AWSClientManager
from ..data.loader import DataLoader
from ..data.parser import DataParser
from ..display.image_viewer import ImageViewer
from ..display.ui_components import UIComponents
from ..review.comment_manager import CommentManager
from ..review.status_updater import StatusUpdater
from ..review.rejection_handler import RejectionHandler
from ..stats.analyzer import StatsAnalyzer

# AWS設定
AWS_REGION = 'ap-northeast-1'
S3_BUCKET = 'aight-media-images'
DYNAMODB_TABLE = 'AightMediaImageData'

class ImageReviewSystem:
    """検品システムメインクラス"""
    
    def __init__(self):
        """検品システム初期化"""
        self.logger = ColorLogger()
        
        # AWS接続
        fake_config = {
            'aws': {
                'region': AWS_REGION,
                's3_bucket': S3_BUCKET,
                'dynamodb_table': DYNAMODB_TABLE
            }
        }
        self.aws_manager = AWSClientManager(self.logger, fake_config)
        self.connection_status = self.aws_manager.setup_reviewer_clients(
            AWS_REGION, S3_BUCKET, DYNAMODB_TABLE
        )
        
        # 各モジュール初期化
        self.data_loader = DataLoader(self.aws_manager, self.logger)
        self.data_parser = DataParser(self.logger)
        self.image_viewer = ImageViewer(self.aws_manager.s3_client, S3_BUCKET, self.logger)
        self.ui_components = UIComponents(self.data_parser, self.logger)
        self.comment_manager = CommentManager(self.logger)
        self.status_updater = StatusUpdater(self.aws_manager.dynamodb_table, self.logger)
        self.rejection_handler = RejectionHandler(self.logger)
        self.stats_analyzer = StatsAnalyzer(self.aws_manager.dynamodb_table, self.logger)
    
    def get_single_image_latest_data(self, image_id):
        """個別画像の最新データ取得"""
        return self.data_loader.get_single_image_latest_data(image_id)
    
    def load_images_efficiently(self, status_filter=None, genre_filter=None, 
                               highres_mode_filter=None, days_back=7):
        """効率的画像データ読み込み"""
        return self.data_loader.load_images_efficiently(
            status_filter, genre_filter, highres_mode_filter, days_back
        )
    
    def get_image_from_s3(self, s3_key):
        """S3から画像取得"""
        return self.image_viewer.get_image_from_s3(s3_key)
    
    def display_enhanced_image_metadata(self, image_data):
        """拡張画像メタデータ表示"""
        return self.image_viewer.display_enhanced_image_metadata(image_data)
    
    def render_integrated_comment_timeslot_area(self, image_data):
        """統合コメント・時間帯設定エリア"""
        return self.comment_manager.render_integrated_comment_timeslot_area(image_data)
    
    def render_rejection_reason_tags(self, selected_image):
        """却下理由タグ選択"""
        return self.rejection_handler.render_rejection_reason_tags(selected_image)
    
    def update_image_status(self, image_id, status, rejection_reasons=None, 
                           other_reason=None, reviewer=None):
        """画像ステータス更新"""
        return self.status_updater.update_image_status(
            image_id, status, rejection_reasons, other_reason, reviewer
        )
    
    def get_statistics(self, days_back=7):
        """統計情報取得"""
        return self.stats_analyzer.get_statistics(days_back)
    
    def clear_comment_settings_on_image_change(self):
        """画像切り替え時コメント設定クリア"""
        self.comment_manager.clear_comment_settings_on_image_change()
