#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ImageProcessor - 画像前処理・最終仕上げ処理
- preprocess_input_image: SDXL用リサイズ
- encode_image_to_base64: Base64 エンコード
- apply_final_enhancement: ImageMagick / PIL 仕上げ
"""

import os
import time
import base64
import subprocess
import shutil
from PIL import Image, ImageFilter, ImageEnhance
from common.logger import ColorLogger
from datetime import datetime, timezone, timedelta

# JST
JST = timezone(timedelta(hours=9))

class ImageProcessor:
    """画像前処理・最終仕上げ処理クラス"""

    def __init__(self, config: dict, temp_dir: str, pose_mode: str):
        self.logger = ColorLogger()
        self.config = config
        self.temp_dir = temp_dir
        self.pose_mode = pose_mode

        self.sdxl_cfg = config.get('sdxl_generation', {})
        self.input_cfg = config.get('input_images', {})

    def preprocess_input_image(self, image_path: str) -> str:
        """
        ControlNet-SDXL 用画像前処理（リサイズ）
        ポーズ指定モードではスキップ
        """
        if self.pose_mode == "specification":
            self.logger.print_status("🎯 ポーズ指定モード: 前処理スキップ")
            return None

        if not image_path or not os.path.exists(image_path):
            self.logger.print_warning("⚠️ 入力画像が存在しません")
            return None

        self.logger.print_status("🔄 画像リサイズ開始（ポーズ検出モード）")

        w = self.sdxl_cfg.get('width', 896)
        h = self.sdxl_cfg.get('height', 1152)
        
        try:
            img = Image.open(image_path).convert("RGB")
            original_size = img.size
            img = img.resize((w, h), Image.LANCZOS)
            
            out = os.path.join(self.temp_dir, "resized_sdxl_input.png")
            img.save(out, "PNG", optimize=True, quality=self.input_cfg.get('resize_quality', 95))
            
            size = os.path.getsize(out)
            self.logger.print_success(f"✅ リサイズ完了: {original_size} → {(w, h)}, {size} bytes")
            return out
            
        except Exception as e:
            self.logger.print_error(f"❌ 画像リサイズエラー: {e}")
            return None


    def encode_image_to_base64(self, image_path: str) -> str:
        """画像を Base64 エンコード"""
        if self.pose_mode == "specification" or not image_path:
            return None
        with open(image_path, 'rb') as f:
            data = f.read()
        b64 = base64.b64encode(data).decode('utf-8')
        self.logger.print_status(f"🔄 Base64 エンコード: {len(b64)} 文字")
        return b64

    def apply_final_enhancement(self, image_path: str):
        """
        最終仕上げ処理  
        - ImageMagick があればシェルコマンドで
        - なければ PIL でアンシャープマスク・コントラスト・彩度調整
        """
        self.logger.print_status("✨ 最終仕上げ処理開始")
        # ImageMagick が使えるか
        if shutil.which('convert'):
            try:
                cmd = [
                    "convert", image_path,
                    "-unsharp", "1.2x1.0+1.0+0.02",
                    "-contrast-stretch", "0.03%x0.03%",
                    "-modulate", "102,110,100",
                    "-define", "png:compression-level=0",
                    image_path
                ]
                res = subprocess.run(cmd, capture_output=True, timeout=30, text=True)
                if res.returncode == 0:
                    self.logger.print_success("✅ ImageMagick 仕上げ完了")
                    return
                else:
                    self.logger.print_warning(f"⚠️ ImageMagick エラー: {res.stderr}")
            except Exception as e:
                self.logger.print_warning(f"⚠️ ImageMagick 例外: {e}")

        # PIL 代替処理
        self._apply_pil(image_path)

    def _apply_pil(self, image_path: str):
        """PIL 仕上げ処理"""
        try:
            img = Image.open(image_path).convert("RGB")
            # アンシャープマスク
            img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=100, threshold=1))
            # コントラスト
            img = ImageEnhance.Contrast(img).enhance(1.05)
            # 彩度・明度調整
            img = ImageEnhance.Brightness(img).enhance(1.02)
            img = ImageEnhance.Color(img).enhance(1.10)
            # 保存
            img.save(image_path, "PNG", optimize=True, compress_level=0)
            self.logger.print_success("✅ PIL 仕上げ完了")
        except Exception as e:
            self.logger.print_error(f"❌ PIL 仕上げエラー: {e}")
