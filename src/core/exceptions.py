#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Core Exceptions - 共通例外定義
"""

class HybridGenerationError(Exception):
    """ハイブリッド生成専用エラー"""
    pass

class ConfigurationError(Exception):
    """設定エラー"""
    pass

class AWSConnectionError(Exception):
    """AWS接続エラー"""
    pass

class ModelSwitchError(Exception):
    """モデル切り替えエラー"""
    pass

class MemoryManagementError(Exception):
    """メモリ管理エラー"""
    pass

class ImageProcessingError(Exception):
    """画像処理エラー"""
    pass

class BedrockError(Exception):
    """Bedrock機能エラー"""
    pass
