#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ImageProcessor - 画像前処理・最終仕上げ処理
- preprocess_input_image: SDXL用リサイズ
- encode_image_to_base64: Base64 エンコード
- apply_final_enhancement: ImageMagick or PIL 処理
"""

import os
import base64
import subprocess
from PIL import Image, ImageFilter, ImageEnhance
from common.logger import ColorLogger

class ImageProcessor:
    """画像前処理・最終仕上げ処理クラス"""

    def __init__(self, config, temp_dir, pose_mode):
        """
        Args:
            config: 設定 dict
            temp_dir: 一時ディレクトリパス
            pose_mode: 'detection' or 'specification'
        """
        self.logger = ColorLogger()
        self.sdxl_config = config.get('sdxl_generation', {})
        self.input_images_config = config.get('input_images', {})
        self.temp_dir = temp_dir
        self.pose_mode = pose_mode

    def preprocess_input_image(self, image_path: str) -> str | None:
        """
        SDXL 用入力画像リサイズ
        Returns: リサイズ後ファイルパス or None
        """
        # ポーズ指定モードではスキップ
        if self.pose_mode == "specification":
            self.logger.print_status("🎯 ポーズ指定モード: 前処理をスキップ")
            return None

        self.logger.print_status("ControlNet-SDXL用画像リサイズ中...")
        target_w = self.sdxl_config.get('width')
        target_h = self.sdxl_config.get('height')
        img = Image.open(image_path)
        img = img.resize((target_w, target_h), Image.LANCZOS)

        resized_path = os.path.join(self.temp_dir, "resized_sdxl_input.png")
        img.save(resized_path, "PNG",
                 optimize=True,
                 quality=self.input_images_config.get('resize_quality', 95))
        size = os.path.getsize(resized_path)
        self.logger.print_success(f"SDXL画像リサイズ完了: {size} bytes")
        return resized_path

    def encode_image_to_base64(self, image_path: str) -> str | None:
        """
        画像を Base64 エンコード
        Returns: Base64 文字列 or None
        """
        if self.pose_mode == "specification" or image_path is None:
            return None
        with open(image_path, 'rb') as f:
            data = f.read()
        b64 = base64.b64encode(data).decode('utf-8')
        self.logger.print_status(f"Base64エンコードサイズ: {len(b64)} 文字")
        return b64

    def apply_final_enhancement(self, image_path: str):
        """
        最終仕上げ処理（ImageMagick or PIL）
        """
        self.logger.print_status("最終仕上げ処理中（顔品質特化）...")
        if shutil.which('convert'):
            try:
                cmd = [
                    'convert', image_path,
                    '-unsharp', '1.2x1.0+1.0+0.02',
                    '-contrast-stretch', '0.03%x0.03%',
                    '-modulate', '102,110,100',
                    '-define', 'png:compression-level=0',
                    image_path
                ]
                res = subprocess.run(cmd, capture_output=True, timeout=30, text=True)
                if res.returncode == 0:
                    self.logger.print_success("✅ ImageMagick最終仕上げ処理完了")
                    return
                else:
                    self.logger.print_warning(f"⚠️ ImageMagick処理エラー: {res.stderr}")
            except Exception as e:
                self.logger.print_warning(f"⚠️ ImageMagick処理エラー: {e}")

        # PIL 代替処理
        self.apply_pil_enhancement(image_path)

    def apply_pil_enhancement(self, image_path: str):
        """
        PIL 代替仕上げ処理
        """
        try:
            img = Image.open(image_path)
            # アンシャープマスク
            img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=100, threshold=1))
            # コントラスト
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.05)
            # 色彩調整
            brightness = ImageEnhance.Brightness(img)
            img = brightness.enhance(1.02)
            color = ImageEnhance.Color(img)
            img = color.enhance(1.10)
            img.save(image_path, "PNG", optimize=True, compress_level=0)
            self.logger.print_success("✅ PIL代替仕上げ処理完了")
        except Exception as e:
            self.logger.print_error(f"❌ PIL仕上げ処理エラー: {e}")
