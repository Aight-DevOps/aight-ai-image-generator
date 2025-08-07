#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
HybridBijoImageGeneratorV7 - メイン画像生成クラス
- 初期化: 設定読み込み、AWS クライアント、プロンプトデータ、ランダム機能、メモリ管理
- generate_hybrid_image: 単発生成
"""

import os
import yaml
from common.logger import ColorLogger
from common.config_manager import ConfigManager
from common.aws_client import AWSClientManager
from common.types import HybridGenerationError
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

class HybridBijoImageGeneratorV7:
    """美少女画像SDXL統合生成クラス v7.0"""

    def __init__(self):
        self.logger = ColorLogger()
        self.logger.print_stage("🚀 SDXL統合生成ツール Ver7.0 初期化中...")

        # 設定読み込み
        cfg_mgr = ConfigManager(self.logger)
        self.config = cfg_mgr.load_config(['config_v10.yaml'])

        # AWS クライアント初期化
        self.aws = AWSClientManager(self.logger, self.config)
        self.aws.setup_clients(include_lambda=True)

        # メモリ管理
        self.memory_manager = MemoryManager(self.config)

        # プロンプトデータ読み込み
        prompts = cfg_mgr.load_yaml(self.config['prompt_files']['prompts'])
        random_elems = cfg_mgr.load_yaml(self.config['prompt_files']['random_elements'])
        gen_types_data = cfg_mgr.load_yaml(self.config['prompt_files']['generation_types'])

        # 生成タイプ設定
        self.generation_types = []
        for t in gen_types_data['generation_types']:
            if t['name'] in ['teen','jk']:
                t['age_range'] = [18,20]
            self.generation_types.append(
                GenerationType(
                    name=t['name'],
                    model_name=t['model_name'],
                    prompt=t['prompt'],
                    negative_prompt=t['negative_prompt'],
                    random_elements=t.get('random_elements',[]),
                    age_range=t.get('age_range',[18,24]),
                    lora_settings=t.get('lora_settings',[])
                )
            )

        # プロンプトビルダー
        self.prompt_builder = PromptBuilder(self.config, prompts, gen_types_data)

        # LoRA, Pose
        self.lora_manager = LoRAManager()
        self.pose_manager = PoseManager(random_elems.get('specific_random_elements', {}))

        # ランダム生成
        self.secure_random = SecureRandom()
        self.enhanced_random = EnhancedSecureRandom()
        self.input_pool = None
        self.elem_generator = None

        # 一時ディレクトリ
        self.temp_dir = self.config['temp_files']['directory']
        os.makedirs(self.temp_dir, exist_ok=True)

        self.logger.print_success("✅ 初期化完了")

    def generate_hybrid_single(self, gen_type):
        """単発画像生成"""
        # モデル切替
        ModelManager(self.config).ensure_model_for_generation_type(gen_type)
        # 入力画像
        if not self.input_pool:
            self.input_pool = InputImagePool(
                self.config['input_images']['source_directory'],
                self.config['input_images']['supported_formats'],
                history_file=os.path.join(self.temp_dir, 'image_history.json')
            )
        input_path = self.input_pool.get_next_image()

        # 前処理・エンコード
        proc = ImageProcessor(self.config, self.temp_dir, self.pose_manager.pose_mode)
        resized = proc.preprocess_input_image(input_path)
        b64 = proc.encode_image_to_base64(resized)

        # プロンプト構築
        prompt, neg, ad_neg = self.prompt_builder.build_prompts(gen_type, mode="auto")
        # LoRA, Pose プロンプト付与
        prompt += self.lora_manager.generate_lora_prompt(gen_type)
        prompt += self.pose_manager.generate_pose_prompt(gen_type)

        # 生成実行
        engine = GeneratorEngine(self.config, self.pose_manager.pose_mode, self.logger)
        path, resp = engine.execute_generation(prompt, neg, ad_neg, input_b64=b64)

        # 仕上げ処理
        proc.apply_final_enhancement(path)

        # 保存
        saver = ImageSaver(self.config, self.aws, self.temp_dir, local_mode=self.config['local_execution']['enabled'])
        if self.config['local_execution']['enabled']:
            saver.save_image_locally(path, 0, resp, gen_type, input_path)
        else:
            saver.save_image_to_s3_and_dynamodb(path, 0, resp, gen_type, input_path)

        return path, resp
