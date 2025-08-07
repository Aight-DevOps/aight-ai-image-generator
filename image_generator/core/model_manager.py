#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ModelManager - モデル切り替え管理
- get_current_model: 現在のモデル取得
- switch_model: モデル切り替え
- ensure_model_for_generation_type: 生成タイプ別モデル確保
"""

import requests
import time
from common.logger import ColorLogger
from common.types import HybridGenerationError

class ModelManager:
    """モデル切り替え管理クラス"""

    def __init__(self, config):
        """
        Args:
            config: 設定 dict
        """
        self.config = config
        self.api_url = config['stable_diffusion']['api_url']
        self.verify_ssl = config['stable_diffusion']['verify_ssl']
        self.logger = ColorLogger()

    def get_current_model(self) -> str | None:
        """現在のモデル名取得"""
        try:
            resp = requests.get(f"{self.api_url}/sdapi/v1/options",
                                timeout=30, verify=self.verify_ssl)
            resp.raise_for_status()
            data = resp.json()
            return data.get('sd_model_checkpoint', None)
        except Exception as e:
            self.logger.print_warning(f"⚠️ モデル取得エラー: {e}")
            return None

    def switch_model(self, target_model: str) -> bool:
        """モデル切り替え"""
        current = self.get_current_model()
        if current == target_model:
            self.logger.print_status(f"モデル切り替え不要: {target_model}")
            return True

        self.logger.print_status(f"モデル切替開始: {current}→{target_model}")
        payload = {"sd_model_checkpoint": target_model}
        start = time.time()
        resp = requests.post(f"{self.api_url}/sdapi/v1/options",
                             json=payload, timeout=self.config['model_switching']['switch_timeout'],
                             verify=self.verify_ssl)
        resp.raise_for_status()
        duration = time.time() - start
        self.logger.print_status(f"切替API呼び出し: {duration:.1f}s")
        time.sleep(self.config['model_switching']['wait_after_switch'])
        # 確認
        for i in range(self.config['model_switching']['verification_retries']):
            now = self.get_current_model()
            if now == target_model:
                self.logger.print_success(f"✅ 切替完了: {target_model}")
                return True
            self.logger.print_warning(f"切替確認失敗 ({i+1})")
            time.sleep(5)
        self.logger.print_error(f"❌ 切替失敗: {target_model}")
        return False

    def ensure_model_for_generation_type(self, gen_type):
        """
        生成タイプに必要なモデル確保
        """
        if not getattr(gen_type, 'model_name', None):
            raise HybridGenerationError(f"model_name 未定義: {gen_type.name}")
        if not self.switch_model(gen_type.model_name):
            raise HybridGenerationError(f"モデル切替失敗: {gen_type.model_name}")
        return True
