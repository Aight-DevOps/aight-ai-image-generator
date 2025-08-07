#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FileScanner - ディレクトリスキャン・ペア管理
- scan_directory_for_pairs
- load_and_validate_metadata
- cleanup_local_files
"""

import os
import json
from pathlib import Path
from common.logger import ColorLogger

class FileScanner:
    """ファイルスキャン管理クラス"""

    def __init__(self, logger):
        self.logger = logger

    def scan_directory_for_pairs(self, directory):
        """画像+_metadata.json ペア検出"""
        self.logger.print_status(f"📁 ディレクトリスキャン: {directory}")
        if not os.path.exists(directory):
            self.logger.print_error(f"❌ ディレクトリなし: {directory}")
            return []
        pairs = []
        for ext in self._supported_formats():
            for img in Path(directory).glob(f"*.{ext}"):
                meta = img.parent / f"{img.stem}_metadata.json"
                if meta.exists():
                    pairs.append((str(img), str(meta)))
                    self.logger.print_status(f"ペア検出: {img.name}, {meta.name}")
        self.logger.print_success(f"✅ {len(pairs)} ペア検出")
        return pairs

    def load_and_validate_metadata(self, meta_path):
        """メタデータ読み込み・必須フィールド検証"""
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for fld in ['image_id','genre','generation_mode']:
                if fld not in data:
                    self.logger.print_error(f"❌ 欠損フィールド: {fld}")
                    return None
            return data
        except Exception as e:
            self.logger.print_error(f"❌ メタデータ読み込み失敗: {e}")
            return None

    def cleanup_local_files(self, img_path, meta_path):
        """成功後ローカルファイル削除"""
        try:
            os.remove(img_path)
            os.remove(meta_path)
            self.logger.print_status(f"🗑️ ローカルファイル削除: {os.path.basename(img_path)}")
        except Exception as e:
            self.logger.print_warning(f"削除エラー: {e}")

    def _supported_formats(self):
        """対応拡張子一覧"""
        return self.logger and ['png','jpg','jpeg','bmp']
