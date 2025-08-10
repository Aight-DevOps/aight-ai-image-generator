#!/usr/bin/env python3

# -*- coding: utf-8 -*-

"""

ConfigManager - 設定ファイル管理

"""

import os
import yaml
import boto3
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, timezone, timedelta
from .logger import ColorLogger
from botocore.exceptions import ClientError, NoCredentialsError

# JST タイムゾーン定義（11スロット対応機能用）
JST = timezone(timedelta(hours=9))

class ConfigManager:
    """設定ファイル管理クラス"""

    def __init__(self, logger: ColorLogger):
        self.logger = logger
        # 11スロット対応機能用の属性（既存機能に影響しない）
        self._posting_schedule_manager = None
        self._s3_client = None

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
            self.logger.print_error(f"  カレントディレクトリ: {current_dir}")
            self.logger.print_error(f"  探索パス: {absolute_path}")

            # ファイルの存在確認とパス候補の提案
            dir_name = os.path.dirname(absolute_path)
            if os.path.exists(dir_name):
                files = os.listdir(dir_name)
                self.logger.print_error(f"  ディレクトリ内のファイル: {files}")

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

    # ===============================================
    # 新規追加: 11スロット対応機能
    # 既存機能には影響しません
    # ===============================================

    def _ensure_s3_client(self):
        """S3クライアントの初期化（遅延初期化）"""
        if self._s3_client is None:
            try:
                self._s3_client = boto3.client('s3', region_name='ap-northeast-1')
                self.logger.print_success("✅ S3クライアント初期化完了")
            except Exception as e:
                self.logger.print_error(f"❌ S3クライアント初期化エラー: {e}")
                raise

    def get_posting_schedule_manager(self, 
                                   region: str = 'ap-northeast-1',
                                   s3_bucket: str = 'aight-media-images',
                                   config_key: str = 'config/posting_schedule.yaml') -> 'PostingScheduleManager':
        """
        投稿スケジュール管理インスタンスを取得
        
        Args:
            region: AWSリージョン
            s3_bucket: S3バケット名
            config_key: 設定ファイルのS3キー
            
        Returns:
            PostingScheduleManagerインスタンス
        """
        if self._posting_schedule_manager is None:
            self._ensure_s3_client()
            self._posting_schedule_manager = PostingScheduleManager(
                s3_client=self._s3_client,
                bucket_name=s3_bucket,
                config_key=config_key,
                logger=self.logger,
                region=region
            )
            self.logger.print_success("✅ 投稿スケジュール管理機能を初期化しました")
        
        return self._posting_schedule_manager

    def get_all_time_slots(self, **kwargs) -> List[str]:
        """
        全時間帯スロット名を取得
        
        Returns:
            11個のスロット名のリスト
        """
        try:
            manager = self.get_posting_schedule_manager(**kwargs)
            return manager.get_all_slot_names()
        except Exception as e:
            self.logger.print_warning(f"⚠️ スロット取得エラー、静的リストを返します: {e}")
            return PostingScheduleManager.get_static_slot_names()

    def get_default_suitable_slots(self, **kwargs) -> List[str]:
        """
        デフォルト適合スロット取得（general以外の10個）
        
        Returns:
            デフォルト適合スロットのリスト
        """
        try:
            manager = self.get_posting_schedule_manager(**kwargs)
            return manager.get_default_suitable_slots()
        except Exception as e:
            self.logger.print_warning(f"⚠️ デフォルトスロット取得エラー、静的リストを返します: {e}")
            static_slots = PostingScheduleManager.get_static_slot_names()
            return [slot for slot in static_slots if slot != 'general']

    def validate_time_slots(self, slots: List[str], **kwargs) -> bool:
        """
        時間帯スロット名リストの妥当性チェック
        
        Args:
            slots: チェックするスロット名のリスト
            
        Returns:
            全て有効な場合True
        """
        try:
            manager = self.get_posting_schedule_manager(**kwargs)
            return manager.validate_slots(slots)
        except Exception as e:
            self.logger.print_error(f"❌ スロット検証エラー: {e}")
            return False
class PostingScheduleManager:
    """
    投稿スケジュール設定専用管理クラス（11スロット対応）
    S3からposting_schedule.yamlを読み込み、時間帯判定やハッシュタグ取得を行う
    """
    
    def __init__(self, s3_client, bucket_name: str, config_key: str, logger: ColorLogger, region: str = 'ap-northeast-1'):
        self.s3_client = s3_client
        self.bucket_name = bucket_name
        self.config_key = config_key
        self.logger = logger
        self.region = region
        self._config_cache = None
    
    def load_posting_schedule_config(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        S3から投稿スケジュール設定を読み込み
        
        Args:
            force_refresh: キャッシュを無視して強制再読み込み
            
        Returns:
            投稿スケジュール設定辞書
        """
        if self._config_cache is not None and not force_refresh:
            return self._config_cache
            
        try:
            self.logger.print_status(f"📋 S3から投稿スケジュール設定を読み込み中: s3://{self.bucket_name}/{self.config_key}")
            
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=self.config_key
            )
            
            config_content = response['Body'].read().decode('utf-8')
            config = yaml.safe_load(config_content)
            
            # 基本検証
            self._validate_posting_schedule_config(config)
            
            self._config_cache = config
            self.logger.print_success("✅ S3からの投稿スケジュール設定読み込み完了")
            
            return config
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                self.logger.print_warning(f"⚠️ 投稿スケジュール設定ファイルが見つかりません: s3://{self.bucket_name}/{self.config_key}")
            elif error_code == 'NoSuchBucket':
                self.logger.print_warning(f"⚠️ S3バケットが見つかりません: {self.bucket_name}")
            else:
                self.logger.print_warning(f"⚠️ S3アクセスエラー: {e}")
            
            self.logger.print_status("📝 フォールバック設定を使用します")
            return self._get_fallback_posting_schedule_config()
            
        except yaml.YAMLError as e:
            self.logger.print_error(f"❌ YAML解析エラー: {e}")
            return self._get_fallback_posting_schedule_config()
            
        except Exception as e:
            self.logger.print_error(f"❌ 投稿スケジュール設定読み込みエラー: {e}")
            return self._get_fallback_posting_schedule_config()
    
    def _validate_posting_schedule_config(self, config: Dict[str, Any]):
        """投稿スケジュール設定の基本検証"""
        if 'posting_schedule' not in config:
            raise ValueError("posting_schedule キーが見つかりません")
            
        if 'slots' not in config['posting_schedule']:
            raise ValueError("slots キーが見つかりません")
            
        slots = config['posting_schedule']['slots']
        required_slots = self.get_static_slot_names()
        
        missing_slots = []
        for slot_name in required_slots:
            if slot_name not in slots:
                missing_slots.append(slot_name)
        
        if missing_slots:
            self.logger.print_warning(f"⚠️ 以下のスロットが設定ファイルに見つかりません: {missing_slots}")
    
    def _get_fallback_posting_schedule_config(self) -> Dict[str, Any]:
        """フォールバック投稿スケジュール設定（11スロット対応）"""
        self.logger.print_warning("⚠️ S3からの設定読み込みに失敗したため、11スロット対応フォールバック設定を使用します")
        return {
            "posting_schedule": {
                "slots": {
                    "early_morning": {
                        "start": "05:00",
                        "end": "07:59",
                        "hashtags": ["#おはよう", "#朝の癒し"],
                        "weekdays": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
                    },
                    "morning": {
                        "start": "08:00", 
                        "end": "09:59",
                        "hashtags": ["#朝活", "#モーニング"],
                        "weekdays": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
                    },
                    "late_morning": {
                        "start": "10:00",
                        "end": "11:59", 
                        "hashtags": ["#ブレイクタイム", "#10時休憩"],
                        "weekdays": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
                    },
                    "lunch": {
                        "start": "12:00",
                        "end": "13:59",
                        "hashtags": ["#ランチタイム", "#ランチ女子"],
                        "weekdays": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
                    },
                    "afternoon": {
                        "start": "14:00",
                        "end": "15:59",
                        "hashtags": ["#午後のひととき", "#ティータイム"],
                        "weekdays": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
                    },
                    "pre_evening": {
                        "start": "16:00",
                        "end": "17:59",
                        "hashtags": ["#夕方コーデ", "#もうすぐ夜"],
                        "weekdays": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
                    },
                    "evening": {
                        "start": "18:00",
                        "end": "19:59",
                        "hashtags": ["#ディナー女子", "#夜ごはん"],
                        "weekdays": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
                    },
                    "night": {
                        "start": "20:00",
                        "end": "21:59",
                        "hashtags": ["#夜景女子", "#ナイトライフ"],
                        "weekdays": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
                    },
                    "late_night": {
                        "start": "22:00",
                        "end": "23:59",
                        "hashtags": ["#深夜スイーツ", "#夜カフェ"],
                        "weekdays": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
                    },
                    "mid_night": {
                        "start": "00:00",
                        "end": "04:59",
                        "hashtags": ["#おやすみ前", "#深夜の癒し"],
                        "weekdays": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
                    },
                    "general": {
                        "hashtags": ["#美少女", "#今日の一枚"],
                        "weekdays": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
                    }
                }
            },
            "slot_metadata": {
                "total_slots": 11,
                "fallback_slot": "general",
                "version": "v1.2_fallback",
                "source": "embedded_fallback"
            }
        }
    
    def get_all_slot_names(self) -> List[str]:
        """
        全スロット名を取得（S3設定から動的取得）
        
        Returns:
            スロット名のリスト
        """
        try:
            config = self.load_posting_schedule_config()
            slots = config['posting_schedule']['slots']
            return list(slots.keys())
        except Exception as e:
            self.logger.print_warning(f"⚠️ スロット名取得エラー、静的リストを返します: {e}")
            return self.get_static_slot_names()
    
    @staticmethod
    def get_static_slot_names() -> List[str]:
        """
        全スロット名を取得（静的定義・フォールバック用）
        
        Returns:
            11個のスロット名のリスト
        """
        return [
            'early_morning', 'morning', 'late_morning', 'lunch', 
            'afternoon', 'pre_evening', 'evening', 'night', 
            'late_night', 'mid_night', 'general'
        ]
    
    def get_default_suitable_slots(self) -> List[str]:
        """
        デフォルト適合スロット取得（general以外の10個）
        
        Returns:
            デフォルト適合スロットのリスト
        """
        all_slots = self.get_all_slot_names()
        return [slot for slot in all_slots if slot != 'general']
    
    def get_slot_config(self, slot_name: str) -> Optional[Dict[str, Any]]:
        """
        特定スロットの設定を取得
        
        Args:
            slot_name: スロット名
            
        Returns:
            スロット設定辞書（見つからない場合はNone）
        """
        try:
            config = self.load_posting_schedule_config()
            slots = config['posting_schedule']['slots']
            return slots.get(slot_name)
        except Exception as e:
            self.logger.print_error(f"❌ スロット設定取得エラー: {e}")
            return None
    
    def get_slot_hashtags(self, slot_name: str) -> List[str]:
        """
        特定スロットのハッシュタグを取得
        
        Args:
            slot_name: スロット名
            
        Returns:
            ハッシュタグのリスト
        """
        slot_config = self.get_slot_config(slot_name)
        if slot_config and 'hashtags' in slot_config:
            return slot_config['hashtags']
        else:
            self.logger.print_warning(f"⚠️ スロット '{slot_name}' のハッシュタグが見つかりません")
            return ["#美少女", "#今日の一枚"]  # フォールバック
    
    def get_current_time_slot_and_hashtags(self, current_time: datetime) -> tuple[str, List[str]]:
        """
        現在時刻に基づいて時間帯スロットとハッシュタグを取得
        
        Args:
            current_time: 現在時刻（JST想定）
            
        Returns:
            (スロット名, ハッシュタグリスト) のタプル
        """
        try:
            config = self.load_posting_schedule_config()
            slots = config["posting_schedule"]["slots"]
            
            # JSTに変換
            now = current_time.astimezone(JST)
            now_time = now.time()
            weekday = now.strftime("%a").lower()
            
            # スロットを順番にチェック
            for slot_name, slot_cfg in slots.items():
                # 曜日チェック
                if "weekdays" in slot_cfg and weekday not in slot_cfg["weekdays"]:
                    continue
                
                # 時間範囲チェック（start/endがないスロットはスキップ）
                if "start" not in slot_cfg or "end" not in slot_cfg:
                    continue
                
                try:
                    # 時刻文字列をtimeオブジェクトに変換
                    start_h, start_m = map(int, slot_cfg["start"].split(":"))
                    end_h, end_m = map(int, slot_cfg["end"].split(":"))
                    
                    # JSTとして解釈
                    start_time = datetime(now.year, now.month, now.day, start_h, start_m, tzinfo=JST).time()
                    end_time = datetime(now.year, now.month, now.day, end_h, end_m, tzinfo=JST).time()
                    
                    # 範囲内判定（start <= now < end）
                    if start_time <= now_time < end_time:
                        hashtags = slot_cfg.get("hashtags", [])[:2]  # 最初の2個のみ使用
                        self.logger.print_success(f"✅ 現在時刻 {now_time} は '{slot_name}' スロットに一致")
                        return slot_name, hashtags
                        
                except (ValueError, TypeError) as e:
                    self.logger.print_warning(f"⚠️ スロット '{slot_name}' の時刻形式エラー: {e}")
                    continue
            
            # 一致するスロットがない場合はgeneral
            general_hashtags = slots.get("general", {}).get("hashtags", ["#美少女", "#今日の一枚"])
            self.logger.print_warning(f"⚠️ 現在時刻 {now_time} に一致するスロットがありません。generalを使用します")
            return "general", general_hashtags[:2]
            
        except Exception as e:
            self.logger.print_error(f"❌ 時間帯スロット判定エラー: {e}")
            return "general", ["#美少女", "#今日の一枚"]
    
    def validate_slots(self, slots: List[str]) -> bool:
        """
        スロット名リストの妥当性をチェック
        
        Args:
            slots: チェックするスロット名のリスト
            
        Returns:
            全て有効な場合True
        """
        try:
            valid_slots = self.get_all_slot_names()
            return all(slot in valid_slots for slot in slots)
        except Exception as e:
            self.logger.print_error(f"❌ スロット妥当性チェックエラー: {e}")
            return False
    
    def get_config_version(self) -> str:
        """
        設定ファイルのバージョンを取得
        
        Returns:
            バージョン文字列
        """
        try:
            config = self.load_posting_schedule_config()
            metadata = config.get('slot_metadata', {})
            return metadata.get('version', 'unknown')
        except Exception as e:
            self.logger.print_warning(f"⚠️ バージョン取得エラー: {e}")
            return 'unknown'
    
    def get_total_slots(self) -> int:
        """
        総スロット数を取得
        
        Returns:
            スロット数
        """
        return len(self.get_all_slot_names())
    
    def clear_cache(self) -> None:
        """設定キャッシュをクリア"""
        self._config_cache = None
        self.logger.print_success("✅ 投稿スケジュール設定キャッシュをクリアしました")


# 便利な関数群（既存システムとの互換性保持・新規追加）

def get_posting_schedule_manager_standalone(
    logger: ColorLogger,
    region: str = 'ap-northeast-1',
    s3_bucket: str = 'aight-media-images',
    config_key: str = 'config/posting_schedule.yaml'
) -> PostingScheduleManager:
    """
    スタンドアロンで投稿スケジュール管理インスタンスを取得
    
    Args:
        logger: ロガーインスタンス
        region: AWSリージョン
        s3_bucket: S3バケット名
        config_key: 設定ファイルのS3キー
        
    Returns:
        PostingScheduleManagerインスタンス
    """
    try:
        s3_client = boto3.client('s3', region_name=region)
        return PostingScheduleManager(
            s3_client=s3_client,
            bucket_name=s3_bucket,
            config_key=config_key,
            logger=logger,
            region=region
        )
    except Exception as e:
        logger.print_error(f"❌ スタンドアロン投稿スケジュール管理インスタンス作成エラー: {e}")
        raise

def get_all_time_slots_static() -> List[str]:
    """
    全時間帯スロット名を取得（静的・便利関数）
    
    Returns:
        11個のスロット名のリスト
    """
    return PostingScheduleManager.get_static_slot_names()

def get_default_suitable_slots_static() -> List[str]:
    """
    デフォルト適合スロットを取得（静的・便利関数）
    
    Returns:
        デフォルト適合スロットのリスト（general以外の10個）
    """
    static_slots = PostingScheduleManager.get_static_slot_names()
    return [slot for slot in static_slots if slot != 'general']


# 既存システム統合のためのユーティリティ関数（互換性保持）

def printf(message: str, *args) -> None:
    """
    既存コードでよく使われているprintf関数の互換実装
    
    Args:
        message: 出力メッセージ
        *args: フォーマット引数
    """
    if args:
        print(message % args)
    else:
        print(message)

def get_jst_now() -> datetime:
    """
    JST現在時刻取得（既存パターンに合わせる）
    
    Returns:
        JST現在時刻
    """
    return datetime.now(JST)


# 例外クラス（11スロット対応機能用）

class PostingScheduleConfigError(Exception):
    """投稿スケジュール設定エラー"""
    pass


# モジュールレベルでの使用例・テスト用コード
if __name__ == "__main__":
    # テスト用コード（既存パターンに合わせる）
    import logging
    logging.basicConfig(level=logging.INFO)
    
    # 簡易ロガーの作成（テスト用）
    class TestLogger:
        def print_success(self, msg): print(f"✅ {msg}")
        def print_error(self, msg): print(f"❌ {msg}")
        def print_warning(self, msg): print(f"⚠️ {msg}")
        def print_status(self, msg): print(f"📋 {msg}")
    
    try:
        test_logger = TestLogger()
        config_manager = ConfigManager(test_logger)
        
        printf("=== 投稿スケジュール設定テスト（既存システム統合版） ===")
        
        # 既存機能のテスト
        printf("既存機能テスト:")
        default_config = config_manager._get_default_config()
        printf("デフォルト設定読み込み: %s", "成功" if default_config else "失敗")
        
        # 新機能のテスト（11スロット対応）
        printf("\n新機能テスト（11スロット対応）:")
        
        # 静的スロット取得
        all_slots = get_all_time_slots_static()
        printf("総スロット数: %d", len(all_slots))
        
        printf("\n全スロット名:")
        for i, slot in enumerate(all_slots, 1):
            printf("%2d. %s", i, slot)
        
        printf("\nデフォルト適合スロット（general以外）:")
        default_slots = get_default_suitable_slots_static()
        for i, slot in enumerate(default_slots, 1):
            printf("%2d. %s", i, slot)
        
        printf("\n現在時刻（JST）: %s", get_jst_now().strftime("%Y-%m-%d %H:%M:%S %Z"))
        
        printf("\nテスト完了！既存機能と新機能が共存しています。")
        
    except Exception as e:
        printf("テストエラー: %s", e)
