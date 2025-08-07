#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ModelManager - モデル切り替え管理
- get_current_model: 現在のモデル取得
- switch_model: モデル自動切り替え
- ensure_model_for_generation_type: 生成タイプ別モデル確保
"""

import requests
import time
from common.logger import ColorLogger
from common.types import HybridGenerationError

class ModelManager:
    """モデル切り替え管理クラス"""

    def __init__(self, config: dict):
        self.config = config
        self.api_url = config['stable_diffusion']['api_url']
        self.verify_ssl = config['stable_diffusion']['verify_ssl']
        self.logger = ColorLogger()

    def get_current_model(self) -> str:
        """現在のモデル名を取得"""
        try:
            resp = requests.get(f"{self.api_url}/sdapi/v1/options",
                                timeout=30, verify=self.verify_ssl)
            resp.raise_for_status()
            data = resp.json()
            return data.get('sd_model_checkpoint', '')
        except Exception as e:
            self.logger.print_warning(f"⚠️ 現在のモデル取得エラー: {e}")
            return None

    def switch_model(self, target_model: str) -> bool:
        """モデルを指定されたモデルに切り替え"""
        current = self.get_current_model()
        if current == target_model:
            self.logger.print_status(f"🎯 モデル切り替え不要: {target_model}")
            return True

        self.logger.print_status(f"🔄 モデル切り替え開始: {current} → {target_model}")
        payload = {"sd_model_checkpoint": target_model}

        switch_cfg = self.config.get('model_switching', {})
        timeout = switch_cfg.get('switch_timeout', 120)
        wait_after = switch_cfg.get('wait_after_switch', 10)
        retries = switch_cfg.get('verification_retries', 3)

        try:
            start = time.time()
            resp = requests.post(f"{self.api_url}/sdapi/v1/options",
                                 json=payload, timeout=timeout, verify=self.verify_ssl)
            resp.raise_for_status()
            duration = time.time() - start
            self.logger.print_status(f"⏱️ 切替API呼び出し完了: {duration:.1f}秒")
            self.logger.print_status(f"⏳ 切替後待機: {wait_after}秒")
            time.sleep(wait_after)

            for i in range(retries):
                now = self.get_current_model()
                if now == target_model:
                    total = time.time() - start
                    self.logger.print_success(f"✅ モデル切り替え完了: {target_model} (総時間: {total:.1f}秒)")
                    return True
                self.logger.print_warning(f"⚠️ 切替確認失敗 ({i+1}/{retries}): 期待={target_model}, 実際={now}")
                time.sleep(5)
        except Exception as e:
            self.logger.print_error(f"❌ モデル切り替えエラー: {e}")
            return False

        self.logger.print_error(f"❌ モデル切り替え失敗: {target_model}")
        return False

    def ensure_model_for_generation_type(self, gen_type):
        """生成タイプに必要なモデルが設定されていることを確認し、切り替える"""
        if not gen_type.model_name:
            self.logger.print_error(f"❌ {gen_type.name} の model_name が未定義")
            raise HybridGenerationError(f"model_name undefined: {gen_type.name}")

        if not self.switch_model(gen_type.model_name):
            raise HybridGenerationError(f"モデル切り替え失敗: {gen_type.model_name}")
        return True
