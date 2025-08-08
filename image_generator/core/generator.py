#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Hybrid Bijo Image Generator v7.0 - コア画像生成クラス
"""

import os
import time
import base64
import subprocess
import shutil
import requests
import json
import yaml
import torch
import gc
import urllib3
from io import BytesIO
from pathlib import Path
from collections import deque, Counter
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from PIL import Image, ImageFilter, ImageEnhance
from typing import TYPE_CHECKING

from common.logger import ColorLogger
from common.timer import ProcessTimer
from common.types import GenerationType, HybridGenerationError
from common.config_manager import ConfigManager
from common.aws_client import AWSClientManager

# 相対インポートの修正
from ..prompt.builder import PromptBuilder
from ..prompt.lora_manager import LoRAManager
from ..prompt.pose_manager import PoseManager
from ..randomization.secure_random import SecureRandom, EnhancedSecureRandom
from ..randomization.image_pool import InputImagePool
from ..randomization.element_generator import RandomElementGenerator
from ..processing.image_processor import ImageProcessor
from ..processing.generator_engine import GeneratorEngine
from ..processing.saver import ImageSaver
from ..memory.manager import MemoryManager
from ..aws.bedrock import BedrockManager
from ..aws.metadata import MetadataManager

if TYPE_CHECKING:
    from .model_manager import ModelManager

# SSL 警告無視
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# JST タイムゾーン
JST = timezone(timedelta(hours=9))

class HybridBijoImageGeneratorV7:
    """美少女画像SDXL統合生成クラス v7.0"""

    def __init__(self):
        self.logger = ColorLogger()
        self.logger.print_stage("🚀 SDXL統合生成ツール Ver7.0 初期化中...")

        # 設定読み込み
        cfg_mgr = ConfigManager(self.logger)
        self.config = cfg_mgr.load_config(['config/config_v10.yaml'])

        # AWS クライアント初期化
        try:
            self.aws = AWSClientManager(self.logger, self.config)
            self.aws.setup_clients(include_lambda=True)
        except Exception as e:
            self.logger.print_warning(f"⚠️ AWS初期化スキップ: {e}")
            self.aws = None

        # メモリ管理
        self.memory_manager = MemoryManager(self.config)

        # プロンプト関連設定読み込み
        try:
            prompts_data = cfg_mgr.load_yaml(self.config['prompt_files']['prompts'])
            random_data = cfg_mgr.load_yaml(self.config['prompt_files']['random_elements'])
            gen_types_data = cfg_mgr.load_yaml(self.config['prompt_files']['generation_types'])
        except Exception as e:
            self.logger.print_error(f"❌ 設定ファイル読み込みエラー: {e}")
            # デフォルト値で続行
            prompts_data = {}
            random_data = {}
            gen_types_data = {'generation_types': []}

        # 生成タイプ設定
        self.generation_types = []
        for t in gen_types_data.get('generation_types', []):
            # teen/jk の年齢補正
            if t.get('name') in ['teen', 'jk']:
                t['age_range'] = [18, 20]
            gt = GenerationType(
                name=t.get('name', 'default'),
                model_name=t.get('model_name', 'default.safetensors'),
                prompt=t.get('prompt', ''),
                negative_prompt=t.get('negative_prompt', ''),
                random_elements=t.get('random_elements', []),
                age_range=t.get('age_range', [18,24]),
                lora_settings=t.get('lora_settings', [])
            )

            gt.fast_mode = self.config.get('fast_mode', {}).get('enabled', False)
            gt.bedrock_enabled = self.config.get('bedrock_features', {}).get('enabled', False)
            gt.ultra_safe_mode = self.config.get('memory_management', {}).get('enabled', False)
            
            self.generation_types.append(gt)

        if not self.generation_types:
            # デフォルト生成タイプを追加
            default_gt = GenerationType(
                name='default',
                model_name='default.safetensors',
                prompt='beautiful Japanese woman',
                negative_prompt='low quality',
                random_elements=[],
                age_range=[18, 24],
                lora_settings=[]
            )
            self.generation_types.append(default_gt)

        # 各種マネージャ初期化
        self.prompt_builder = PromptBuilder(self.config, prompts_data, gen_types_data)
        self.lora_manager = LoRAManager()
        self.pose_manager = PoseManager(random_data.get('specific_random_elements', {}))
        self.secure_random = SecureRandom()
        self.enhanced_random = EnhancedSecureRandom()

        # 入力プール & 要素
        self.input_pool = None
        self.elem_generator = None

        # 一時ディレクトリ
        self.temp_dir = self.config.get('temp_files', {}).get('directory', '/tmp/sdprocess')
        os.makedirs(self.temp_dir, exist_ok=True)

        self.logger.print_success("✅ 初期化完了")

    def generate_hybrid_image(self, gen_type: GenerationType, count: int=1) -> int:
        """
        複数枚バッチ生成（モデル切り替え含む）
        Returns: 成功数
        """
        overall_timer = ProcessTimer(self.logger)
        overall_timer.start(f"SDXL統合画像生成バッチ（{count}枚）")

        # モデル確保
        try:
            from .model_manager import ModelManager
            ModelManager(self.config).ensure_model_for_generation_type(gen_type)
        except HybridGenerationError as e:
            self.logger.print_error(f"❌ モデル切替失敗: {e}")
            return 0

        success = 0
        for i in range(count):
            img_timer = ProcessTimer(self.logger)
            img_timer.start(f"画像{i+1}/{count}")

            try:
                path, response = self._generate_single(gen_type, i)
                success += 1
                img_timer.end_and_report(1)
            except Exception as e:
                self.logger.print_error(f"❌ 生成エラー: {e}")
                break

        overall_timer.end_and_report(success)
        self.logger.print_stage(f"=== 完了: {success}/{count} 枚 ===")
        return success

    def _generate_single(self, gen_type: GenerationType, index: int):
        """単発生成ワークフロー"""
        # 入力画像選択 & プロンプト構築
        if not self.input_pool:
            cfg = self.config.get('input_images', {})
            source_dir = cfg.get('source_directory', '/tmp/input')
            formats = cfg.get('supported_formats', ['jpg', 'jpeg', 'png'])
            
            # ディレクトリが存在しない場合は作成
            if not os.path.exists(source_dir):
                os.makedirs(source_dir, exist_ok=True)
                self.logger.print_warning(f"⚠️ 入力ディレクトリを作成しました: {source_dir}")
            
            self.input_pool = InputImagePool(
                source_dir, formats,
                history_file=os.path.join(self.temp_dir,'image_history.json')
            )
        
        # ポーズモード表示の改善
        self.logger.print_status(f"🎯 現在のポーズモード: {self.pose_manager.pose_mode}")
        
        try:
            input_path = self.input_pool.get_next_image()
        except FileNotFoundError:
            self.logger.print_warning("⚠️ 入力画像がないため、プロンプトのみで生成します")
            input_path = None

        # ポーズモード別のログ表示
        if self.pose_manager.pose_mode == "detection":
            if input_path:
                self.logger.print_status(f"📸 入力画像（ポーズ検出モード用）: {input_path}")
            else:
                self.logger.print_warning("⚠️ ポーズ検出モード選択中ですが入力画像がありません")
        else:  # specification mode
            self.logger.print_status("🎯 ポーズ指定モード: プロンプトベースで生成")
            if input_path:
                self.logger.print_status("💡 入力画像は存在しますがポーズ指定モードのため使用されません")

        # 前処理
        proc = ImageProcessor(self.config, self.temp_dir, self.pose_manager.pose_mode)
        
        if input_path:
            resized = proc.preprocess_input_image(input_path)
            b64 = proc.encode_image_to_base64(resized)
        else:
            resized = None
            b64 = None

        # プロンプト
        prompt, neg, ad_neg = self.prompt_builder.build_prompts(gen_type, mode="auto")
        prompt += self.lora_manager.generate_lora_prompt(gen_type)
        prompt += self.pose_manager.generate_pose_prompt(gen_type)

        # 生成実行
        engine = GeneratorEngine(self.config, self.pose_manager.pose_mode, self.logger)
        img_path, resp = engine.execute_generation(prompt, neg, ad_neg, input_b64=b64)

        # 仕上げ処理
        if img_path and os.path.exists(img_path):
            proc.apply_final_enhancement(img_path)

        # 保存
        saver = ImageSaver(self.config, self.aws, self.temp_dir,
                          local_mode=self.config.get('local_execution', {}).get('enabled', True))
        
        if self.config.get('local_execution', {}).get('enabled', True):
            saver.save_image_locally(img_path, index, resp, gen_type, input_path, self.pose_manager.pose_mode)
        else:
            saver.save_image_to_s3_and_dynamodb(img_path, index, resp, gen_type, input_path, self.pose_manager.pose_mode)
            
        return img_path, resp
