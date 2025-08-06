#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stable Diffusion Image Registrar - SD画像登録管理クラス
"""

import os
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from decimal import Decimal

from ..core.config_manager import ConfigManager
from ..core.aws_manager import AWSManager
from ..core.exceptions import HybridGenerationError
from ..utils.logger import ColorLogger
from ..utils.timer import ProcessTimer

# JST タイムゾーン
JST = timezone(timedelta(hours=9))

class SDImageRegistrar:
    """Stable Diffusion画像登録管理クラス（DynamoDB Float型エラー修正版）"""

    def __init__(self, config_manager: ConfigManager):
        """
        SD画像登録クラス初期化
        
        Args:
            config_manager: 設定管理クラスインスタンス
        """
        self.config_manager = config_manager
        self.logger = ColorLogger()
        self.aws_manager = AWSManager(config_manager)
        
        # 登録専用設定の読み込み
        self.register_config = self._load_register_config()
        
        # 統計情報
        self.stats = {
            'total_found': 0,
            'success': 0,
            'skipped': 0,
            'errors': 0,
            'duplicates': 0
        }
        
        self.logger.print_stage("🚀 SD画像登録ツール初期化完了（DynamoDB Float型エラー修正版）")

    def _load_register_config(self) -> Dict[str, Any]:
        """登録専用設定読み込み"""
        try:
            register_config_file = "hybrid_bijo_register_config.yaml"
            return self.config_manager.load_config("hybrid_bijo_register_config")
        except Exception:
            # フォールバック：メイン設定から取得
            self.logger.print_warning("⚠️ 登録専用設定が見つかりません。メイン設定を使用します")
            return {
                'batch_directories': {
                    'normal': './output/test_images/normal',
                    'seiso': './output/test_images/seiso',
                    'teen': './output/test_images/teen',
                    'gyal_black': './output/test_images/gyal_black',
                    'gyal_natural': './output/test_images/gyal_natural',
                    'gyal_erotic': './output/test_images/gyal_erotic'
                },
                'processing': {
                    'cleanup_local_files_on_success': True,
                    'skip_on_individual_errors': True,
                    'abort_on_aws_connection_errors': True,
                    'supported_image_formats': ["png", "jpg", "jpeg"]
                },
                'default_suitable_slots': ["early_morning", "morning", "lunch", "evening", "night", "mid_night", "general"]
            }

    def scan_directory_for_pairs(self, directory_path: str) -> List[Tuple[str, str]]:
        """
        ディレクトリから画像+JSONペアをスキャン
        
        Args:
            directory_path: スキャン対象ディレクトリ
            
        Returns:
            List[Tuple[str, str]]: (画像パス, メタデータパス)のペアリスト
        """
        self.logger.print_status(f"📁 ディレクトリスキャン: {directory_path}")
        
        if not os.path.exists(directory_path):
            self.logger.print_error(f"❌ ディレクトリが存在しません: {directory_path}")
            return []

        pairs = []
        supported_formats = self.register_config['processing']['supported_image_formats']
        
        for ext in supported_formats:
            for image_path in Path(directory_path).glob(f"*.{ext}"):
                # _metadata.json形式に対応
                base_name = image_path.stem  # 拡張子なしのファイル名
                metadata_path = image_path.parent / f"{base_name}_metadata.json"
                
                if metadata_path.exists():
                    pairs.append((str(image_path), str(metadata_path)))
                    self.logger.print_status(f"🔍 ペア検出: {image_path.name} + {metadata_path.name}")

        self.logger.print_success(f"✅ {len(pairs)}ペアの画像+JSONファイルを検出")
        return pairs

    def load_and_validate_metadata(self, metadata_path: str) -> Optional[Dict[str, Any]]:
        """
        メタデータ読み込み・検証
        
        Args:
            metadata_path: メタデータファイルパス
            
        Returns:
            Optional[Dict[str, Any]]: 検証済みメタデータ（エラー時はNone）
        """
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)

            # 必須フィールドチェック
            required_fields = ['image_id', 'genre', 'generation_mode']
            for field in required_fields:
                if field not in metadata:
                    self.logger.print_error(f"❌ 必須フィールド不足: {field} in {metadata_path}")
                    return None

            return metadata

        except Exception as e:
            self.logger.print_error(f"❌ メタデータ読み込みエラー {metadata_path}: {e}")
            return None

    def safe_convert_numeric(self, value):
        """数値を安全にDynamoDB対応型に変換"""
        if isinstance(value, float):
            return Decimal(str(value))
        elif isinstance(value, dict):
            return {k: self.safe_convert_numeric(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self.safe_convert_numeric(item) for item in value]
        return value

    def safe_convert_for_json(self, value):
        """JSON送信用に安全に変換"""
        if isinstance(value, Decimal):
            return float(value)  # JSONではfloatで送信
        elif isinstance(value, dict):
            return {k: self.safe_convert_for_json(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self.safe_convert_for_json(item) for item in value]
        return value

    def convert_metadata_for_aws(self, local_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        ローカルメタデータをAWS用に変換（Decimal型対応版）
        
        Args:
            local_metadata: ローカルメタデータ
            
        Returns:
            Dict[str, Any]: AWS用メタデータ
        """
        # image_idを変換（local_sdxl_* → sdxl_*）
        original_id = local_metadata['image_id']
        if original_id.startswith('local_sdxl_'):
            new_id = original_id.replace('local_sdxl_', 'sdxl_', 1)
        else:
            new_id = original_id

        # 基本情報取得
        genre = local_metadata['genre']
        created_at_iso = local_metadata.get('created_at', datetime.now().isoformat())

        # created_atから日時文字列生成
        try:
            dt = datetime.fromisoformat(created_at_iso.replace('Z', '+00:00'))
            created_at_string = dt.strftime("%Y%m%d%H%M%S")
        except:
            created_at_string = datetime.now().strftime("%Y%m%d%H%M%S")

        # S3キー生成
        s3_key = f"image-pool/{genre}/{new_id}.png"

        # 適合時間帯スロット
        suitable_slots = self.register_config['default_suitable_slots']

        # DynamoDBアイテム構築（Decimal型対応版）
        aws_metadata = {
            "imageId": new_id,
            "s3Bucket": self.aws_manager.get_s3_bucket(),
            "s3Key": s3_key,
            "genre": genre,
            "imageState": "unprocessed",
            "postingStage": "notposted",
            "createdAt": created_at_string,
            "suitableTimeSlots": suitable_slots,
            "preGeneratedComments": {},
            "commentGeneratedAt": "",
            "recommendedTimeSlot": "general",
            "sdParams": self.safe_convert_numeric(self.extract_sd_params(local_metadata)),
            # X投稿管理用フィールド
            "scheduledPostTime": "",
            "actualPostTime": created_at_string,
            "tweetId": "",
            "postingAttempts": 0,
            "lastErrorMessage": "",
            "movedToArchive": False,
        }

        return aws_metadata

    def extract_sd_params(self, local_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        SDパラメータ抽出（Decimal型対応版）
        
        Args:
            local_metadata: ローカルメタデータ
            
        Returns:
            Dict[str, Any]: SDパラメータ
        """
        def convert_to_decimal(value):
            """float値をDecimalに安全に変換"""
            if isinstance(value, float):
                return Decimal(str(value))
            elif isinstance(value, (int, str)):
                try:
                    return Decimal(str(value))
                except:
                    return value
            return value

        sd_params = {}

        # ベースパラメータ
        if 'genre' in local_metadata:
            sd_params['base'] = {
                'generation_method': local_metadata.get('generation_mode', ''),
                'input_image': local_metadata.get('input_image', ''),
                'pose_mode': local_metadata.get('pose_mode', 'detection'),
                'fast_mode_enabled': str(local_metadata.get('fast_mode_enabled', False)),
                'secure_random_enabled': 'true',
                'ultra_memory_safe_enabled': str(local_metadata.get('ultra_memory_safe_enabled', False)),
                'bedrock_enabled': str(local_metadata.get('bedrock_enabled', False))
            }

        # SDXL統合生成パラメータ（Decimal型対応）
        if 'sdxl_unified_generation' in local_metadata:
            sdxl_gen = local_metadata['sdxl_unified_generation']
            sd_params['sdxl_unified'] = {
                'prompt': sdxl_gen.get('prompt', ''),
                'negative_prompt': sdxl_gen.get('negative_prompt', ''),
                'steps': int(sdxl_gen.get('steps', 30)),
                'cfg_scale': convert_to_decimal(sdxl_gen.get('cfg_scale', 7.0)),
                'width': int(sdxl_gen.get('width', 896)),
                'height': int(sdxl_gen.get('height', 1152)),
                'model': sdxl_gen.get('model', ''),
                'sampler': sdxl_gen.get('sampler', 'DPM++ 2M Karras')
            }

        # ControlNetパラメータ（Decimal型対応）
        if 'controlnet' in local_metadata:
            cn = local_metadata['controlnet']
            sd_params['controlnet'] = {
                'enabled': cn.get('enabled', False),
                'openpose': {
                    'enabled': cn.get('openpose', {}).get('enabled', False),
                    'weight': convert_to_decimal(cn.get('openpose', {}).get('weight', 0.8))
                },
                'depth': {
                    'enabled': cn.get('depth', {}).get('enabled', False),
                    'weight': convert_to_decimal(cn.get('depth', {}).get('weight', 0.3))
                }
            }

        # ADetailerパラメータ
        if 'adetailer' in local_metadata:
            ad = local_metadata['adetailer']
            sd_params['adetailer'] = {
                'enabled': ad.get('enabled', True)
            }

        return sd_params

    def generate_bedrock_comments(self, image_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Bedrockコメント生成（Decimal型対応版）
        
        Args:
            image_metadata: 画像メタデータ
            
        Returns:
            Dict[str, Any]: 生成されたコメント
        """
        if not self.config_manager.is_bedrock_enabled():
            self.logger.print_status("Bedrock無効のためコメント生成をスキップ")
            return {}

        try:
            self.logger.print_status("🤖 Bedrockコメント生成中...")
            
            # Bedrock用メタデータ準備（JSON送信用にfloat変換）
            bedrock_metadata = self.safe_convert_for_json({
                'genre': image_metadata.get('genre', ''),
                'style': 'general',
                'imageId': image_metadata.get('imageId', ''),
                'prompt': image_metadata.get('sdParams', {}).get('sdxl_unified', {}).get('prompt', ''),
                'pose_mode': image_metadata.get('sdParams', {}).get('base', {}).get('pose_mode', 'detection')
            })

            # Bedrockコメント生成を実行
            comments = self.aws_manager.generate_bedrock_comments(bedrock_metadata)
            
            if comments:
                self.logger.print_success(f"🤖 Bedrockコメント生成完了: {len(comments)}件")
                return comments
            else:
                self.logger.print_warning("⚠️ Bedrockコメント生成に失敗しました")
                return {}

        except Exception as e:
            self.logger.print_warning(f"⚠️ Bedrockコメント生成エラー: {e}")
            return {}

    def register_to_dynamodb(self, aws_metadata: Dict[str, Any]) -> bool:
        """
        DynamoDB登録（Decimal型対応版）
        
        Args:
            aws_metadata: AWS用メタデータ
            
        Returns:
            bool: 成功時True
        """
        image_id = aws_metadata['imageId']
        
        try:
            self.logger.print_status(f"📝 DynamoDB登録中: {image_id}")

            # 重複チェック
            existing_item = self.aws_manager.get_from_dynamodb(image_id)
            if existing_item:
                self.logger.print_warning(f"⚠️ 既存画像のため登録スキップ: {image_id}")
                self.stats['duplicates'] += 1
                return False

            # Bedrockコメント生成
            bedrock_comments = self.generate_bedrock_comments(aws_metadata)
            if bedrock_comments:
                aws_metadata['preGeneratedComments'] = bedrock_comments
                aws_metadata['commentGeneratedAt'] = datetime.now(JST).isoformat()

            # DynamoDB登録
            success = self.aws_manager.save_to_dynamodb(aws_metadata)
            
            if success:
                self.logger.print_success(f"✅ DynamoDB登録完了: {image_id}")
                return True
            else:
                self.logger.print_error(f"❌ DynamoDB登録失敗: {image_id}")
                return False

        except Exception as e:
            self.logger.print_error(f"❌ DynamoDB登録エラー ({image_id}): {e}")
            return False

    def upload_to_s3(self, image_path: str, s3_key: str) -> bool:
        """
        S3アップロード
        
        Args:
            image_path: ローカル画像パス
            s3_key: S3キー
            
        Returns:
            bool: 成功時True
        """
        return self.aws_manager.upload_to_s3(image_path, s3_key)

    def cleanup_local_files(self, image_path: str, metadata_path: str):
        """
        ローカルファイル削除
        
        Args:
            image_path: 画像ファイルパス
            metadata_path: メタデータファイルパス
        """
        if not self.register_config['processing']['cleanup_local_files_on_success']:
            return

        try:
            os.remove(image_path)
            os.remove(metadata_path)
            self.logger.print_status(f"🗑️ ローカルファイル削除完了: {os.path.basename(image_path)}")
        except Exception as e:
            self.logger.print_warning(f"⚠️ ローカルファイル削除エラー: {e}")

    def process_single_pair(self, image_path: str, metadata_path: str) -> bool:
        """
        単一ペア処理（Decimal型対応版）
        
        Args:
            image_path: 画像ファイルパス
            metadata_path: メタデータファイルパス
            
        Returns:
            bool: 成功時True
        """
        try:
            # 1. メタデータ読み込み・検証
            local_metadata = self.load_and_validate_metadata(metadata_path)
            if not local_metadata:
                self.stats['errors'] += 1
                return False

            # 2. AWS用メタデータ変換（Decimal型対応版）
            aws_metadata = self.convert_metadata_for_aws(local_metadata)
            image_id = aws_metadata['imageId']
            s3_key = aws_metadata['s3Key']

            self.logger.print_status(f"🔄 処理中: {image_id}")

            # 3. DynamoDB登録
            if not self.register_to_dynamodb(aws_metadata):
                # 重複の場合はS3アップロードもスキップ
                if self.stats['duplicates'] > 0:
                    return False
                self.stats['errors'] += 1
                return False

            # 4. S3アップロード
            if not self.upload_to_s3(image_path, s3_key):
                # S3失敗時はDynamoDBから削除（クリーンアップ）
                try:
                    self.aws_manager.update_dynamodb_item(
                        image_id,
                        "REMOVE imageId",
                        {}
                    )
                    self.logger.print_status(f"🧹 DynamoDB削除完了: {image_id}")
                except Exception as cleanup_error:
                    self.logger.print_warning(f"⚠️ DynamoDB削除エラー: {cleanup_error}")
                
                self.stats['errors'] += 1
                return False

            # 5. ローカルファイル削除
            self.cleanup_local_files(image_path, metadata_path)

            self.stats['success'] += 1
            self.logger.print_success(f"✅ 処理完了: {image_id}")
            return True

        except Exception as e:
            self.logger.print_error(f"❌ 処理エラー: {e}")
            self.stats['errors'] += 1
            return False

    def process_batch(self, genre: str) -> int:
        """
        バッチ処理
        
        Args:
            genre: 処理対象ジャンル
            
        Returns:
            int: 成功数
        """
        directory_path = self.register_config['batch_directories'].get(genre)
        if not directory_path:
            self.logger.print_error(f"❌ ジャンル '{genre}' のディレクトリが設定されていません")
            return 0

        self.logger.print_stage(f"=== {genre} バッチ処理開始 (DynamoDB Float型エラー修正版) ===")

        # 統計情報リセット
        self.stats = {
            'total_found': 0,
            'success': 0,
            'skipped': 0,
            'errors': 0,
            'duplicates': 0
        }

        # ファイルペアスキャン
        pairs = self.scan_directory_for_pairs(directory_path)
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
            
            if not success and self.register_config['processing']['skip_on_individual_errors']:
                self.logger.print_status("⏭️ エラーをスキップして継続")
                continue

            # API制限対策：処理間隔
            if i < len(pairs):
                delay = self.register_config.get('processing', {}).get('delay_between_items', 1)
                time.sleep(delay)

        timer.end_and_report(self.stats['success'])
        self.print_final_summary()

        return self.stats['success']

    def print_final_summary(self):
        """最終サマリー表示"""
        self.logger.print_stage("=== 処理結果サマリー (DynamoDB Float型エラー修正版) ===")
        self.logger.print_status(f"📊 検出ファイル: {self.stats['total_found']}ペア")
        self.logger.print_success(f"✅ 成功: {self.stats['success']}件")
        self.logger.print_warning(f"⚠️ 重複スキップ: {self.stats['duplicates']}件")
        self.logger.print_error(f"❌ エラー: {self.stats['errors']}件")

        if self.stats['total_found'] > 0:
            success_rate = (self.stats['success'] / self.stats['total_found']) * 100
            self.logger.print_status(f"📈 成功率: {success_rate:.1f}%")

        if self.stats['success'] > 0:
            self.logger.print_success("🎉 登録されたデータは正常なDynamoDB形式で保存されています")

    def show_menu_and_process(self):
        """メニュー表示・処理実行"""
        self.logger.print_stage("🚀 SD画像登録ツール (DynamoDB Float型エラー修正版)")

        available_genres = list(self.register_config['batch_directories'].keys())

        while True:
            print("\n" + "="*60)
            print("📋 ジャンル選択メニュー (DynamoDB Float型エラー修正版)")
            print("="*60)
            
            for i, genre in enumerate(available_genres, 1):
                print(f"{i}. {genre}")
            print(f"{len(available_genres) + 1}. 終了")
            print("="*60)
            print("🔧 修正内容: Float型をDecimal型に自動変換")
            print("✅ DynamoDB互換性完全対応")
            print("="*60)

            try:
                choice = input("選択 (1-{}): ".format(len(available_genres) + 1)).strip()
                choice_num = int(choice)

                if 1 <= choice_num <= len(available_genres):
                    selected_genre = available_genres[choice_num - 1]
                    self.process_batch(selected_genre)
                elif choice_num == len(available_genres) + 1:
                    break
                else:
                    print("❌ 無効な選択です")

            except ValueError:
                print("❌ 数値を入力してください")
            except KeyboardInterrupt:
                print("\n🛑 処理が中断されました")
                break
