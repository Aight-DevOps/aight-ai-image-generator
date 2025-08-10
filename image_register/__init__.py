#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Image Register module for Aight AI Image Generator
画像登録ツールモジュール
"""

# 循環インポートを避けるため、必要最小限のインポートに留める
__version__ = "1.0"

def get_register():
    """遅延インポートでレジスターを取得"""
    from .core.register import HybridBijoRegisterV9
    return HybridBijoRegisterV9

__all__ = ["get_register"]
