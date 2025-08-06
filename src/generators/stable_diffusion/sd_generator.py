#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stable Diffusion Generator - SD専用メイン生成器クラス
"""

import os
import time
import base64
import requests
from io import BytesIO
from typing import Tuple, Dict, Any
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import torch
import urllib3
from PIL import Image

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
    """Stable Diffusion専用画像生成器クラス"""

    def __init__(self, config_manager: ConfigManager):
        super().__init__(config_manager)
        self.logger = ColorLogger()
        self.logger.print_stage("🚀 Stable Diffusion生成器 初期化中...")
        self.sd_api_config = config_manager.get_stable_diffusion_config()
        self.sdxl_config = config_manager.get_sdxl_generation_config()
        self.controlnet_config = config_manager.get_controlnet_config()
        self.input_images_config = config_manager.get_input_images_config()
        self.adetailer_config = config_manager.get_adetailer_config()
        self.memory_manager = MemoryManager(config_manager)
        self.prompt_builder = SDPromptBuilder(config_manager)
        self.image_processor = SDImageProcessor(config_manager)
        self.pose_mode = None
        temp_conf = config_manager.get_temp_files_config()
        self.temp_dir = temp_conf.get("directory", "/tmp/sd_process")
        os.makedirs(self.temp_dir, exist_ok=True)
        self.input_image_pool = None
        self.random_element_generator = None
        self.current_model = None
        self.setup_enhanced_randomness()
        self.logger.print_success("✅ SD生成器初期化完了")

    def setup_enhanced_randomness(self):
        """拡張ランダム機能の初期化"""
        try:
            data = self.config_manager.load_config("random_elements")
            specific = data.get("specific_random_elements", {})
            general = data.get("general_random_elements", {})
            self.input_image_pool = InputImagePool(
                self.input_images_config["source_directory"],
                self.input_images_config["supported_formats"],
                history_file=os.path.join(self.temp_dir, "image_history.json")
            )
            self.random_element_generator = RandomElementGenerator(
                specific, general,
                history_file=os.path.join(self.temp_dir, "element_history.json")
            )
            self.prompt_builder.set_random_element_generator(self.random_element_generator)
        except Exception as e:
            raise HybridGenerationError(f"拡張ランダム機能初期化エラー: {e}")

    def generate_image(self, gen_type: GenerationType, **kwargs) -> Tuple[str, Dict[str, Any]]:
        """単一画像生成"""
        try:
            self.memory_manager.prepare_for_generation()
            self.ensure_model_for_generation_type(gen_type)
            inp = self.input_image_pool.get_next_image()
            proc = self.image_processor.preprocess_input_image(inp)
            b64 = self.image_processor.encode_image_to_base64(proc)
            prompt, neg, ad_neg = self.prompt_builder.build_prompts(gen_type)
            path, resp = self.execute_generation(gen_type, b64, prompt, neg, ad_neg)
            self.image_processor.apply_final_enhancement(path)
            meta = self.prepare_metadata(gen_type, resp, inp)
            self.memory_manager.cleanup_after_generation()
            return path, meta
        except Exception as e:
            self.logger.print_error(f"❌ 画像生成エラー: {e}")
            raise HybridGenerationError(f"画像生成失敗: {e}")

    def build_prompts(self, gen_type: GenerationType, mode: str = "auto") -> Tuple[str, str]:
        p, n, _ = self.prompt_builder.build_prompts(gen_type, mode)
        return p, n

    def ensure_model_for_generation_type(self, gen_type: GenerationType):
        target = gen_type.model_name
        if self.current_model == target:
            return
        self.logger.print_status(f"🔄 モデル切り替え: {self.current_model}→{target}")
        try:
            url = f"{self.sd_api_config.get('api_url')}/sdapi/v1/options"
            resp = requests.post(url, json={"sd_model_checkpoint": target}, timeout=180, verify=False)
            if resp.status_code != 200 or not self.verify_model_switch(target):
                raise ModelSwitchError(f"切り替え失敗: {target}")
            self.current_model = target
            time.sleep(self.config_manager.get_main_config().get("model_switching", {}).get("wait_after_switch", 10))
        except Exception as e:
            raise ModelSwitchError(f"モデル切り替えエラー: {e}")

    def verify_model_switch(self, expected: str) -> bool:
        url = f"{self.sd_api_config.get('api_url')}/sdapi/v1/options"
        for _ in range(self.config_manager.get_main_config().get("model_switching", {}).get("verification_retries", 3)):
            r = requests.get(url, timeout=30, verify=False)
            if r.status_code == 200 and expected in r.json().get("sd_model_checkpoint", ""):
                return True
            time.sleep(5)
        return False

    def execute_generation(self, gen_type: GenerationType, input_b64: str,
                           prompt: str, negative: str, ad_neg: str) -> Tuple[str, Dict[str, Any]]:
        url = f"{self.sd_api_config.get('api_url')}/sdapi/v1/txt2img"
        payload = {
            "prompt": prompt,
            "negative_prompt": negative,
            "steps": self.sdxl_config.get("steps", 30),
            "cfg_scale": self.sdxl_config.get("cfg_scale", 7.0),
            "width": self.memory_manager.get_current_resolution_config().get("width", 896),
            "height": self.memory_manager.get_current_resolution_config().get("height", 1152),
            "alwayson_scripts": {}
        }
        if self.pose_mode == "detection":
            cn = self.build_controlnet_units(input_b64)
            if cn:
                payload["alwayson_scripts"]["ControlNet"] = {"args": cn}
        if self.adetailer_config.get("enabled", True):
            payload["alwayson_scripts"]["ADetailer"] = self.build_adetailer_config(ad_neg)
        resp = requests.post(url, json=payload, timeout=self.sd_api_config.get("timeout", 3600), verify=False)
        if resp.status_code != 200:
            raise HybridGenerationError(f"API呼び出し失敗:{resp.status_code}")
        data = resp.json()
        img_data = data.get("images", [None])[0]
        if not img_data:
            raise HybridGenerationError("画像データなし")
        path = self.save_generated_image(img_data, gen_type)
        return path, data

    def build_controlnet_units(self, input_b64: str) -> list:
        units = []
        cfg = self.controlnet_config.get("openpose", {})
        if cfg.get("enabled", True):
            units.append({
                "input_image": input_b64,
                "model": cfg.get("model"),
                "module": cfg.get("module"),
                "weight": cfg.get("weight", 0.8),
                "resize_mode": cfg.get("resize_mode", "Just Resize"),
                "processor_res": cfg.get("processor_res", 512)
            })
        return units

    def build_adetailer_config(self, negative: str) -> Dict[str, Any]:
        ad = self.adetailer_config
        return {
            "args": [
                {"ad_model": ad.get("model")},
                {"ad_negative_prompt": negative},
                {"ad_steps": ad.get("steps", 12)},
                {"ad_cfg_scale": ad.get("cfg_scale", 6.5)}
            ]
        }

    def save_generated_image(self, img_b64: str, gen_type: GenerationType) -> str:
        img_bytes = base64.b64decode(img_b64)
        img = Image.open(BytesIO(img_bytes))
        ts = datetime.now(JST).strftime("%Y%m%d_%H%M%S_%f")[:-3]
        fn = f"sd_{gen_type.name}_{ts}.png"
        out = os.path.join(self.temp_dir, fn)
        img.save(out, "PNG", optimize=True)
        return out

    def prepare_metadata(self, gen_type: GenerationType, response: Dict[str, Any], input_path: str) -> Dict[str, Any]:
        now = datetime.now(JST).isoformat()
        meta = {
            "image_id": f"sd_{gen_type.name}_{datetime.now(JST).strftime('%Y%m%d%H%M%S')}",
            "genre": gen_type.name,
            "generation_mode": "sdxl_unified",
            "model_name": gen_type.model_name,
            "created_at": now,
            "input_image": os.path.basename(input_path),
            "sdxl_unified": response,
            "s3Key": f"image-pool/{gen_type.name}/{now}.png",
            "imageId": f"sd_{gen_type.name}_{datetime.now(JST).timestamp()}"
        }
        def _conv(o):
            if isinstance(o, float):
                return Decimal(str(o))
            if isinstance(o, dict):
                return {k: _conv(v) for k, v in o.items()}
            if isinstance(o, list):
                return [_conv(v) for v in o]
            return o
        return _conv(meta)
