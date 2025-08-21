#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
GeneratorEngine - SDXL統合生成実行
- execute_generation: SDXL統合プロンプト生成（ControlNet + ADetailer 対応）
ポーズ検出モード対応版（設定ファイル完全対応版）
"""

import time
import base64
import os
import requests
import json
from common.logger import ColorLogger
from common.timer import ProcessTimer
from common.types import HybridGenerationError

class GeneratorEngine:
    """SDXL統合生成実行クラス（ポーズ検出モード対応版・設定ファイル完全対応）"""

    def __init__(self, config: dict, pose_mode: str, logger=None):
        self.config = config
        self.pose_mode = pose_mode
        self.logger = logger or ColorLogger()
        
        sd_cfg = config['stable_diffusion']
        self.api_url = sd_cfg['api_url']
        self.timeout = sd_cfg['timeout']
        self.verify_ssl = sd_cfg['verify_ssl']
        
        # ControlNet, ADetailer 設定
        self.controlnet = config.get('controlnet', {})
        self.adetailer = config.get('adetailer', {})
        
        # ★ 追加: 初期化時のデバッグ出力
        self.logger.print_status(f"🎯 GeneratorEngine初期化 - ポーズモード: {self.pose_mode}")

    def execute_generation(self, prompt: str, negative_prompt: str,
                          adetailer_negative: str, input_b64: str=None):
        """
        SDXL統合プロンプト生成（ポーズモード完全対応版）
        Returns: (保存パス, API レスポンス)
        """
        def _generate():
            timer = ProcessTimer(self.logger)
            timer.start("SDXL統合プロンプト生成")

            mode_text = "ポーズ指定モード" if self.pose_mode=="specification" else "ポーズ検出モード"
            self.logger.print_stage(f"🎨 SDXL統合生成開始 ({mode_text})")

            # ★ 重要な修正: ポーズモードの詳細デバッグと判定強化
            self.logger.print_status(f"🔍 詳細ポーズモード情報:")
            self.logger.print_status(f"  - pose_mode値: '{self.pose_mode}'")
            self.logger.print_status(f"  - input_b64存在: {'あり' if input_b64 else 'なし'}")
            if input_b64:
                self.logger.print_status(f"  - Base64データサイズ: {len(input_b64)} 文字")
            
            # ★ 修正: ControlNet適用条件の明確化
            controlnet_should_be_enabled = (self.pose_mode == "detection" and input_b64 is not None)
            self.logger.print_status(f"🔍 ControlNet適用判定:")
            self.logger.print_status(f"  - 条件1 (pose_mode=='detection'): {self.pose_mode == 'detection'}")
            self.logger.print_status(f"  - 条件2 (input_b64 is not None): {input_b64 is not None}")
            self.logger.print_status(f"  - 最終判定: {controlnet_should_be_enabled}")

            # 1. 基本Payload設定
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

            # ★ 修正: 2. ControlNet設定（完全対応版）
            if controlnet_should_be_enabled:
                self.logger.print_success("🎯 ControlNet（OpenPose + Depth）を有効化します")
                controlnet_args = []

                # OpenPose設定（設定ファイル完全対応版）
                if self.controlnet.get('openpose', {}).get('enabled', False):
                    openpose_config = {
                        'enabled': True,  # ★ 修正: 明示的にTrueに設定
                        'image': input_b64,
                        'module': self.controlnet['openpose'].get('module', 'dw_openpose_full'),
                        'model': self.controlnet['openpose'].get('model', 'control_v11p_sd15_openpose_fp16 [73c2b67d]'),
                        'weight': self.controlnet['openpose'].get('weight', 0.8),
                        'resize_mode': self.controlnet['openpose'].get('resize_mode', 'Just Resize'),
                        'low_vram': False,
                        'processor_res': self.controlnet['openpose'].get('processor_res', 512),
                        'threshold_a': self.controlnet['openpose'].get('threshold_a', 0.5),
                        'threshold_b': self.controlnet['openpose'].get('threshold_b', 0.5),
                        'guidance_start': self.controlnet['openpose'].get('guidance_start', 0.0),
                        'guidance_end': self.controlnet['openpose'].get('guidance_end', 0.7),
                        'control_mode': self.controlnet['openpose'].get('control_mode', 'ControlNet is more important'),
                        'pixel_perfect': self.controlnet['openpose'].get('pixel_perfect', True)
                    }
                    
                    controlnet_args.append(openpose_config)
                    self.logger.print_success(f"✅ OpenPose設定完了: {openpose_config['model']}")
                    self.logger.print_status(f"  - Weight: {openpose_config.get('weight')}")
                    self.logger.print_status(f"  - Module: {openpose_config.get('module')}")
                    self.logger.print_status(f"  - Control Mode: {openpose_config.get('control_mode')}")
                else:
                    self.logger.print_warning("⚠️ OpenPose設定が無効です")

                # Depth設定（設定ファイル完全対応版）
                if self.controlnet.get('depth', {}).get('enabled', False):
                    depth_config = {
                        'enabled': True,  # ★ 修正: 明示的にTrueに設定
                        'image': input_b64,
                        'module': self.controlnet['depth'].get('module', 'depth_midas'),
                        'model': self.controlnet['depth'].get('model', 'control_v11f1p_sd15_depth_fp16 [4b72d323]'),
                        'weight': self.controlnet['depth'].get('weight', 0.6),
                        'resize_mode': self.controlnet['depth'].get('resize_mode', 'Crop and Resize'),
                        'low_vram': False,
                        'processor_res': self.controlnet['depth'].get('processor_res', 512),
                        'threshold_a': self.controlnet['depth'].get('threshold_a', 0.5),
                        'threshold_b': self.controlnet['depth'].get('threshold_b', 0.5),
                        'guidance_start': self.controlnet['depth'].get('guidance_start', 0.0),
                        'guidance_end': self.controlnet['depth'].get('guidance_end', 1.0),
                        'control_mode': self.controlnet['depth'].get('control_mode', 'Balanced'),
                        'pixel_perfect': self.controlnet['depth'].get('pixel_perfect', True)
                    }
                    
                    controlnet_args.append(depth_config)
                    self.logger.print_success(f"✅ Depth設定完了: {depth_config['model']}")
                    self.logger.print_status(f"  - Weight: {depth_config.get('weight')}")
                    self.logger.print_status(f"  - Module: {depth_config.get('module')}")
                    self.logger.print_status(f"  - Control Mode: {depth_config.get('control_mode')}")
                else:
                    self.logger.print_warning("⚠️ Depth設定が無効です")

                if controlnet_args:
                    payload["alwayson_scripts"]["controlnet"] = {
                        "args": controlnet_args
                    }
                    self.logger.print_success(f"✅ ControlNet有効化完了: {len(controlnet_args)}個のモデル")
                    
                    # ★ 追加: ControlNet有効時の詳細確認
                    self.logger.print_status(f"🔍 ControlNet詳細確認:")
                    for i, arg in enumerate(controlnet_args):
                        self.logger.print_status(f"  - [{i}] {arg.get('module')} -> {arg.get('model')[:30]}...")
                        self.logger.print_status(f"  - [{i}] enabled: {arg.get('enabled')}, weight: {arg.get('weight')}")
                else:
                    self.logger.print_error("❌ ControlNet有効化失敗: 有効なモデルがありません")
            else:
                # ★ 修正: ControlNet無効時の明確なメッセージ
                if self.pose_mode == "specification":
                    self.logger.print_success("✅ ControlNet無効化: ポーズ指定モード（プロンプトベース生成）")
                    self.logger.print_status("🎯 プロンプトに含まれるポーズ指定が使用されます")
                else:
                    self.logger.print_warning("⚠️ ControlNet無効化: 入力画像がありません")

            # 3. ADetailer設定（既存のまま）
            adetailer_args = []
            
            # 新しいmodels設定があるかチェック
            if 'models' in self.adetailer and self.adetailer['models']:
                # 複数モデル設定を使用（設定ファイル完全対応）
                for model_config in self.adetailer['models']:
                    if model_config.get('model', 'None') != 'None':
                        adetailer_args.append({
                            "ad_model": model_config.get('model', 'face_yolov8n.pt'),
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
                        self.logger.print_status(f"🔧 ADetailer: {model_config.get('name', 'Unknown')} モデル設定完了")
                
                self.logger.print_status(f"🔧 ADetailer: {len(adetailer_args)}個のモデルを設定")
            else:
                # 後方互換性: 既存の単一モデル設定を使用
                if self.adetailer.get('model', 'None') != 'None':
                    adetailer_args.append({
                        "ad_model": self.adetailer.get('model', 'face_yolov8n.pt'),
                        "ad_prompt": prompt,
                        "ad_negative_prompt": adetailer_negative,
                        "ad_confidence": self.adetailer.get('confidence', 0.3),
                        "ad_mask_blur": self.adetailer.get('mask_blur', 4),
                        "ad_denoising_strength": self.adetailer.get('denoising_strength', 0.4),
                        "ad_inpaint_only_masked": self.adetailer.get('inpaint_only_masked', True),
                        "ad_inpaint_only_masked_padding": self.adetailer.get('inpaint_only_masked_padding', 32),
                        "ad_inpaint_width": self.adetailer.get('inpaint_width', 512),
                        "ad_inpaint_height": self.adetailer.get('inpaint_height', 640),
                        "ad_use_steps": self.adetailer.get('use_steps', False),
                        "ad_steps": self.adetailer.get('steps', 12),
                        "ad_use_cfg_scale": self.adetailer.get('use_cfg_scale', False),
                        "ad_cfg_scale": self.adetailer.get('cfg_scale', 6.5),
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

            # ★ 追加: 最終確認ログ（強化版）
            script_count = len(payload["alwayson_scripts"])
            self.logger.print_status(f"📋 最終ペイロード確認:")
            self.logger.print_status(f"  - アクティブスクリプト数: {script_count}")
            self.logger.print_status(f"  - ControlNet: {'有効' if 'controlnet' in payload['alwayson_scripts'] else '無効'}")
            self.logger.print_status(f"  - ADetailer: {'有効' if 'adetailer' in payload['alwayson_scripts'] else '無効'}")
            self.logger.print_status(f"  - プロンプト長: {len(prompt)}文字")

            # ★ 追加: プロンプト内容の確認（ポーズ指定モード時）
            if self.pose_mode == "specification":
                # プロンプトにBREAKとposeが含まれているかチェック
                has_pose_in_prompt = "pose" in prompt.lower() or "BREAK" in prompt
                self.logger.print_status(f"🔍 ポーズ指定モード確認:")
                self.logger.print_status(f"  - プロンプトにポーズ要素: {'含まれています' if has_pose_in_prompt else '含まれていません'}")
                if has_pose_in_prompt:
                    # ポーズ関連部分を抽出して表示
                    pose_parts = [part.strip() for part in prompt.split(',') if 'pose' in part.lower() or 'BREAK' in part]
                    if pose_parts:
                        self.logger.print_status(f"  - 検出されたポーズ要素: {pose_parts[0][:50]}...")

            # 4. API 呼び出し
            start = time.time()
            self.logger.print_status("🎨 SDXL 生成 API 呼び出し中...")
            
            try:
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
                    raise HybridGenerationError("画像生成失敗: imagesが空")
                
                self.logger.print_success(f"✅ API呼び出し成功: {len(images)}枚生成")
                
            except requests.exceptions.RequestException as e:
                raise HybridGenerationError(f"API接続エラー: {e}")
            except Exception as e:
                raise HybridGenerationError(f"API処理エラー: {e}")

            # 5. 画像保存
            b64_image = images[0]
            img_data = base64.b64decode(b64_image)
            fname = f"sdxl_unified_{int(time.time())}.png"
            path = os.path.join(self.config['temp_files']['directory'], fname)
            
            try:
                with open(path, 'wb') as f:
                    f.write(img_data)
                
                file_size = len(img_data)
                self.logger.print_success(f"✅ 画像保存完了: {fname} ({file_size} bytes)")
                
            except Exception as e:
                raise HybridGenerationError(f"画像保存エラー: {e}")
            
            timer.mark_phase("画像保存")
            timer.end_and_report()
            
            # ★ 追加: 生成完了時の最終確認ログ
            final_mode = "ポーズ指定モード（プロンプトベース）" if self.pose_mode == "specification" else "ポーズ検出モード（ControlNetベース）"
            self.logger.print_success(f"🎨 生成完了 - {final_mode}")
            
            return path, result

        # メモリ安全実行
        try:
            return _generate()
        except HybridGenerationError:
            raise
        except Exception as e:
            raise HybridGenerationError(f"予期しないエラー: {e}")
