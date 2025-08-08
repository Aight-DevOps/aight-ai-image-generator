#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ModelManager - モデル管理機能
"""

import requests
import time
from common.logger import ColorLogger
from common.types import HybridGenerationError

class ModelManager:
    """モデル管理クラス"""
    
    def __init__(self, config):
        self.config = config
        self.logger = ColorLogger()
        # Stable Diffusion API設定
        sd_config = config.get('stable_diffusion', {})
        self.api_url = sd_config.get('api_url', 'http://localhost:7860')
        self.timeout = sd_config.get('timeout', 3600)
        self.verify_ssl = sd_config.get('verify_ssl', False)
        
        # モデル切り替え設定
        switch_config = config.get('model_switching', {})
        self.switch_enabled = switch_config.get('enabled', True)
        self.switch_timeout = switch_config.get('switch_timeout', 180)
        self.wait_after_switch = switch_config.get('wait_after_switch', 10)
        self.verification_retries = switch_config.get('verification_retries', 3)
    
    def ensure_model_for_generation_type(self, gen_type):
        """生成タイプに応じたモデル確保"""
        try:
            model_name = gen_type.model_name
            self.logger.print_status(f"📋 モデル確認: {model_name}")
            
            if not self.switch_enabled:
                self.logger.print_warning("⚠️ モデル切り替えが無効化されています")
                return
            
            # 現在のモデル確認
            current_model = self.get_current_model()
            if current_model == model_name:
                self.logger.print_success(f"✅ モデル既に選択済み: {model_name}")
                return
            
            self.logger.print_status(f"🔄 モデル切り替え実行: {current_model} → {model_name}")
            
            # モデル切り替え実行
            self.switch_model(model_name)
            
            # 切り替え完了まで待機
            time.sleep(self.wait_after_switch)
            
            # 切り替え確認
            self.verify_model_switch(model_name)
            
            self.logger.print_success(f"✅ モデル準備完了: {model_name}")
            
        except Exception as e:
            self.logger.print_error(f"❌ モデル切り替えエラー: {e}")
            raise HybridGenerationError(f"モデル準備エラー: {e}")
    
    def get_current_model(self):
        """現在のモデル取得"""
        try:
            response = requests.get(
                f"{self.api_url}/sdapi/v1/options",
                timeout=30,
                verify=self.verify_ssl
            )
            response.raise_for_status()
            data = response.json()
            current_model = data.get("sd_model_checkpoint", "")
            self.logger.print_status(f"🔍 現在のモデル: {current_model}")
            return current_model
        except Exception as e:
            self.logger.print_warning(f"⚠️ 現在のモデル取得失敗: {e}")
            return ""
    
    def switch_model(self, model_name):
        """モデル切り替え実行"""
        try:
            payload = {
                "sd_model_checkpoint": model_name
            }
            
            response = requests.post(
                f"{self.api_url}/sdapi/v1/options",
                json=payload,
                timeout=self.switch_timeout,
                verify=self.verify_ssl
            )
            response.raise_for_status()
            self.logger.print_status(f"🔄 モデル切り替え要求送信完了")
            
        except requests.exceptions.Timeout:
            raise HybridGenerationError(f"モデル切り替えタイムアウト: {self.switch_timeout}秒")
        except requests.exceptions.RequestException as e:
            raise HybridGenerationError(f"モデル切り替えAPI呼び出し失敗: {e}")
    
    def verify_model_switch(self, expected_model):
        """モデル切り替え確認"""
        for attempt in range(self.verification_retries):
            try:
                current_model = self.get_current_model()
                if current_model == expected_model:
                    self.logger.print_success(f"✅ モデル切り替え確認完了: {expected_model}")
                    return True
                
                if attempt < self.verification_retries - 1:
                    self.logger.print_status(f"🔄 切り替え確認待機中... ({attempt + 1}/{self.verification_retries})")
                    time.sleep(5)
                
            except Exception as e:
                if attempt < self.verification_retries - 1:
                    self.logger.print_warning(f"⚠️ 切り替え確認失敗 ({attempt + 1}/{self.verification_retries}): {e}")
                    time.sleep(5)
                else:
                    raise HybridGenerationError(f"モデル切り替え確認失敗: {e}")
        
        # 全てのリトライが失敗した場合
        raise HybridGenerationError(f"モデル切り替え確認失敗: 期待値={expected_model}, 実際={current_model}")
    
    def list_available_models(self):
        """利用可能なモデル一覧取得"""
        try:
            response = requests.get(
                f"{self.api_url}/sdapi/v1/sd-models",
                timeout=30,
                verify=self.verify_ssl
            )
            response.raise_for_status()
            models = response.json()
            self.logger.print_status(f"📋 利用可能なモデル数: {len(models)}")
            return models
        except Exception as e:
            self.logger.print_warning(f"⚠️ モデル一覧取得失敗: {e}")
            return []
