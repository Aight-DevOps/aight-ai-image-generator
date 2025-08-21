#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
GeneratorEngine - SDXL統合生成実行
- execute_generation: SDXL統合プロンプト生成（ControlNet + ADetailer 対応）
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

    def __init__(self, config: dict, pose_mode: str, logger=None):
        self.config = config
        self.pose_mode = pose_mode
        self.logger = logger or ColorLogger()
        sd_cfg = config['stable_diffusion']
        self.api_url    = sd_cfg['api_url']
        self.timeout    = sd_cfg['timeout']
        self.verify_ssl = sd_cfg['verify_ssl']
        # ControlNet, ADetailer 設定
        self.controlnet = config.get('controlnet', {})
        self.adetailer  = config.get('adetailer', {})

    def execute_generation(self, prompt: str, negative_prompt: str,
                           adetailer_negative: str, input_b64: str=None):
        """
        SDXL統合プロンプト生成
        Returns: (保存パス, API レスポンス)
        """
        def _generate():
            timer = ProcessTimer(self.logger)
            timer.start("SDXL統合プロンプト生成")
            mode_text = "ポーズ指定モード" if self.pose_mode=="specification" else "ポーズ検出モード"
            self.logger.print_stage(f"🎨 SDXL統合生成開始 ({mode_text})")

            # １. Payload
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
                    "sd_model_checkpoint": ""  # ModelManager 経由で設定
                },
                "alwayson_scripts": {}
            }
            # 2. ControlNet
            if self.pose_mode=="detection" and input_b64:
                payload["alwayson_scripts"]["controlnet"] = {
                    "args": [
                        {
                            "input_image": input_b64,
                            **self.controlnet['openpose']
                        },
                        {
                            "input_image": input_b64,
                            **self.controlnet['depth']
                        }
                    ]
                }
            else:
                self.logger.print_status("🎯 ControlNet 無効")

            # 3. ADetailer
            adetailer_args = []
            
            # 新しいmodels設定があるかチェック
            if 'models' in self.adetailer and self.adetailer['models']:
                # 複数モデル設定を使用
                for model_config in self.adetailer['models']:
                    if model_config.get('model', 'None') != 'None':
                        adetailer_args.append({
                            "ad_model": model_config['model'],
                            "ad_prompt": prompt,
                            "ad_negative_prompt": adetailer_negative,
                            "ad_confidence": model_config.get('confidence', 0.3),
                            "ad_mask_blur": model_config.get('mask_blur', 4),
                            "ad_denoising_strength": model_config.get('denoising_strength', 0.4),
                            "ad_inpaint_only_masked": model_config.get('inpaint_only_masked', True),
                            "ad_inpaint_only_masked_padding": model_config.get('inpaint_only_masked_padding', 32),
                            "ad_inpaint_width": model_config.get('inpaint_width', 512),
                            "ad_inpaint_height": model_config.get('inpaint_height', 640),
                            "ad_use_steps": model_config.get('use_steps', False),
                            "ad_steps": model_config.get('steps', 12),
                            "ad_use_cfg_scale": model_config.get('use_cfg_scale', False),
                            "ad_cfg_scale": model_config.get('cfg_scale', 6.5),
                            "is_api": []
                        })
                
                self.logger.print_status(f"🔧 ADetailer: {len(adetailer_args)}個のモデルを設定")
            else:
                # 後方互換性: 既存の単一モデル設定を使用
                if self.adetailer.get('model', 'None') != 'None':
                    adetailer_args.append({
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
                    })
                
                self.logger.print_warning("⚠️ ADetailer: 旧設定を使用中（単一モデル）")
            
            # ADetailerの設定をpayloadに追加
            if adetailer_args:
                payload["alwayson_scripts"]["adetailer"] = {
                    "args": adetailer_args
                }
                self.logger.print_success(f"✅ ADetailer設定完了: {len(adetailer_args)}個のモデル")
            else:
                self.logger.print_status("📋 ADetailer: 無効またはモデル未設定")

            # 4. API 呼び出し
            start = time.time()
            self.logger.print_status("🎨 SDXL 生成 API 呼び出し中...")
            resp = requests.post(f"{self.api_url}/sdapi/v1/txt2img", json=payload,
                                 timeout=self.timeout, verify=self.verify_ssl)
            api_time = time.time() - start
            timer.mark_phase(f"API呼び出し ({timer.format_duration(api_time)})")
            resp.raise_for_status()
            result = resp.json()
            if 'error' in result:
                raise HybridGenerationError(f"APIエラー: {result['error']}")
            images = result.get('images', [])
            if not images:
                raise HybridGenerationError("画像生成失敗")

            # 5. 保存
            b64 = images[0]
            img_data = base64.b64decode(b64)
            fname = f"sdxl_unified_{int(time.time())}.png"
            path = os.path.join(self.config['temp_files']['directory'], fname)
            with open(path, 'wb') as f:
                f.write(img_data)
            timer.mark_phase("画像保存")
            timer.end_and_report()
            self.logger.print_success("🎨 生成完了")
            return path, result

        # メモリ安全実行
        from common.types import HybridGenerationError
        return _generate()
