#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
HybridBijoRegisterV9 - メイン登録システム（完全版 + BedrockManager対応版）
リファクタリング前の全機能を再現 + Bedrockコメント生成をBedrockManagerに委譲
"""

import os
import json
import yaml
import boto3
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from botocore.exceptions import ClientError
from decimal import Decimal

from common.logger import ColorLogger
from common.config_manager import ConfigManager
from common.aws_client import AWSClientManager

# 相対インポート
from ..scanner.file_scanner import FileScanner
from ..converter.metadata_converter import MetadataConverter
from ..converter.type_converter import TypeConverter
from ..uploader.s3_uploader import S3Uploader
from ..uploader.dynamodb_uploader import DynamoDBUploader
from ..processor.batch_processor import BatchProcessor

# BedrockManagerのインポート（新規追加）
try:
    from image_generator.aws.bedrock_manager import BedrockManager
    BEDROCK_MANAGER_AVAILABLE = True
except ImportError:
    BEDROCK_MANAGER_AVAILABLE = False

# JST
JST = timezone(timedelta(hours=9))

class ProcessTimer:
    """処理時間計測"""
    
    def __init__(self, logger):
        self.logger = logger
        self.start_time = None

    def start(self, process_name="処理"):
        self.start_time = time.time()
        self.process_name = process_name

    def end_and_report(self, count=None):
        if not self.start_time:
            return 0.0
        
        total_time = time.time() - self.start_time
        formatted_time = self.format_duration(total_time)
        
        if count:
            self.logger.print_status(f"⏱️ {self.process_name}完了: {formatted_time} ({count}件)")
            if count > 1:
                avg_time = total_time / count
                avg_formatted = self.format_duration(avg_time)
                self.logger.print_status(f"📊 1件あたり平均時間: {avg_formatted}")
        else:
            self.logger.print_status(f"⏱️ {self.process_name}完了: {formatted_time}")
        
        return total_time

    @staticmethod
    def format_duration(seconds):
        if seconds < 60:
            return f"{seconds:.1f}秒"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = seconds % 60
            return f"{minutes}分{secs:.1f}秒"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = seconds % 60
            return f"{hours}時間{minutes}分{secs:.1f}秒"

class HybridBijoRegisterV9:
    """ローカル画像AWS登録ツール（完全版 + BedrockManager対応版）"""

    def __init__(self, config_path="config/hybrid_bijo_register_config.yaml"):
        self.logger = ColorLogger()
        self.logger.print_stage("🚀 Hybrid Bijo Register v9 (BedrockManager対応版) 初期化中...")

        # 設定読み込み
        self.config = self.load_config(config_path)

        # AWS クライアント初期化
        self.setup_aws_clients()

        # BedrockManager初期化（新規追加）
        self.setup_bedrock_manager()

        # 統計情報
        self.stats = {
            'total_found': 0,
            'success': 0,
            'skipped': 0,
            'errors': 0,
            'duplicates': 0
        }

        self.logger.print_success("✅ 初期化完了（BedrockManager対応版）")

    def load_config(self, config_path: str):
        """設定ファイル読み込み"""
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

    def setup_aws_clients(self):
        """AWSクライアント初期化"""
        aws_config = self.config['aws']
        try:
            self.s3_client = boto3.client('s3', region_name=aws_config['region'])
            self.dynamodb = boto3.resource('dynamodb', region_name=aws_config['region'])
            self.dynamodb_table = self.dynamodb.Table(aws_config['dynamodb_table'])
            
            if self.config['bedrock']['enabled']:
                self.lambda_client = boto3.client('lambda', region_name=aws_config['region'])
                self.logger.print_status("🤖 Bedrock Lambda クライアント初期化完了")
            
            self.logger.print_success(f"✅ AWS接続完了: {aws_config['region']}")
        except Exception as e:
            self.logger.print_error(f"❌ AWS接続エラー: {e}")
            raise

    # setup_bedrock_managerメソッドの修正
    def setup_bedrock_manager(self):
        """BedrockManager初期化（修正版）"""
        if not self.config['bedrock']['enabled']:
            self.logger.print_status("📋 Bedrock機能無効のためBedrockManagerをスキップ")
            self.bedrock_manager = None
            return

        if not BEDROCK_MANAGER_AVAILABLE:
            self.logger.print_warning("⚠️ BedrockManagerが利用できません。従来方式を使用します。")
            self.bedrock_manager = None
            return

        try:
            # ConfigManagerインスタンスを作成
            from common.config_manager import ConfigManager
            config_manager = ConfigManager(self.logger)
            
            self.bedrock_manager = BedrockManager(
                lambda_client=self.lambda_client,
                logger=self.logger,
                config=self.config,
                config_manager=config_manager
            )
            self.logger.print_success("✅ BedrockManager初期化完了")
        except Exception as e:
            self.logger.print_warning(f"⚠️ BedrockManager初期化エラー、従来方式を使用: {e}")
            self.bedrock_manager = None


    def generate_bedrock_comments(self, image_metadata):
        """Bedrockコメント生成（BedrockManagerに委譲 or 従来方式）"""
        if not self.config['bedrock']['enabled']:
            self.logger.print_status("📋 Bedrock無効のためコメント生成をスキップ")
            return {}

        # BedrockManagerを使用（推奨方式）
        if self.bedrock_manager:
            try:
                self.logger.print_status("🤖 BedrockManager経由でコメント生成中...")
                
                # BedrockManager用メタデータ準備
                bedrock_metadata = {
                    'genre': image_metadata.get('genre', ''),
                    'style': 'general',
                    'imageId': image_metadata.get('imageId', ''),
                    'prompt': image_metadata.get('sdParams', {}).get('sdxl_unified', {}).get('prompt', ''),
                    'pose_mode': image_metadata.get('sdParams', {}).get('base', {}).get('pose_mode', 'detection')
                }
                
                # API制限対策
                time.sleep(1)
                
                # BedrockManagerに委譲
                comments = self.bedrock_manager.generate_all_timeslot_comments(bedrock_metadata)
                
                if comments:
                    self.logger.print_success(f"🤖 BedrockManager経由でコメント生成完了: {len(comments)}件")
                    time.sleep(2)
                    return comments
                else:
                    self.logger.print_warning("⚠️ BedrockManagerでコメント生成失敗、従来方式を試行")
                    # フォールバック: 従来方式を実行
                    return self._generate_bedrock_comments_legacy(image_metadata)
                    
            except Exception as e:
                self.logger.print_warning(f"⚠️ BedrockManagerエラー、従来方式を使用: {e}")
                # フォールバック: 従来方式を実行
                return self._generate_bedrock_comments_legacy(image_metadata)
        else:
            # 従来方式を実行
            return self._generate_bedrock_comments_legacy(image_metadata)

    def _generate_bedrock_comments_legacy(self, image_metadata):
        """従来のBedrockコメント生成方式（フォールバック用）"""
        try:
            self.logger.print_status("🤖 従来方式でBedrockコメント生成中...")
            
            # Bedrock用メタデータ準備
            bedrock_metadata = {
                'genre': image_metadata.get('genre', ''),
                'style': 'general',
                'imageId': image_metadata.get('imageId', ''),
                'prompt': image_metadata.get('sdParams', {}).get('sdxl_unified', {}).get('prompt', ''),
                'pose_mode': image_metadata.get('sdParams', {}).get('base', {}).get('pose_mode', 'detection')
            }

            # API制限対策
            time.sleep(1)

            response = self.lambda_client.invoke(
                FunctionName=self.config['bedrock']['lambda_function_name'],
                InvocationType='RequestResponse',
                Payload=json.dumps({
                    'generation_mode': 'all_timeslots',
                    'image_metadata': bedrock_metadata
                })
            )

            result = json.loads(response['Payload'].read())
            body = json.loads(result['body'])
            
            if body.get('success'):
                comments = body.get('all_comments', {})
                self.logger.print_success(f"🤖 従来方式でBedrockコメント生成完了: {len(comments)}件")
                time.sleep(2)
                return comments
            else:
                self.logger.print_warning(f"⚠️ 従来方式でBedrockコメント生成失敗: {body.get('error')}")
                return {}

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            self.logger.print_warning(f"⚠️ Bedrock APIエラー: {error_code}")
            if error_code == 'ThrottlingException':
                self.logger.print_warning("API制限のため長時間待機します...")
                time.sleep(10)
            return {}
        except Exception as e:
            self.logger.print_warning(f"⚠️ 従来方式Bedrockコメント生成エラー: {e}")
            return {}

    def process_single_pair(self, image_path: str, metadata_path: str) -> bool:
        """単一ペア処理（完全版 + BedrockManager対応）"""
        try:
            # 1. メタデータ読み込み・検証
            scanner = FileScanner(self.logger)
            local_metadata = scanner.load_and_validate_metadata(metadata_path)
            if not local_metadata:
                self.stats['errors'] += 1
                return False

            # 2. AWS用メタデータ変換
            converter = MetadataConverter(self.logger)
            type_conv = TypeConverter(self.logger)
            aws_metadata = converter.convert_metadata_for_aws(local_metadata)
            aws_metadata = type_conv.convert_for_dynamodb(aws_metadata)

            # S3バケット名を設定に合わせて更新
            aws_metadata['s3Bucket'] = self.config['aws']['s3_bucket']
            
            image_id = aws_metadata['imageId']
            s3_key = aws_metadata['s3Key']
            
            self.logger.print_status(f"🔄 処理中: {image_id}")

            # 3. DynamoDB登録（重複チェック付き）
            dbu = DynamoDBUploader(self.dynamodb_table, self.logger)
            
            # 重複チェック
            try:
                existing_item = self.dynamodb_table.get_item(Key={'imageId': image_id})
                if 'Item' in existing_item:
                    self.logger.print_warning(f"⚠️ 既存画像のため登録スキップ: {image_id}")
                    self.stats['duplicates'] += 1
                    return False
            except:
                pass

            # Bedrockコメント生成（BedrockManager対応）
            bedrock_comments = self.generate_bedrock_comments(aws_metadata)
            if bedrock_comments:
                aws_metadata['preGeneratedComments'] = bedrock_comments
                aws_metadata['commentGeneratedAt'] = datetime.now(JST).isoformat()

            if not dbu.register_to_dynamodb(aws_metadata):
                self.stats['errors'] += 1
                return False

            # 4. S3アップロード
            s3u = S3Uploader(self.s3_client, self.config['aws']['s3_bucket'], self.logger)
            if not s3u.upload_to_s3(image_path, s3_key):
                # S3失敗時はDynamoDBから削除
                try:
                    self.dynamodb_table.delete_item(Key={'imageId': image_id})
                    self.logger.print_status(f"🧹 DynamoDB削除完了: {image_id}")
                except Exception as cleanup_error:
                    self.logger.print_warning(f"⚠️ DynamoDB削除エラー: {cleanup_error}")
                self.stats['errors'] += 1
                return False

            # 5. ローカルファイル削除
            if self.config.get('processing', {}).get('cleanup_local_files_on_success', False):
                scanner.cleanup_local_files(image_path, metadata_path)

            self.stats['success'] += 1
            self.logger.print_success(f"✅ 処理完了: {image_id}")
            return True

        except Exception as e:
            self.logger.print_error(f"❌ 処理エラー: {e}")
            self.stats['errors'] += 1
            return False

    def process_batch(self, genre: str) -> int:
        """バッチ処理（完全版 + BedrockManager対応）"""
        directory_path = self.config['batch_directories'].get(genre)
        if not directory_path:
            self.logger.print_error(f"❌ ジャンル '{genre}' のディレクトリが設定されていません")
            return 0

        self.logger.print_stage(f"=== {genre} バッチ処理開始 (BedrockManager対応版) ===")

        # 統計情報リセット
        self.stats = {
            'total_found': 0,
            'success': 0,
            'skipped': 0,
            'errors': 0,
            'duplicates': 0
        }

        # ファイルペアスキャン
        scanner = FileScanner(self.logger)
        pairs = scanner.scan_directory_for_pairs(directory_path)
        
        if not pairs:
            self.logger.print_warning(f"⚠️ 処理対象ファイルがありません: {directory_path}")
            return 0

        self.stats['total_found'] = len(pairs)
        
        timer = ProcessTimer(self.logger)
        timer.start(f"{genre} バッチ処理")

        # 各ペア処理
        for i, (image_path, metadata_path) in enumerate(pairs, 1):
            self.logger.print_status(f"\n--- {i}/{len(pairs)} ---")
            
            success = self.process_single_pair(image_path, metadata_path)
            
            if not success and self.config['processing']['skip_on_individual_errors']:
                self.logger.print_status("⏭️ エラーをスキップして継続")
                continue

            # API制限対策：処理間隔
            if i < len(pairs):
                time.sleep(self.config.get('processing', {}).get('delay_between_items', 1))

        timer.end_and_report(self.stats['success'])
        self.print_final_summary()
        return self.stats['success']

    def print_final_summary(self):
        """最終サマリー表示（BedrockManager対応版）"""
        self.logger.print_stage("=== 処理結果サマリー (BedrockManager対応版) ===")
        
        self.logger.print_status(f"📊 検出ファイル: {self.stats['total_found']}ペア")
        self.logger.print_success(f"✅ 成功: {self.stats['success']}件")
        self.logger.print_warning(f"⚠️ 重複スキップ: {self.stats['duplicates']}件")
        self.logger.print_error(f"❌ エラー: {self.stats['errors']}件")
        
        if self.stats['total_found'] > 0:
            success_rate = (self.stats['success'] / self.stats['total_found']) * 100
            self.logger.print_status(f"📈 成功率: {success_rate:.1f}%")

        if self.stats['success'] > 0:
            self.logger.print_success("🎉 登録されたデータは正常なDynamoDB形式で保存されています")
            
        # BedrockManager使用状況の表示
        if self.bedrock_manager:
            self.logger.print_success("🤖 BedrockManagerを使用してコメント生成が実行されました")
        elif self.config['bedrock']['enabled']:
            self.logger.print_warning("⚠️ BedrockManagerは利用できませんでしたが、従来方式でコメント生成が実行されました")
        else:
            self.logger.print_status("📋 Bedrock機能は無効です")

    def show_menu_and_process(self):
        """メニュー表示と処理実行"""
        while True:
            print("\n" + "="*50)
            print("🎨 Hybrid Bijo Register v9 - メイン メニュー")
            print("="*50)
            print("1. normal - 通常画像バッチ処理")
            print("2. gyal - ギャル画像バッチ処理") 
            print("3. seiso - 清楚画像バッチ処理")
            print("4. teen - ティーン画像バッチ処理")
            print("5. all - 全ジャンル一括処理")
            print("0. 終了")
            print("="*50)
            
            try:
                choice = input("選択してください (0-5): ").strip()
                
                if choice == "0":
                    self.logger.print_success("👋 処理を終了します")
                    break
                elif choice == "1":
                    self.process_batch("normal")
                elif choice == "2":
                    self.process_batch("gyal")
                elif choice == "3":
                    self.process_batch("seiso")
                elif choice == "4":
                    self.process_batch("teen")
                elif choice == "5":
                    self._process_all_genres()
                else:
                    print("❌ 無効な選択です。0-5の数字を入力してください。")
                    continue
                    
            except KeyboardInterrupt:
                self.logger.print_warning("\n🛑 ユーザーによる中断")
                break
            except Exception as e:
                self.logger.print_error(f"❌ メニュー処理エラー: {e}")
                continue

    def _process_all_genres(self):
        """全ジャンル一括処理"""
        genres = ["normal", "gyal", "seiso", "teen"]
        total_success = 0
        
        self.logger.print_stage("🚀 全ジャンル一括処理開始")
        
        for genre in genres:
            try:
                success = self.process_batch(genre)
                total_success += success
                self.logger.print_status(f"📊 {genre}: {success}件成功")
            except Exception as e:
                self.logger.print_error(f"❌ {genre}処理エラー: {e}")
                continue
        
        self.logger.print_success(f"🎉 全ジャンル処理完了: 合計{total_success}件成功")
