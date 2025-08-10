#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MetadataManager - DynamoDB�p���^�f�[�^�\�z�@�\
- prepare_metadata_and_dynamodb_item: S3�L�[�EDynamoDB�A�C�e������
"""

import os
import json
from datetime import datetime, timezone, timedelta
from common.logger import ColorLogger

# JST �^�C���]�[��
JST = timezone(timedelta(hours=9))

class MetadataManager:
    """DynamoDB���^�f�[�^�\�z�N���X"""

    def __init__(self, config, default_slots):
        """
        Args:
            config: �ݒ� dict
            default_slots: �K�����ԑуX���b�g�ꗗ
        """
        self.config = config
        self.default_slots = default_slots
        self.logger = ColorLogger()

    def prepare_metadata_and_dynamodb_item(self, final_image_path: str, index: int,
                                           generation_response: dict, gen_type,
                                           original_input_path: str):
        """
        S3�L�[�� DynamoDB �A�C�e��������
        Returns: image_id, dynamodb_item
        """
        # �摜ID����
        now = datetime.now(JST).strftime("%Y%m%d%H%M%S")
        fast_suffix = "_fast" if gen_type.fast_mode else ""
        ultra_suffix = "_ultra_safe"
        bedrock_suffix = "_bedrock" if gen_type.bedrock_enabled else ""
        pose_suffix = f"_{gen_type.pose_mode}" if hasattr(gen_type, 'pose_mode') else ""
        image_id = f"sdxl_{gen_type.name}{fast_suffix}{ultra_suffix}{bedrock_suffix}{pose_suffix}_{now}_{index:03d}"

        # S3�L�[
        s3_key = f"image-pool/{gen_type.name}/{image_id}.png"

        # SD �p�����[�^�擾
        params = generation_response.get('parameters', {})

        # Bedrock �R�����g
        pre_comments = {}
        comment_ts = ""
        if hasattr(gen_type, 'bedrock_comments'):
            pre_comments = gen_type.bedrock_comments
            comment_ts = datetime.now(JST).isoformat()

        # DynamoDB �A�C�e��
        item = {
            "imageId": image_id,
            "s3Bucket": self.config['aws']['s3_bucket'],
            "s3Key": s3_key,
            "genre": gen_type.name,
            "imageState": "unprocessed",
            "postingStage": "notposted",
            "createdAt": now,
            # --- �ǉ�: 11�X���b�g�Ή��t�B�[���h ---
            "suitableTimeSlots": generation_response.get('suitableTimeSlots', self.default_slots),
            "recommendedTimeSlot": generation_response.get('recommendedTimeSlot', 'general'),
            "slotConfigVersion": generation_response.get('slotConfigVersion', ''),
            # --- �����t�B�[���h�i���R�[�h���S�ێ��j ---
            "preGeneratedComments": pre_comments,
            "commentGeneratedAt": comment_ts,
            "sdParams": {
                "prompt": params.get('prompt', ''),
                "negative_prompt": params.get('negative_prompt', ''),
                "steps": params.get('steps', self.config['sdxl_generation']['steps']),
                "cfg_scale": params.get('cfg_scale', self.config['sdxl_generation']['cfg_scale']),
                "sampler": params.get('sampler', self.config['sdxl_generation']['sampler_name']),
                "width": params.get('width', self.config['sdxl_generation']['width']),
                "height": params.get('height', self.config['sdxl_generation']['height']),
                "model": gen_type.model_name
            },
            # X ���e�Ǘ��t�B�[���h
            "scheduledPostTime": "",
            "actualPostTime": now,
            "tweetId": "",
            "postingAttempts": 0,
            "lastErrorMessage": "",
            "movedToArchive": False
        }

        self.logger.print_status(f"?? ���^�f�[�^��������: {image_id}")
        return image_id, item

