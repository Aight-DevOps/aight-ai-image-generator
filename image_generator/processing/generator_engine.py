#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
GeneratorEngine - SDXL統合生成実行
- execute_generation: 実際の画像生成呼び出し
"""

import time
import base64
import os
import requests
from common.logger import ColorLogger
from common.timer import ProcessTimer
from common.types import HybridGenerationError

class GeneratorEngine:
    """SDXL統合生成実行クラス"""

    def __init__(self, config, pose_mode, logger=None):
        """
        Args:
            config: 設定 dict
            pose_mode: 'detection' or 'specification'
        """
        self.config = config
        self.pose_mode = pose_mode
        self.logger = logger or ColorLogger()
        self.api_url = config['stable_diffusion']['api_url']
        self.verify_ssl = config['stable_diffusion']['verify_ssl']
        self.timeout = config['stable_diffusion']['timeout']

        # ControlNet, ADetailer 設定
        self.controlnet = config.get('controlnet', {})
        self.adetailer = config.get('adetailer', {})
        self.error_handling = config.get('error_handling', {})

    def execute_generation(self, prompt, negative_prompt, adetailer_negative, input_b64=None):
        """
        SDXL統合生成実行
        Returns: 生成画像ファイルパス, API レスポンス dict
        """
        def generation():
            timer = ProcessTimer(self.logger)
            timer.start("SDXL統合プロンプト生成")
            mode_text = "ポーズ指定モード" if self.pose_mode == "specification" else "ポーズ検出モード"
            self.logger.print_stage(f"🎨 SDXL統合プロンプト生成開始 ({mode_text})")
            # payload 構築
            payload = {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "steps": self.config['sdxl_generation']['steps'],
                "sampler_name": self.config['sdxl_generation']['sampler_name'],
                "cfg_scale": self.config['sdxl_generation']['cfg_scale'],
                "width": self.config['sdxl_generation']['width'],
                "height": self.config['sdxl_generation']['height'],
                "batch_size": 1,
                "override_settings": {
                    "sd_model_checkpoint": ""  # モデル切り替え後自己設定
                },
                "alwayson_scripts": {}
            }

            # ControlNet
            if self.pose_mode == "detection" and input_b64:
                payload["alwayson_scripts"]["controlnet"] = [{
                    "input_image": input_b64,
                    **self.controlnet['openpose']
                }, {
                    "input_image": input_b64,
                    **self.controlnet['depth']
                }]
            else:
                self.logger.print_status("🎯 ポーズ指定モード: ControlNetを無効化")

            # ADetailer
            payload["alwayson_scripts"]["adetailer"] = [{
                "ad_model": self.adetailer['model'],
                "ad_prompt": prompt,
                "ad_negative_prompt": adetailer_negative,
                "ad_confidence": self.adetailer['confidence'],
                "ad_mask_blur": self.adetailer['mask_blur'],
                "ad_denoising_strength": self.adetailer['denoising_strength'],
                "ad_inpaint_only_masked": self.adetailer['inpaint_only_masked'],
                "ad_inpaint_only_masked_padding": self.adetailer['inpaint_only_masked_padding'],
                "ad_inpaint_width": self.adetailer['inpaint_width'],
                "ad_inpaint_height": self.adetailer['inpaint_height'],
                "ad_use_steps": self.adetailer['use_steps'],
                "ad_steps": self.adetailer['steps'],
                "ad_use_cfg_scale": self.adetailer['use_cfg_scale'],
                "ad_cfg_scale": self.adetailer['cfg_scale'],
                "is_api": []
            }]

            # API call
            start = time.time()
            self.logger.print_status("🎨 SDXL統合生成 API 呼び出し中...")
            res = requests.post(f"{self.api_url}/sdapi/v1/txt2img",
                                json=payload,
                                timeout=self.timeout,
                                verify=self.verify_ssl)
            api_time = time.time() - start
            timer.mark_phase(f"API呼び出し ({timer.format_duration(api_time)})")
            res.raise_for_status()
            result = res.json()
            if 'error' in result:
                raise HybridGenerationError(f"SDXL統合APIエラー: {result['error']}")
            images = result.get('images')
            if not images:
                raise HybridGenerationError("画像生成に失敗しました")

            # 保存
            img_b64 = images[0]
            img_bytes = base64.b64decode(img_b64)
            file_path = os.path.join(self.config['temp_files']['directory'],
                                     f"sdxl_unified_{int(time.time())}.png")
            with open(file_path, 'wb') as f:
                f.write(img_bytes)
            timer.mark_phase("画像保存")
            timer.end_and_report()
            self.logger.print_success("🎨 生成完了")
            return file_path, result

        # エラーハンドリング付き実行
        from common.types import HybridGenerationError
        try:
            return generation()
        except Exception as e:
            raise HybridGenerationError(f"生成エラー: {e}")
