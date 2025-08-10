#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
DataLoader - 画像データ取得・検索機能
- get_single_image_latest_data
- load_images_efficiently (GSI使用・フィルタリング)
"""

from datetime import datetime, timedelta
from boto3.dynamodb.conditions import Key
from common.logger import ColorLogger

class DataLoader:
    """画像データ取得・検索管理クラス"""

    def __init__(self, aws_manager, logger):
        """
        Args:
            aws_manager: AWSClientManager インスタンス
            logger: ColorLogger
        """
        self.logger = logger
        self.table = aws_manager.dynamodb_table

    def get_single_image_latest_data(self, image_id):
        """個別画像の最新データを取得"""
        try:
            self.logger.print_status(f"🔄 画像 {image_id} の最新データ取得中...")
            resp = self.table.get_item(Key={'imageId': image_id})
            if 'Item' not in resp:
                self.logger.print_warning(f"⚠️ {image_id} が見つかりません")
                return None
            item = resp['Item']
            return item
        except Exception as e:
            self.logger.print_error(f"❌ データ取得エラー: {e}")
            return None

    def load_images_efficiently(self, status_filter=None,
                                genre_filter=None, highres_mode_filter=None, days_back=7):
        """
        効率的データ読み込み
        - GSI ImageStateIndex 使用
        - 日付/ジャンル/モードフィルタリング
        """
        self.logger.print_status("🔍 画像データ読み込み...")
        try:
            if status_filter and status_filter != "全て":
                resp = self.table.query(
                    IndexName='ImageStateIndex',
                    KeyConditionExpression=Key('imageState').eq(status_filter)
                )
                items = resp.get('Items', [])
                self.logger.print_success(f"GSI検索: {len(items)}件取得")
            else:
                resp = self.table.scan(Limit=500)
                items = resp.get('Items', [])
                self.logger.print_success(f"全件検索: {len(items)}件取得")

            # フィルタリング
            filtered = []
            for item in items:
                # 日付判定
                if days_back >= 0:
                    dt = None
                    created = item.get('createdAt','')
                    try:
                        dt = datetime.strptime(created, "%Y%m%d%H%M%S")
                    except:
                        pass
                    if dt:
                        if datetime.now() - dt > timedelta(days=days_back):
                            continue
                # ジャンル
                if genre_filter and genre_filter != "全て":
                    if item.get('genre') != genre_filter:
                        continue
                # モード
                if highres_mode_filter and highres_mode_filter != "全て":
                    mode = item.get('highres_mode', item.get('HIGHRES_MODE',''))
                    if mode != highres_mode_filter:
                        continue
                filtered.append(item)

            self.logger.print_success(f"フィルタ後: {len(filtered)}件")
            return filtered

        except Exception as e:
            self.logger.print_error(f"❌ データ読み込みエラー: {e}")
            return []
