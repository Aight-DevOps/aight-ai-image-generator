#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ConfigManager - 設定ファイル管理
"""

import os
import yaml
from typing import List, Dict, Any
from .logger import ColorLogger

class ConfigManager:
    """設定ファイル管理クラス"""
    
    def __init__(self, logger: ColorLogger):
        self.logger = logger
    
    def load_config(self, config_files: List[str] = None) -> Dict[str, Any]:
        """メイン設定ファイル読み込み"""
        config_files = config_files or ['config/config_v10.yaml']
        
        for config_file in config_files:
            try:
                config = self.load_yaml(config_file)
                self.logger.print_success(f"✅ {config_file}読み込み成功")
                return config
            except FileNotFoundError:
                continue
            except Exception as e:
                self.logger.print_error(f"❌ {config_file}読み込みエラー: {e}")
                continue
        
        # すべて失敗した場合はデフォルト設定を返す
        self.logger.print_warning("⚠️ 設定ファイルが見つからないため、デフォルト設定を使用します")
        return self._get_default_config()
    
    def load_register_config(self, config_path: str) -> Dict[str, Any]:
        """Register用設定読み込み（強化版）"""
        self.logger.print_status(f"📋 Register設定ファイル読み込み: {config_path}")
        
        # ファイル存在確認
        if not os.path.exists(config_path):
            self.logger.print_warning(f"⚠️ 設定ファイルが見つかりません: {config_path}")
            self.logger.print_status("📝 デフォルト設定ファイルを作成します...")
            
            # デフォルト設定ファイルを作成
            default_config = self._get_default_register_config()
            try:
                with open(config_path, 'w', encoding='utf-8') as f:
                    yaml.dump(default_config, f, default_flow_style=False, allow_unicode=True)
                self.logger.print_success(f"✅ デフォルト設定ファイルを作成: {config_path}")
            except Exception as e:
                self.logger.print_error(f"❌ 設定ファイル作成エラー: {e}")
                return default_config
        
        # 設定ファイル読み込み
        try:
            config = self.load_yaml(config_path)
            self.logger.print_success(f"✅ Register設定読み込み成功: {config_path}")
            
            # 設定の妥当性チェック
            self._validate_register_config(config)
            return config
            
        except Exception as e:
            self.logger.print_error(f"❌ Register設定読み込みエラー: {e}")
            self.logger.print_warning("⚠️ デフォルト設定を使用します")
            return self._get_default_register_config()
    
    def _validate_register_config(self, config: Dict[str, Any]):
        """Register設定の妥当性チェック"""
        required_sections = ['aws', 'batch_directories', 'processing']
        for section in required_sections:
            if section not in config:
                raise ValueError(f"必須セクション '{section}' が設定ファイルにありません")
        
        # AWS設定チェック
        aws_config = config['aws']
        required_aws_keys = ['region', 's3_bucket', 'dynamodb_table']
        for key in required_aws_keys:
            if key not in aws_config:
                raise ValueError(f"AWS設定に必須項目 '{key}' が不足しています")
        
        # バッチディレクトリチェック
        batch_dirs = config['batch_directories']
        if not batch_dirs:
            raise ValueError("batch_directories が空です")
        
        self.logger.print_success("✅ Register設定の妥当性チェック完了")
    
    def load_yaml(self, filepath: str) -> Dict[str, Any]:
        """YAML ファイル読み込み（絶対パス・相対パス対応）"""
        # 絶対パスまたは相対パスの解決
        if not os.path.isabs(filepath):
            # カレントディレクトリからの相対パスとして解決
            absolute_path = os.path.abspath(filepath)
        else:
            absolute_path = filepath
        
        # ファイル存在確認
        if not os.path.exists(absolute_path):
            # カレントディレクトリを表示してデバッグ
            current_dir = os.getcwd()
            self.logger.print_error(f"❌ YAMLファイルが見つかりません: {filepath}")
            self.logger.print_error(f"   カレントディレクトリ: {current_dir}")
            self.logger.print_error(f"   探索パス: {absolute_path}")
            
            # ファイルの存在確認とパス候補の提案
            dir_name = os.path.dirname(absolute_path)
            if os.path.exists(dir_name):
                files = os.listdir(dir_name)
                self.logger.print_error(f"   ディレクトリ内のファイル: {files}")
            
            raise FileNotFoundError(f"YAMLファイルが見つかりません: {filepath}")
        
        try:
            with open(absolute_path, 'r', encoding='utf-8') as file:
                data = yaml.safe_load(file)
                self.logger.print_success(f"✅ YAML読み込み成功: {filepath}")
                return data if data is not None else {}
        except yaml.YAMLError as e:
            self.logger.print_error(f"❌ YAML解析エラー ({filepath}): {e}")
            raise Exception(f"YAML解析エラー ({filepath}): {e}")
        except Exception as e:
            self.logger.print_error(f"❌ ファイル読み込みエラー ({filepath}): {e}")
            raise e
    
    def _get_default_config(self) -> Dict[str, Any]:
        """デフォルト設定"""
        return {
            'aws': {
                'region': 'ap-northeast-1',
                's3_bucket': 'aight-media-images',
                'dynamodb_table': 'AightMediaImageData'
            },
            'stable_diffusion': {
                'api_url': 'http://localhost:7860',
                'verify_ssl': False,
                'timeout': 3600
            },
            'input_images': {
                'source_directory': '/tmp/input_images',
                'supported_formats': ['jpg', 'jpeg', 'png'],
                'resize_quality': 95
            },
            'local_execution': {
                'enabled': True,
                'output_directory': './output_test_images',
                'save_metadata': True,
                'create_subdirs': True
            },
            'prompt_files': {
                'generation_types': 'config/generation_types.yaml',
                'prompts': 'config/prompts.yaml',
                'random_elements': 'config/random_elements.yaml'
            },
            'temp_files': {
                'directory': '/tmp/sdprocess',
                'cleanup_on_success': True
            },
            'generation': {
                'batch_size': 5,
                'genres': ['normal', 'seiso'],
                'genre_distribution': {
                    'normal': 0.5,
                    'seiso': 0.5
                }
            },
            'memory_management': {
                'enabled': True,
                'threshold_percent': 70
            }
        }
    
    def _get_default_register_config(self) -> Dict[str, Any]:
        """デフォルト登録設定（詳細版）"""
        return {
            'aws': {
                'region': 'ap-northeast-1',
                's3_bucket': 'aight-media-images',
                'dynamodb_table': 'AightMediaImageData'
            },
            'batch_directories': {
                'normal': './output_test_images/normal',
                'gyal_black': './output_test_images/gyal_black',
                'gyal_erotic': './output_test_images/gyal_erotic',
                'gyal_natural': './output_test_images/gyal_natural',
                'seiso': './output_test_images/seiso',
                'teen': './output_test_images/teen'
            },
            'processing': {
                'cleanup_local_files_on_success': False,
                'max_retries': 3,
                'retry_delay': 5
            },
            'file_scanner': {
                'supported_formats': ['png', 'jpg', 'jpeg'],
                'required_metadata_fields': ['image_id', 'genre', 'generation_mode']
            },
            'logging': {
                'level': 'INFO',
                'detailed_statistics': True
            }
        }
