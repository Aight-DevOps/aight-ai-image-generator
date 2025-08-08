#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FileScanner - ファイルスキャン・ペア管理
"""

import os
import json
import shutil
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
from common.logger import ColorLogger

class FileScanner:
    """ディレクトリスキャン・ペア管理クラス"""
    
    def __init__(self, logger: ColorLogger):
        self.logger = logger
    
    def scan_directory_for_pairs(self, directory: str) -> List[Tuple[str, str]]:
        """ディレクトリ内の画像・メタデータペアを検出"""
        self.logger.print_status(f"📁 ディレクトリスキャン: {directory}")
        
        if not os.path.exists(directory):
            self.logger.print_error(f"❌ ディレクトリなし: {directory}")
            return []
        
        pairs = []
        for file_path in Path(directory).iterdir():
            if file_path.suffix.lower() in ['.png', '.jpg', '.jpeg']:
                # 対応するメタデータファイルを探す
                meta_candidates = [
                    file_path.with_suffix('.json'),
                    file_path.parent / f"{file_path.stem}_metadata.json"
                ]
                
                for meta_path in meta_candidates:
                    if meta_path.exists():
                        self.logger.print_status(f"ペア検出: {file_path.name}, {meta_path.name}")
                        pairs.append((str(file_path), str(meta_path)))
                        break
        
        self.logger.print_success(f"✅ {len(pairs)} ペア検出")
        return pairs
    
    def load_and_validate_metadata(self, metadata_path: str) -> Optional[Dict[str, Any]]:
        """メタデータ読み込み・バリデーション（改良版）"""
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            # 必須フィールドの確認と補完
            required_fields = {
                'image_id': metadata.get('image_id'),
                'genre': metadata.get('genre'),
                'generation_mode': metadata.get('generation_mode') or self._infer_generation_mode(metadata),
                'created_at': metadata.get('created_at'),
                'model_name': metadata.get('model_name')
            }
            
            missing_fields = []
            for field, value in required_fields.items():
                if not value:
                    missing_fields.append(field)
            
            if missing_fields:
                self.logger.print_warning(f"⚠️ 不足フィールド検出: {missing_fields}")
                
                # 補完可能なフィールドを自動補完
                if 'generation_mode' in missing_fields:
                    generation_mode = self._infer_generation_mode(metadata)
                    if generation_mode:
                        metadata['generation_mode'] = generation_mode
                        missing_fields.remove('generation_mode')
                        self.logger.print_status(f"🔧 generation_mode を自動補完: {generation_mode}")
                
                if 'genre' in missing_fields:
                    genre = self._infer_genre_from_filename(metadata_path)
                    if genre:
                        metadata['genre'] = genre
                        missing_fields.remove('genre')
                        self.logger.print_status(f"🔧 genre を自動補完: {genre}")
                
                # まだ不足しているフィールドがあればエラー
                if missing_fields:
                    self.logger.print_error(f"❌ 補完不可能な欠損フィールド: {', '.join(missing_fields)}")
                    return None
            
            return metadata
            
        except Exception as e:
            self.logger.print_error(f"❌ メタデータ読み込みエラー: {e}")
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
        return 'standard'
    
    def _infer_genre_from_filename(self, metadata_path: str) -> Optional[str]:
        """ファイル名からジャンルを推論"""
        filename = os.path.basename(metadata_path)
        
        # 一般的なジャンル名をファイル名から抽出
        genres = ['gyal_erotic', 'gyal_black', 'gyal_natural', 'normal', 'seiso', 'teen']
        for genre in genres:
            if genre in filename.lower():
                return genre
        
        return None
    
    def cleanup_local_files(self, image_path: str, metadata_path: str):
        """ローカルファイルの削除"""
        try:
            if os.path.exists(image_path):
                os.remove(image_path)
                self.logger.print_status(f"🗑️ 画像削除: {os.path.basename(image_path)}")
            
            if os.path.exists(metadata_path):
                os.remove(metadata_path)
                self.logger.print_status(f"🗑️ メタデータ削除: {os.path.basename(metadata_path)}")
                
        except Exception as e:
            self.logger.print_error(f"❌ ファイル削除エラー: {e}")
