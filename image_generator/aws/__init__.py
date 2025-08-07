#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AWS module for image generation
AWS連携機能モジュール
"""

from .bedrock import BedrockManager
from .metadata import MetadataManager

__all__ = [
    'BedrockManager',
    'MetadataManager'
]
