#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stable Diffusion Image Processor - SD専用画像後処理クラス
"""

import os
import time
from PIL import Image, ImageEnhance
from typing import Dict, Any
from ...core.config_manager import ConfigManager
from ...core.exceptions import ImageProcessingError

class SDImageProcessor:
    """Stable Diffusion専用画像後処理クラス"""

    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager
        tf = config_manager.get_temp_files_config()
        self.temp_dir = tf.get("directory", "/tmp/sd_process")
        os.makedirs(self.temp_dir, exist_ok=True)
        ii = config_manager.get_input_images_config()
        self.quality = ii.get("resize_quality", 95)

    def preprocess_input_image(self, input_path: str) -> str:
        try:
            img = Image.open(input_path)
            if img.mode == "RGBA":
                bg = Image.new("RGB", img.size, (255,255,255))
                bg.paste(img, mask=img.split()[-1])
                img = bg
            elif img.mode != "RGB":
                img = img.convert("RGB")
            w, h = img.size
            cfg = self.config.get_sdxl_generation_config()
            tw, th = cfg.get("width",896), cfg.get("height",1152)
            ar = w/h; tar = tw/th
            if ar>tar:
                nh = int(tw/ar); nw = tw
            else:
                nw = int(th*ar); nh = th
            img = img.resize((nw,nh), Image.Resampling.LANCZOS)
            out = os.path.join(self.temp_dir, f"{os.path.splitext(os.path.basename(input_path))[0]}_p.jpg")
            img.save(out, "JPEG", quality=self.quality, optimize=True)
            return out
        except Exception as e:
            raise ImageProcessingError(f"前処理エラー: {e}")

    def apply_final_enhancement(self, image_path: str) -> bool:
        try:
            img = Image.open(image_path)
            img = ImageEnhance.Sharpness(img).enhance(1.1)
            img = ImageEnhance.Color(img).enhance(1.05)
            img.save(image_path, "PNG", optimize=True)
            return True
        except Exception as e:
            return False

    def encode_image_to_base64(self, image_path: str) -> str:
        try:
            import base64
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            raise ImageProcessingError(f"Base64エンコードエラー: {e}")
