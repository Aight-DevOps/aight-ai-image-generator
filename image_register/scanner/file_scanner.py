#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FileScanner - ファイルスキャン・ペア管理（強化版）
リファクタリング前の完全機能を再現
"""

import os
import json
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
from common.logger import ColorLogger

class FileScanner:
    """ディレクトリスキャン・ペア管理クラス（完全版）"""
    
    def __init__(self, logger: ColorLogger):
        self.logger = logger
        
    def scan_directory_for_pairs(self, directory_path: str) -> List[Tuple[str, str]]:
        """ディレクトリから画像+JSONペアをスキャン（完全版）"""
        self.logger.print_status(f"📁 ディレクトリスキャン: {directory_path}")
        
        if not os.path.exists(directory_path):
            self.logger.print_error(f"❌ ディレクトリが存在しません: {directory_path}")
            return []
        
        pairs = []
        supported_formats = ['png', 'jpg', 'jpeg']
        
        for ext in supported_formats:
            for image_path in Path(directory_path).glob(f"*.{ext}"):
                # 修正：_metadata.json形式に対応
                base_name = image_path.stem  # 拡張子なしのファイル名
                metadata_path = image_path.parent / f"{base_name}_metadata.json"
                
                if metadata_path.exists():
                    pairs.append((str(image_path), str(metadata_path)))
                    self.logger.print_status(f"🔍 ペア検出: {image_path.name} + {metadata_path.name}")
        
        self.logger.print_success(f"✅ {len(pairs)}ペアの画像+JSONファイルを検出")
        return pairs

    def load_and_validate_metadata(self, metadata_path: str) -> Optional[Dict[str, Any]]:
        """メタデータ読み込み・検証（完全版）"""
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            # 必須フィールドチェック
            required_fields = ['image_id', 'genre', 'generation_mode']
            missing_fields = []
            
            for field in required_fields:
                if field not in metadata or not metadata[field]:
                    missing_fields.append(field)
            
            if missing_fields:
                self.logger.print_warning(f"⚠️ 不足フィールド: {missing_fields}")
                
                # 自動補完を試行
                if 'generation_mode' in missing_fields:
                    inferred_mode = self._infer_generation_mode(metadata)
                    if inferred_mode:
                        metadata['generation_mode'] = inferred_mode
                        missing_fields.remove('generation_mode')
                        self.logger.print_status(f"🔧 generation_mode 自動補完: {inferred_mode}")
                
                if 'genre' in missing_fields:
                    inferred_genre = self._infer_genre_from_path(metadata_path)
                    if inferred_genre:
                        metadata['genre'] = inferred_genre
                        missing_fields.remove('genre')
                        self.logger.print_status(f"🔧 genre 自動補完: {inferred_genre}")
                
                # まだ不足がある場合はエラー
                if missing_fields:
                    self.logger.print_error(f"❌ 補完不可能な欠損フィールド: {', '.join(missing_fields)}")
                    return None
            
            return metadata
            
        except Exception as e:
            self.logger.print_error(f"❌ メタデータ読み込みエラー {metadata_path}: {e}")
            return None

    def _infer_generation_mode(self, metadata: Dict[str, Any]) -> Optional[str]:
        """メタデータから生成モードを推論"""
        # SDXL統合生成の場合
        if 'sdxl_unified_generation' in metadata:
            return 'sdxl_unified'
        
        # fast_mode が設定されている場合
        if metadata.get('fast_mode_enabled'):
            return 'fast'
        
        # bedrock が有効な場合
        if metadata.get('bedrock_enabled'):
            return 'bedrock'
        
        # ultra_safe_mode が有効な場合
        if metadata.get('ultra_memory_safe_enabled'):
            return 'ultra_safe'
        
        # ポーズモードから推論
        pose_mode = metadata.get('pose_mode')
        if pose_mode:
            return f'pose_{pose_mode}'
        
        # デフォルト
        return 'sdxl_unified'

    def _infer_genre_from_path(self, metadata_path: str) -> Optional[str]:
        """ファイルパスからジャンルを推論"""
        path_str = metadata_path.lower()
        
        # ディレクトリ名またはファイル名からジャンルを特定
        genres = ['gyal_erotic', 'gyal_black', 'gyal_natural', 'normal', 'seiso', 'teen']
        for genre in genres:
            if genre in path_str:
                return genre
        
        return None

    def cleanup_local_files(self, image_path: str, metadata_path: str):
        """ローカルファイル削除"""
        try:
            os.remove(image_path)
            os.remove(metadata_path)
            self.logger.print_status(f"🗑️ ローカルファイル削除完了: {os.path.basename(image_path)}")
        except Exception as e:
            self.logger.print_warning(f"⚠️ ローカルファイル削除エラー: {e}")
