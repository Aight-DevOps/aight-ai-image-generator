#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
HybridBijoRegisterV9 - メイン登録システム
- 初期化: 設定読み込み、AWSクライアント、統計
- process_batch: バッチディレクトリ処理
"""

import yaml
from common.logger import ColorLogger
from common.config_manager import ConfigManager
from common.aws_client import AWSClientManager

# 正しい相対インポート
from ..scanner.file_scanner import FileScanner
from ..converter.metadata_converter import MetadataConverter
from ..converter.type_converter import TypeConverter
from ..uploader.s3_uploader import S3Uploader
from ..uploader.dynamodb_uploader import DynamoDBUploader

class HybridBijoRegisterV9:
    """ローカル画像 AWS 一括登録ツール"""

    def __init__(self, config_path="config/hybrid_bijo_register_config.yaml"):  # ← ここを修正
        self.logger = ColorLogger()
        self.logger.print_stage("🚀 Hybrid Bijo Register v9 初期化中...")
        
        cfg_mgr = ConfigManager(self.logger)
        
        # 複数パス候補での設定ファイル探索
        config_candidates = [
            config_path,  # 指定されたパス
            "config/hybrid_bijo_register_config.yaml",  # config/ ディレクトリ内
            "hybrid_bijo_register_config.yaml"  # カレントディレクトリ
        ]
        
        config_loaded = False
        for candidate_path in config_candidates:
            try:
                self.config = cfg_mgr.load_register_config(candidate_path)
                config_loaded = True
                break
            except Exception as e:
                self.logger.print_warning(f"⚠️ 設定ファイル読み込み失敗: {candidate_path} - {e}")
                continue
        
        if not config_loaded:
            self.logger.print_error("❌ 設定ファイルが見つかりません。デフォルト設定を使用します")
            self.config = cfg_mgr._get_default_register_config()
        
        # AWS クライアント
        try:
            self.aws = AWSClientManager(self.logger, self.config)
            self.aws.setup_register_clients()
        except Exception as e:
            self.logger.print_error(f"❌ AWS初期化エラー: {e}")
            self.aws = None
        
        # 統計
        self.stats = {'total_found':0, 'success':0, 'skipped':0, 'errors':0, 'duplicates':0}
        
        self.logger.print_success("✅ 初期化完了")

    def process_batch(self, genre):
        """バッチ処理エントリ"""
        dirs = self.config.get('batch_directories', {})
        if genre not in dirs:
            self.logger.print_error(f"❌ ジャンル未設定: {genre}")
            return 0
        
        scanner = FileScanner(self.logger)
        pairs = scanner.scan_directory_for_pairs(dirs[genre])
        self.stats['total_found'] = len(pairs)
        if not pairs:
            self.logger.print_warning("⚠️ ペアファイルが見つかりません")
            return 0
        
        converter = MetadataConverter(self.logger)
        type_conv = TypeConverter(self.logger)
        
        if not self.aws:
            self.logger.print_error("❌ AWS接続なしでは登録できません")
            return 0
            
        s3u = S3Uploader(self.aws.s3_client, self.config['aws']['s3_bucket'], self.logger)
        dbu = DynamoDBUploader(self.aws.dynamodb_table, self.logger)
        
        for img_path, meta_path in pairs:
            meta = scanner.load_and_validate_metadata(meta_path)
            if not meta:
                self.stats['errors'] += 1
                continue
                
            aws_meta = converter.convert_metadata_for_aws(meta)
            aws_meta = type_conv.convert_for_dynamodb(aws_meta)
            
            # S3バケット名を設定に合わせて更新
            aws_meta['s3Bucket'] = self.config['aws']['s3_bucket']
            
            # 登録
            if not dbu.register_to_dynamodb(aws_meta):
                self.stats['duplicates'] += 1
                continue
                
            if not s3u.upload_to_s3(img_path, aws_meta['s3Key']):
                self.stats['errors'] += 1
                continue
                
            # 削除
            if self.config.get('processing', {}).get('cleanup_local_files_on_success', False):
                scanner.cleanup_local_files(img_path, meta_path)
                
            self.stats['success'] += 1
        
        self.print_summary()
        return self.stats['success']

    def print_summary(self):
        """統計結果サマリー表示"""
        self.logger.print_stage("=== 処理結果サマリー ===")
        self.logger.print_status(f"検出: {self.stats['total_found']} ペア")
        self.logger.print_success(f"成功: {self.stats['success']}")
        self.logger.print_warning(f"重複スキップ: {self.stats['duplicates']}")
        self.logger.print_error(f"エラー: {self.stats['errors']}")
