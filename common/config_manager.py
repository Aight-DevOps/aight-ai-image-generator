#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ConfigManager - 設定ファイル読み込み統合管理
全ツール共通の設定ファイル管理機能
"""

import yaml
import sys
import os

class ConfigManager:
    """設定ファイル読み込み統合管理クラス"""
    
    def __init__(self, logger):
        self.logger = logger
    
    def load_config(self, config_files=None):
        """設定ファイル読み込み（互換性対応）"""
        if config_files is None:
            config_files = ['config_v10.yaml', 'config_v5.yaml', 'config.yaml']
        
        for config_file in config_files:
            try:
                with open(config_file, 'r', encoding='utf-8') as file:
                    config = yaml.safe_load(file)
                self.logger.print_success(f"✅ {config_file}読み込み成功")
                return config
            except FileNotFoundError:
                continue
            except yaml.YAMLError as e:
                self.logger.print_error(f"❌ {config_file}読み込みエラー: {e}")
                continue
        
        self.logger.print_error("❌ 設定ファイルが見つかりません（config_v10.yaml, config_v5.yaml または config.yaml）")
        sys.exit(1)
    
    def load_yaml(self, filepath):
        """YAMLファイル読み込み"""
        try:
            with open(filepath, 'r', encoding='utf-8') as file:
                return yaml.safe_load(file)
        except FileNotFoundError:
            self.logger.print_error(f"❌ YAMLファイルが見つかりません: {filepath}")
            sys.exit(1)
        except yaml.YAMLError as e:
            self.logger.print_error(f"❌ YAML読み込みエラー {filepath}: {e}")
            sys.exit(1)
    
    def load_register_config(self, config_path="hybrid_bijo_register_config.yaml"):
        """登録ツール設定ファイル読み込み"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            self.logger.print_success(f"✅ 設定ファイル読み込み完了: {config_path}")
            return config
        except FileNotFoundError:
            self.logger.print_error(f"❌ 設定ファイルが見つかりません: {config_path}")
            raise
        except yaml.YAMLError as e:
            self.logger.print_error(f"❌ 設定ファイル読み込みエラー: {e}")
            raise
