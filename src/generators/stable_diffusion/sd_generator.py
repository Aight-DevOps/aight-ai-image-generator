#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stable Diffusion Image Generator - SD専用メイン生成器クラス（完全版・DynamoDBフラット構造対応）
"""

import requests
import time
import os
import base64
import subprocess
import shutil
from io import BytesIO
from PIL import Image, PngImagePlugin, ImageEnhance, ImageFilter
import json
import torch
import gc
import urllib3
from datetime import datetime, timezone, timedelta
from typing import Tuple, Dict, Any, Optional
import secrets
from pathlib import Path
from decimal import Decimal

from ...core.base_generator import BaseImageGenerator, GenerationType
from ...core.config_manager import ConfigManager
from ...core.exceptions import HybridGenerationError, ModelSwitchError, ImageProcessingError
from ...utils.logger import ColorLogger
from ...utils.timer import ProcessTimer
from ...utils.memory_manager import MemoryManager
from .sd_prompt_builder import SDPromptBuilder
from .sd_image_processor import SDImageProcessor
from .sd_random_generator import RandomElementGenerator, InputImagePool

# SSL警告を無効化
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# JST タイムゾーン
JST = timezone(timedelta(hours=9))

class StableDiffusionGenerator(BaseImageGenerator):
    """Stable Diffusion専用画像生成器クラス（完全版）"""

    def __init__(self, config_manager: ConfigManager):
        """SD生成器初期化"""
        super().__init__(config_manager)
        
        # SD専用設定
        self.logger = ColorLogger()
        self.logger.print_stage("🚀 Stable Diffusion生成器 v7.0 初期化中...")
        
        # 設定読み込み
        self.sd_api_config = config_manager.get_stable_diffusion_config()
        self.sdxl_config = config_manager.get_sdxl_generation_config()
        self.controlnet_config = config_manager.get_controlnet_config()
        self.input_images_config = config_manager.get_input_images_config()
        self.temp_files_config = config_manager.get_temp_files_config()
        
        # 専用コンポーネント初期化
        self.prompt_builder = SDPromptBuilder(config_manager)
        self.image_processor = SDImageProcessor(config_manager)
        self.memory_manager = MemoryManager(config_manager)
        
        # ポーズモード
        self.pose_mode = None  # "detection" または "specification"
        
        # 一時ディレクトリ設定
        self.temp_dir = self.temp_files_config.get('directory', '/tmp/sd_process')
        os.makedirs(self.temp_dir, exist_ok=True)
        
        # 拡張ランダム機能初期化
        self.setup_enhanced_randomness()
        
        # 現在のモデル状態
        self.current_model = None
        
        # デフォルト適合時間帯
        self.default_suitable_slots = ["early_morning", "morning", "lunch", "evening", "night", "mid_night", "general"]
        
        self.logger.print_success("✅ SD生成器初期化完了")

    def setup_enhanced_randomness(self):
        """拡張ランダム機能の初期化"""
        try:
            # InputImagePool初期化
            self.input_image_pool = InputImagePool(
                self.input_images_config['source_directory'],
                self.input_images_config['supported_formats'],
                history_file=os.path.join(self.temp_dir, 'image_history.json')
            )
            
            # プロンプトデータから要素を取得
            random_elements_data = self.config_manager.load_config('random_elements')
            specific_elements = random_elements_data.get('specific_random_elements', {})
            general_elements = random_elements_data.get('general_random_elements', {})
            
            # RandomElementGenerator初期化
            self.random_element_generator = RandomElementGenerator(
                specific_elements,
                general_elements,
                history_file=os.path.join(self.temp_dir, 'element_history.json')
            )
            
            # プロンプトビルダーに設定
            self.prompt_builder.set_random_element_generator(self.random_element_generator)
            
            self.logger.print_success("✅ 拡張ランダム機能初期化完了")
            
        except Exception as e:
            raise HybridGenerationError(f"拡張ランダム機能初期化エラー: {e}")

    def set_pose_mode(self, pose_mode: str):
        """ポーズモードを外部から設定"""
        self.pose_mode = pose_mode
        self.prompt_builder.set_pose_mode(self.pose_mode)
        self.logger.print_status(f"🎯 ポーズモード設定: {pose_mode}")

    def select_pose_mode(self):
        """ポーズモード選択"""
        while True:
            print("\n" + "="*50)
            print("🎯 ポーズモード選択")
            print("="*50)
            print("1. ポーズ検出モード（入力画像ベース）")
            print("2. ポーズ指定モード（プロンプトベース）")
            print("="*50)
            
            try:
                choice = input("選択 (1-2): ").strip()
                if choice == '1':
                    self.pose_mode = "detection"
                    self.logger.print_success("✅ ポーズ検出モード（入力画像ベース）を選択しました")
                    self.logger.print_status("🎯 ポーズモード設定: detection")
                    break
                elif choice == '2':
                    self.pose_mode = "specification"
                    self.logger.print_success("✅ ポーズ指定モード（プロンプトベース）を選択しました")
                    self.logger.print_status("🎯 ポーズモード設定: specification")
                    break
                else:
                    print("❌ 無効な選択です")
            except KeyboardInterrupt:
                print("\n🛑 ポーズモード選択が中断されました")
                raise
        
        # プロンプトビルダーにポーズモードを設定
        self.prompt_builder.set_pose_mode(self.pose_mode)

    def get_current_model(self):
        """現在のモデル名を取得"""
        try:
            response = requests.get(
                f"{self.sd_api_config['api_url']}/sdapi/v1/options",
                timeout=30,
                verify=self.sd_api_config.get('verify_ssl', False)
            )
            response.raise_for_status()
            result = response.json()
            current_model = result.get('sd_model_checkpoint', 'Unknown')
            return current_model
        except Exception as e:
            self.logger.print_warning(f"⚠️ 現在のモデル取得エラー: {e}")
            return None

    def switch_model_via_api(self, model_name: str) -> bool:
        """API経由でモデル切り替え"""
        try:
            api_url = self.sd_api_config.get('api_url', 'http://localhost:7860')
            switch_url = f"{api_url}/sdapi/v1/options"
            
            self.logger.print_status(f"🔄 モデル切り替えAPI呼び出し: {switch_url}")
            self.logger.print_status(f"📝 対象モデル: {model_name}")
            
            payload = {
                "sd_model_checkpoint": model_name
            }
            
            model_config = self.config_manager.get_main_config().get('model_switching', {})
            timeout = model_config.get('switch_timeout', 180)
            self.logger.print_status(f"⏰ タイムアウト設定: {timeout}秒")
            
            response = requests.post(
                switch_url,
                json=payload,
                timeout=timeout,
                verify=self.sd_api_config.get('verify_ssl', False)
            )
            
            self.logger.print_status(f"📡 API応答ステータス: {response.status_code}")
            if response.status_code == 200:
                self.logger.print_success("✅ モデル切り替えAPI成功")
                return True
            else:
                self.logger.print_error(f"❌ モデル切り替えAPI失敗: {response.status_code}")
                self.logger.print_error(f"❌ エラー詳細: {response.text}")
                return False
                
        except Exception as e:
            self.logger.print_error(f"❌ モデル切り替えAPI呼び出しエラー: {e}")
            return False

    def verify_model_switch(self, target_model: str) -> bool:
        """モデル切り替え確認"""
        verification_retries = 3
        for attempt in range(verification_retries):
            current_model = self.get_current_model()
            if current_model == target_model:
                self.logger.print_success(f"✅ モデル切り替え確認完了: {target_model}")
                return True
            else:
                self.logger.print_warning(f"⚠️ モデル切り替え確認失敗 (試行{attempt + 1}/{verification_retries}): 期待={target_model}, 実際={current_model}")
                if attempt < verification_retries - 1:
                    time.sleep(5)
        return False

    def ensure_model_for_generation_type(self, gen_type: GenerationType):
        """生成タイプに必要なモデルが設定されていることを確認し、必要に応じて切り替え"""
        if not hasattr(gen_type, 'model_name') or not gen_type.model_name:
            raise HybridGenerationError(f"生成タイプ '{gen_type.name}' のmodel_nameが未定義です")
        
        target_model = gen_type.model_name
        current_model = self.get_current_model()
        
        if current_model == target_model:
            self.logger.print_status(f"🎯 モデル切り替え不要: 既に {target_model} が使用中")
            return True
        
        self.logger.print_status(f"🔄 モデル切り替え中: {current_model} → {target_model}")
        
        # モデル切り替え実行
        if not self.switch_model_via_api(target_model):
            raise HybridGenerationError(f"モデル切り替えAPI呼び出し失敗: {target_model}")
        
        # 切り替え後待機
        wait_time = self.config_manager.get_main_config().get('model_switching', {}).get('wait_after_switch', 10)
        self.logger.print_status(f"⏳ モデル安定化待機: {wait_time}秒")
        time.sleep(wait_time)
        
        # 切り替え確認
        if not self.verify_model_switch(target_model):
            raise HybridGenerationError(f"モデル切り替え確認失敗: {target_model}")
        
        self.current_model = target_model
        self.logger.print_success(f"✅ モデル切り替え完了: {target_model}")
        return True

    def generate_image(self, gen_type: GenerationType, **kwargs) -> Tuple[str, Dict[str, Any]]:
        """
        単一画像生成
        
        Args:
            gen_type: 生成タイプ
            **kwargs: その他のオプション
            
        Returns:
            Tuple[str, Dict[str, Any]]: (画像パス, メタデータ)
        """
        try:
            # メモリ準備
            self.memory_manager.prepare_for_generation()
            
            # モデル切り替え
            self.ensure_model_for_generation_type(gen_type)
            
            # 入力画像選択と前処理
            input_image_path = self.select_random_input_image()
            
            if self.pose_mode == "specification":
                self.logger.print_status("🎯 ポーズ指定モード: 入力画像前処理をスキップします")
                resized_image_path = None
                input_b64 = None
            else:
                resized_image_path = self.image_processor.preprocess_input_image(input_image_path)
                input_b64 = self.image_processor.encode_image_to_base64(resized_image_path)
            
            # プロンプト構築
            prompt, negative_prompt, adetailer_negative = self.prompt_builder.build_prompts(gen_type, mode="auto")
            
            # SDXL統合生成実行
            generation_path, generation_response = self.execute_generation(
                gen_type, input_b64, prompt, negative_prompt, adetailer_negative
            )
            
            # 最終仕上げ処理
            self.image_processor.apply_final_enhancement(generation_path)
            
            # メタデータ作成
            metadata = self.prepare_metadata(gen_type, generation_response, input_image_path)
            
            # 生成後メモリクリーンアップ
            self.memory_manager.cleanup_after_generation()
            
            self.logger.print_success(f"✅ 画像生成完了: {generation_path}")
            return generation_path, metadata
            
        except Exception as e:
            self.logger.print_error(f"❌ 画像生成エラー: {e}")
            raise HybridGenerationError(f"画像生成失敗: {e}")

    def build_prompts(self, gen_type: GenerationType, mode: str = "auto") -> Tuple[str, str]:
        """プロンプト構築（互換性メソッド）"""
        prompt, negative_prompt, adetailer_negative = self.prompt_builder.build_prompts(gen_type, mode)
        return prompt, negative_prompt

    def select_random_input_image(self):
        """ランダム入力画像選択"""
        try:
            selected_image = self.input_image_pool.get_next_image()
            self.logger.print_status(f"🎲 選択された入力画像: {os.path.basename(selected_image)}")
            return selected_image
        except Exception as e:
            raise HybridGenerationError(f"入力画像選択エラー: {e}")

    def execute_generation(self, gen_type: GenerationType, input_b64: str,
                          prompt: str, negative_prompt: str, adetailer_negative: str) -> Tuple[str, Dict[str, Any]]:
        """SDXL統合生成実行"""
        try:
            # API URL構築
            api_url = self.sd_api_config.get('api_url', 'http://localhost:7860')
            generation_url = f"{api_url}/sdapi/v1/txt2img"
            
            # 現在の解像度設定を取得（メモリ調整対応）
            current_resolution = self.memory_manager.get_current_resolution_config()
            
            # 生成パラメータ構築
            payload = self.build_generation_payload(
                gen_type, input_b64, prompt, negative_prompt, adetailer_negative, current_resolution
            )
            
            mode_text = "ポーズ指定モード" if self.pose_mode == "specification" else "ポーズ検出モード"
            self.logger.print_status(f"🎨 SDXL統合生成実行中（{mode_text}）...")
            
            # API呼び出し
            timeout = self.sd_api_config.get('timeout', 3600)
            response = requests.post(
                generation_url,
                json=payload,
                timeout=timeout,
                verify=self.sd_api_config.get('verify_ssl', False)
            )
            
            if response.status_code != 200:
                raise HybridGenerationError(f"API呼び出し失敗: {response.status_code} - {response.text}")
            
            result = response.json()
            if not result.get('images'):
                raise HybridGenerationError("生成結果に画像データが含まれていません")
            
            # 画像保存
            image_data = result['images'][0]
            image_path = self.save_generated_image(image_data, gen_type)
            
            return image_path, result
            
        except Exception as e:
            raise HybridGenerationError(f"SDXL統合生成実行エラー: {e}")

    def build_generation_payload(self, gen_type: GenerationType, input_b64: str,
                               prompt: str, negative_prompt: str, adetailer_negative: str,
                               resolution_config: Dict[str, int]) -> Dict[str, Any]:
        """生成パラメータ構築"""
        # 基本パラメータ
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "steps": self.sdxl_config.get('steps', 30),
            "cfg_scale": self.sdxl_config.get('cfg_scale', 7.0),
            "width": resolution_config.get('width', 896),
            "height": resolution_config.get('height', 1152),
            "sampler_name": self.sdxl_config.get('sampler_name', 'DPM++ 2M Karras'),
            "scheduler": self.sdxl_config.get('scheduler', 'karras'),
            "denoising_strength": self.sdxl_config.get('denoising_strength', 0.0),
            "enable_hr": self.sdxl_config.get('enable_hr', False),
            "hr_scale": self.sdxl_config.get('hr_scale', 1.0),
            "hr_upscaler": self.sdxl_config.get('hr_upscaler', 'R-ESRGAN 4x+'),
            "hr_second_pass_steps": self.sdxl_config.get('hr_second_pass_steps', 0),
            "batch_size": 1,
            "n_iter": 1,
            "save_images": False,
            "override_settings": {
                "sd_model_checkpoint": gen_type.model_name
            }
        }
        
        # ControlNet設定（ポーズモードに応じて制御）
        if self.pose_mode == "detection" and input_b64:
            controlnet_units = self.build_controlnet_units(input_b64)
            if controlnet_units:
                payload["alwayson_scripts"] = {
                    "controlnet": {
                        "args": controlnet_units
                    }
                }
        
        # ADetailer設定
        adetailer_config = self.build_adetailer_config(adetailer_negative)
        if "alwayson_scripts" not in payload:
            payload["alwayson_scripts"] = {}
        payload["alwayson_scripts"]["adetailer"] = adetailer_config
        
        return payload

    def build_controlnet_units(self, input_b64: str) -> list:
        """ControlNet設定構築"""
        units = []
        
        # OpenPose設定
        if self.controlnet_config.get('openpose', {}).get('enabled', True):
            openpose_config = self.controlnet_config['openpose']
            units.append({
                "input_image": input_b64,
                "module": openpose_config.get('module', 'openpose_full'),
                "model": openpose_config.get('model', 'control_v11p_sd15_openpose_fp16 [73c2b67d]'),
                "weight": openpose_config.get('weight', 0.8),
                "resize_mode": openpose_config.get('resize_mode', 1),
                "processor_res": openpose_config.get('processor_res', 512),
                "threshold_a": openpose_config.get('threshold_a', 0.5),
                "threshold_b": openpose_config.get('threshold_b', 0.5),
                "guidance_start": openpose_config.get('guidance_start', 0.0),
                "guidance_end": openpose_config.get('guidance_end', 1.0),
                "pixel_perfect": openpose_config.get('pixel_perfect', False),
                "control_mode": openpose_config.get('control_mode', 0),
                "enabled": True
            })
        
        # Depth設定
        if self.controlnet_config.get('depth', {}).get('enabled', False):
            depth_config = self.controlnet_config['depth']
            units.append({
                "input_image": input_b64,
                "module": depth_config.get('module', 'depth_midas'),
                "model": depth_config.get('model', 'control_v11f1p_sd15_depth_fp16 [4b72d323]'),
                "weight": depth_config.get('weight', 0.3),
                "resize_mode": depth_config.get('resize_mode', 1),
                "processor_res": depth_config.get('processor_res', 384),
                "threshold_a": depth_config.get('threshold_a', 0.5),
                "threshold_b": depth_config.get('threshold_b', 0.5),
                "guidance_start": depth_config.get('guidance_start', 0.0),
                "guidance_end": depth_config.get('guidance_end', 1.0),
                "pixel_perfect": depth_config.get('pixel_perfect', False),
                "control_mode": depth_config.get('control_mode', 0),
                "enabled": True
            })
        
        return units

    def build_adetailer_config(self, adetailer_negative: str) -> Dict[str, Any]:
        """ADetailer設定構築"""
        adetailer_config = self.config_manager.get_main_config().get('adetailer', {})
        return {
            "args": [{
                "ad_model": adetailer_config.get('model', 'face_yolov8n.pt'),
                "ad_prompt": adetailer_config.get('prompt', ''),
                "ad_negative_prompt": adetailer_negative,
                "ad_confidence": adetailer_config.get('confidence', 0.3),
                "ad_mask_blur": adetailer_config.get('mask_blur', 4),
                "ad_denoising_strength": adetailer_config.get('denoising_strength', 0.4),
                "ad_inpaint_only_masked": adetailer_config.get('inpaint_only_masked', True),
                "ad_inpaint_only_masked_padding": adetailer_config.get('inpaint_only_masked_padding', 32),
                "ad_inpaint_width": adetailer_config.get('inpaint_width', 512),
                "ad_inpaint_height": adetailer_config.get('inpaint_height', 512),
                "ad_use_steps": adetailer_config.get('use_steps', True),
                "ad_steps": adetailer_config.get('steps', 28),
                "ad_use_cfg_scale": adetailer_config.get('use_cfg_scale', True),
                "ad_cfg_scale": adetailer_config.get('cfg_scale', 7.0),
                "is_api": []
            }]
        }

    def save_generated_image(self, image_data: str, gen_type: GenerationType) -> str:
        """生成された画像を保存"""
        try:
            # Base64デコードして保存
            image_binary = base64.b64decode(image_data)
            
            # ファイル名生成
            timestamp = int(time.time())
            filename = f"sdxl_{gen_type.name}_{timestamp}.png"
            image_path = os.path.join(self.temp_dir, filename)
            
            with open(image_path, 'wb') as f:
                f.write(image_binary)
            
            file_size = os.path.getsize(image_path)
            self.logger.print_success(f"✅ 画像保存完了: {image_path} ({file_size} bytes)")
            
            return image_path
            
        except Exception as e:
            raise HybridGenerationError(f"画像保存エラー: {e}")

    def prepare_metadata(self, gen_type: GenerationType, generation_response: Dict[str, Any],
                        input_image_path: str) -> Dict[str, Any]:
        """メタデータ準備（フラット化対応版）"""
        now = datetime.now(JST)
        formatted_time = now.strftime("%Y%m%d%H%M%S")
        
        # 画像ID生成
        fast_suffix = "_fast" if self.fast_mode else ""
        ultra_suffix = "_ultra_safe"
        bedrock_suffix = "_bedrock" if self.bedrock_enabled else ""
        pose_suffix = f"_{self.pose_mode}" if self.pose_mode else ""
        image_id = f"sdxl_{gen_type.name}{fast_suffix}{ultra_suffix}{bedrock_suffix}{pose_suffix}_{formatted_time}"
        
        # パラメータ取得
        generation_params = generation_response.get('parameters', {})
        
        # ローカル用メタデータ（JSON保存用）
        local_metadata = {
            'image_id': image_id,
            'genre': gen_type.name,
            'generation_mode': 'sdxl_unified',
            'model_name': gen_type.model_name,
            'created_at': now.isoformat(),
            'pose_mode': self.pose_mode or 'detection',
            'fast_mode_enabled': self.fast_mode,
            'ultra_memory_safe_enabled': self.memory_manager.ultra_safe_mode,
            'bedrock_enabled': self.bedrock_enabled,
            'input_image': os.path.basename(input_image_path) if input_image_path else "pose_specification_mode",
            'sdxl_unified_generation': {
                'prompt': generation_params.get('prompt', ''),
                'negative_prompt': generation_params.get('negative_prompt', ''),
                'steps': self.sdxl_config.get('steps', 30),
                'cfg_scale': self.sdxl_config.get('cfg_scale', 7.0),
                'width': self.sdxl_config.get('width', 896),
                'height': self.sdxl_config.get('height', 1152),
                'model': gen_type.model_name,
                'sampler': self.sdxl_config.get('sampler_name', 'DPM++ 2M Karras')
            },
            'controlnet': {
                'enabled': self.pose_mode == "detection",
                'openpose': self.controlnet_config.get('openpose', {}),
                'depth': self.controlnet_config.get('depth', {})
            },
            'adetailer': {
                'enabled': True
            }
        }
        
        # AWS保存の場合はフラット化されたDynamoDB構造に変換
        if not self.local_mode:
            metadata = self.build_flat_dynamodb_item(local_metadata, generation_response)
        else:
            metadata = local_metadata
            
        return metadata

    def build_flat_dynamodb_item(self, local_meta: Dict[str, Any], generation_response: Dict[str, Any]) -> Dict[str, Any]:
        """
        ローカル生成メタデータ → フラット DynamoDB アイテム
        元のhybrid_bijo_generator_v10.pyの形式に完全準拠
        """
        now = datetime.now(JST)
        formatted_time = now.strftime("%Y%m%d%H%M%S")
        
        # ID 正規化
        orig = local_meta['image_id']
        image_id = orig.replace('local_sdxl_', 'sdxl_', 1) if orig.startswith('local_sdxl_') else orig
        
        # AWS設定取得
        aws_config = self.config_manager.get_aws_config()
        
        # パラメータ取得
        generation_params = generation_response.get('parameters', {})
        
        # ベースパラメータ（元のコードと同じ構造）
        base_params = {
            "generation_method": "sdxl_unified_ultra_safe_bedrock_pose_mode_model_switching",
            "input_image": local_meta.get('input_image', ''),
            "pose_mode": local_meta.get('pose_mode', 'detection'),
            "model": local_meta.get('model_name', ''),
            "fast_mode_enabled": str(self.fast_mode),
            "secure_random_enabled": "true",
            "ultra_memory_safe_enabled": str(self.memory_manager.ultra_safe_mode),
            "bedrock_enabled": str(self.bedrock_enabled),
            "fallback_level": "0"
        }
        
        # SDXL統合生成パラメータ
        sdxl_structured = {
            "prompt": generation_params.get('prompt', ''),
            "negative_prompt": generation_params.get('negative_prompt', ''),
            "steps": str(self.sdxl_config.get('steps', 30)),
            "cfg_scale": str(self.sdxl_config.get('cfg_scale', 7.0)),
            "sampler": self.sdxl_config.get('sampler_name', 'DPM++ 2M Karras'),
            "width": str(self.sdxl_config.get('width', 896)),
            "height": str(self.sdxl_config.get('height', 1152))
        }
        
        # ControlNetパラメータ
        controlnet_structured = {
            "enabled": str(self.pose_mode == "detection"),
            "openpose": {
                "enabled": str(self.controlnet_config.get('openpose', {}).get('enabled', True) and self.pose_mode == "detection"),
                "weight": str(self.controlnet_config.get('openpose', {}).get('weight', 0.8)),
                "model": self.controlnet_config.get('openpose', {}).get('model', 'control_v11p_sd15_openpose_fp16 [73c2b67d]')
            },
            "depth": {
                "enabled": str(self.controlnet_config.get('depth', {}).get('enabled', False) and self.pose_mode == "detection"),
                "weight": str(self.controlnet_config.get('depth', {}).get('weight', 0.3)),
                "model": self.controlnet_config.get('depth', {}).get('model', 'control_v11f1p_sd15_depth_fp16 [4b72d323]')
            }
        }
        
        # ADetailerパラメータ
        adetailer_config = self.config_manager.get_main_config().get('adetailer', {})
        adetailer_structured = {
            "enabled": str(adetailer_config.get('enabled', True)),
            "model": adetailer_config.get('model', 'face_yolov8n.pt'),
            "denoising_strength": str(adetailer_config.get('denoising_strength', 0.4))
        }
        
        # S3キー生成
        s3_key = f"image-pool/{local_meta.get('genre', '')}/{image_id}.png"
        
        # Bedrock用画像メタデータ準備
        image_metadata = {
            'genre': local_meta.get('genre', ''),
            'style': 'general',
            'imageId': image_id,
            'prompt': generation_params.get('prompt', ''),
            'pose_mode': local_meta.get('pose_mode', 'detection'),
            'model_name': local_meta.get('model_name', '')
        }
        
        # Bedrockコメント生成
        pre_generated_comments = self.generate_bedrock_comments(image_metadata)
        comment_generated_at = datetime.now(JST).isoformat() if pre_generated_comments else ""
        
        # DynamoDB アイテム（元のhybrid_bijo_generator_v10.pyと同じフラット構造）
        dynamodb_item = {
            "imageId": image_id,
            "s3Bucket": aws_config.get('s3_bucket', ''),
            "s3Key": s3_key,
            "genre": local_meta.get('genre', ''),
            "imageState": "unprocessed",
            "postingStage": "notposted",
            "createdAt": formatted_time,
            "suitableTimeSlots": self.default_suitable_slots,
            "preGeneratedComments": pre_generated_comments,
            "commentGeneratedAt": comment_generated_at,
            "sdParams": {
                "base": base_params,
                "sdxl_unified": sdxl_structured,
                "controlnet": controlnet_structured,
                "adetailer": adetailer_structured
            },
            # X投稿管理用フィールド
            "scheduledPostTime": "",
            "actualPostTime": formatted_time,
            "tweetId": "",
            "postingAttempts": 0,
            "lastErrorMessage": "",
            "movedToArchive": False
        }
        
        # Float→Decimal変換を確実に実行
        dynamodb_item = self.convert_floats_to_decimal(dynamodb_item)
        
        return dynamodb_item

    def convert_floats_to_decimal(self, obj):
        """再帰的にFloat値をDecimal型に変換"""
        if isinstance(obj, float):
            return Decimal(str(obj))
        elif isinstance(obj, dict):
            return {k: self.convert_floats_to_decimal(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.convert_floats_to_decimal(item) for item in obj]
        return obj

    def run_batch_generation(self, genre: str, count: int) -> int:
        """
        バッチ生成実行
        
        Args:
            genre: ジャンル
            count: 生成枚数
            
        Returns:
            int: 成功数
        """
        gen_type = self.get_generation_type(genre)
        if not gen_type:
            raise HybridGenerationError(f"未知のジャンル: {genre}")
        
        success_count = 0
        timer = ProcessTimer(self.logger)
        timer.start(f"{genre}バッチ生成（{count}枚）")
        
        for i in range(count):
            try:
                self.logger.print_status(f"🎨 {i+1}/{count} 生成中...")
                
                image_path, metadata = self.generate_image(gen_type)
                
                if self.upload_and_save(image_path, metadata):
                    success_count += 1
                
                # 画像間の処理間隔
                if i < count - 1:
                    interval = max(10, self.config_manager.get_main_config().get('performance', {}).get('api_rate_limit', 10))
                    self.logger.print_status(f"⏳ 処理間隔: {interval}秒待機")
                    time.sleep(interval)
                    
            except Exception as e:
                self.logger.print_error(f"❌ 生成エラー {i+1}: {e}")
                continue
        
        timer.end_and_report(success_count)
        return success_count

    def run_single_generation(self, genre: str) -> bool:
        """
        単発生成実行
        
        Args:
            genre: ジャンル
            
        Returns:
            bool: 成功時True
        """
        gen_type = self.get_generation_type(genre)
        if not gen_type:
            raise HybridGenerationError(f"未知のジャンル: {genre}")
        
        try:
            self.logger.print_status("🎨 単発画像生成開始...")
            
            image_path, metadata = self.generate_image(gen_type)
            
            if self.upload_and_save(image_path, metadata):
                self.logger.print_success("🎉 単発生成完了！")
                return True
            else:
                self.logger.print_error("❌ 保存処理失敗")
                return False
                
        except Exception as e:
            self.logger.print_error(f"❌ 単発生成エラー: {e}")
            return False

    def show_menu_and_process(self):
        """メニュー表示・処理実行"""
        self.logger.print_stage("🚀 Stable Diffusion画像生成ツール")
        
        # システム情報表示
        mode_text = "ローカルモード" if self.local_mode else "AWS連携モード"
        bedrock_text = "有効" if self.bedrock_enabled else "無効"
        memory_text = "有効" if self.memory_manager.memory_monitoring_enabled else "無効"
        
        print(f"🔧 実行モード: {mode_text}")
        print(f"🤖 Bedrock機能: {bedrock_text}")
        print(f"🧠 メモリ管理: {memory_text}")
        print(f"⚡ 高速化モード: {'有効' if self.fast_mode else '無効'}")
        
        while True:
            print("\n" + "="*60)
            print("🎨 Stable Diffusion画像生成ツール v7.0")
            print("="*60)
            print("1. バッチ画像生成")
            print("2. 単発画像生成")
            print("3. 設定確認")
            print("4. 終了")
            print("="*60)
            
            try:
                choice = input("選択 (1-4): ").strip()
                
                if choice == '1':
                    self._handle_batch_generation()
                elif choice == '2':
                    self._handle_single_generation()
                elif choice == '3':
                    self._show_system_info()
                elif choice == '4':
                    break
                else:
                    print("❌ 無効な選択です")
                    
            except KeyboardInterrupt:
                print("\n🛑 処理が中断されました")
                break
            except Exception as e:
                self.logger.print_error(f"❌ エラー: {e}")

    def _handle_batch_generation(self):
        """バッチ生成処理"""
        # ポーズモード選択
        self.select_pose_mode()
        
        # ジャンル選択
        available_genres = self.get_available_genres()
        print("\n📋 ジャンル選択")
        for i, genre in enumerate(available_genres, 1):
            gen_type = self.get_generation_type(genre)
            print(f"{i}. {genre} (モデル: {gen_type.model_name})")
        
        try:
            genre_choice = int(input(f"選択 (1-{len(available_genres)}): ").strip())
            if 1 <= genre_choice <= len(available_genres):
                selected_genre = available_genres[genre_choice - 1]
            else:
                print("❌ 無効な選択です")
                return
                
            count = int(input("生成枚数: ").strip())
            if count <= 0:
                print("❌ 無効な枚数です")
                return
            
            # 確認
            gen_type = self.get_generation_type(selected_genre)
            print(f"\n📋 バッチ生成確認")
            print(f"ジャンル: {selected_genre}")
            print(f"モデル: {gen_type.model_name}")
            print(f"ポーズモード: {self.pose_mode}")
            print(f"生成枚数: {count}枚")
            print(f"実行モード: {'ローカル' if self.local_mode else 'AWS連携'}")
            
            confirm = input("実行しますか？ (y/N): ").strip().lower()
            if confirm == 'y':
                self.logger.print_status("🎨 バッチ生成を開始します...")
                success_count = self.run_batch_generation(selected_genre, count)
                self.logger.print_success(f"🎉 バッチ生成完了: {success_count}/{count}枚成功")
                
        except ValueError:
            print("❌ 数値を正しく入力してください")
        except Exception as e:
            self.logger.print_error(f"❌ バッチ生成エラー: {e}")

    def _handle_single_generation(self):
        """単発生成処理"""
        # ポーズモード選択
        self.select_pose_mode()
        
        # ジャンル選択
        available_genres = self.get_available_genres()
        print("\n📋 ジャンル選択")
        for i, genre in enumerate(available_genres, 1):
            gen_type = self.get_generation_type(genre)
            print(f"{i}. {genre} (モデル: {gen_type.model_name})")
        
        try:
            genre_choice = int(input(f"選択 (1-{len(available_genres)}): ").strip())
            if 1 <= genre_choice <= len(available_genres):
                selected_genre = available_genres[genre_choice - 1]
            else:
                print("❌ 無効な選択です")
                return
                
            # 確認
            gen_type = self.get_generation_type(selected_genre)
            print(f"\n📋 単発生成確認")
            print(f"ジャンル: {selected_genre}")
            print(f"モデル: {gen_type.model_name}")
            print(f"ポーズモード: {self.pose_mode}")
            print(f"生成枚数: 1枚")
            print(f"実行モード: {'ローカル' if self.local_mode else 'AWS連携'}")
            
            confirm = input("実行しますか？ (y/N): ").strip().lower()
            if confirm == 'y':
                success = self.run_single_generation(selected_genre)
                if success:
                    self.logger.print_success("🎉 単発生成完了！")
                else:
                    self.logger.print_error("❌ 単発生成失敗")
                    
        except ValueError:
            print("❌ 数値を正しく入力してください")
        except Exception as e:
            self.logger.print_error(f"❌ 単発生成エラー: {e}")

    def _show_system_info(self):
        """システム情報表示"""
        print("\n" + "="*50)
        print("⚙️ システム設定情報")
        print("="*50)
        
        # 基本設定
        print(f"実行モード: {'ローカル' if self.local_mode else 'AWS連携'}")
        print(f"高速化モード: {'有効' if self.fast_mode else '無効'}")
        print(f"Bedrock機能: {'有効' if self.bedrock_enabled else '無効'}")
        
        # メモリ管理設定
        memory_stats = self.memory_manager.get_memory_stats()
        print(f"メモリ管理: {'有効' if memory_stats['monitoring_enabled'] else '無効'}")
        if memory_stats['monitoring_enabled']:
            print(f"  メモリ閾値: {memory_stats['threshold_percent']}%")
            print(f"  自動調整: {'有効' if memory_stats['auto_adjustment_enabled'] else '無効'}")
            print(f"  ウルトラセーフ: {'有効' if memory_stats['ultra_safe_mode'] else '無効'}")
        
        # 解像度設定
        current_resolution = self.memory_manager.get_current_resolution_config()
        print(f"現在の解像度: {current_resolution['width']}x{current_resolution['height']}")
        
        # 利用可能ジャンル
        available_genres = self.get_available_genres()
        print(f"利用可能ジャンル: {', '.join(available_genres)}")
        
        # モデル情報
        print("\nジャンル別モデル:")
        for genre in available_genres:
            gen_type = self.get_generation_type(genre)
            print(f"  {genre}: {gen_type.model_name}")
        
        # 現在のモデル
        current_model = self.get_current_model()
        print(f"\n現在のモデル: {current_model}")
        print("="*50)
