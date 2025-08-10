#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
StatusUpdater - 画像ステータス更新管理
- update_image_status: DynamoDB 更新
"""

from datetime import datetime
import streamlit as st
from common.logger import ColorLogger
from botocore.exceptions import ClientError

class StatusUpdater:
    """画像ステータス更新クラス"""

    def __init__(self, table, logger):
        """
        Args:
            table: boto3 DynamoDB Table
            logger: ColorLogger
        """
        self.table = table
        self.logger = logger

    def update_image_status(self, image_id, status, rejection_reasons=None, other_reason=None, reviewer=None):
        """
        画像ステータス & コメント/スロット設定を自動保存
        """
        now = datetime.now().strftime("%Y%m%d%H%M%S")
        update_expr = "SET imageState = :st, postingStage = :ps, actualPostTime = :apt, reviewed_at = :rev"
        expr_vals = {
            ':st': "rejected" if status=="rejected" else "reviewed_approved",
            ':ps': "archived" if status=="rejected" else "ready_for_posting",
            ':apt': now,
            ':rev': now
        }
        # コメント/スロット設定
        comments = st.session_state.get('updated_comments', {})
        slots = st.session_state.get('updated_suitable', [])
        rec = st.session_state.get('updated_recommended', 'general')
        if comments or slots or rec!='general':
            update_expr += ", preGeneratedComments = :c, suitableTimeSlots = :s, recommendedTimeSlot = :r"
            expr_vals[':c'] = comments
            expr_vals[':s'] = slots
            expr_vals[':r'] = rec
            expr_vals[':rt'] = now
            update_expr += ", commentGeneratedAt = :rt"

        # 却下理由
        if status=="rejected":
            reasons = []
            if rejection_reasons:
                reasons.extend(rejection_reasons)
            if other_reason:
                reasons.append(other_reason)
            if reasons:
                update_expr += ", rejectionReasons = :rr"
                expr_vals[':rr'] = reasons

        # TTL 30日後自動削除
        ttl = int(datetime.now().timestamp()) + 30*24*3600
        update_expr += ", #ttl = :ttl"
        expr_vals[':ttl'] = ttl
        expr_names = {'#ttl':'TTL'}

        try:
            self.logger.print_status(f"📝 更新: {image_id}")
            params = {
                'Key': {'imageId': image_id},
                'UpdateExpression': update_expr,
                'ExpressionAttributeValues': expr_vals,
                'ExpressionAttributeNames': expr_names
            }
            self.table.update_item(**params)
            self.logger.print_success("✅ 更新完了")
            return True
        except ClientError as e:
            code = e.response.get('Error',{}).get('Code','')
            self.logger.print_error(f"❌ 更新エラー: {code}")
            return False
        except Exception as e:
            self.logger.print_error(f"❌ 更新エラー: {e}")
            return False
