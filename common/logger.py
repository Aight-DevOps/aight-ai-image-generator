#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ColorLogger - シェルスクリプトのカラー出力完全再現
全ツール共通のカラー出力ロガー
"""

class ColorLogger:
    """シェルスクリプトのカラー出力完全再現"""
    
    def __init__(self):
        # シェルスクリプトと同じANSIカラーコード
        self.GREEN = '\033[0;32m'
        self.YELLOW = '\033[0;33m'
        self.RED = '\033[0;31m'
        self.BLUE = '\033[0;34m'
        self.CYAN = '\033[0;36m'
        self.MAGENTA = '\033[0;35m'
        self.NC = '\033[0m'  # No Color
    
    def print_status(self, message):
        """[INFO] メッセージ（青色）"""
        print(f"{self.BLUE}[INFO]{self.NC} {message}")
    
    def print_success(self, message):
        """[SUCCESS] メッセージ（緑色）"""
        print(f"{self.GREEN}[SUCCESS]{self.NC} {message}")
    
    def print_warning(self, message):
        """[WARNING] メッセージ（黄色）"""
        print(f"{self.YELLOW}[WARNING]{self.NC} {message}")
    
    def print_error(self, message):
        """[ERROR] メッセージ（赤色）"""
        print(f"{self.RED}[ERROR]{self.NC} {message}")
    
    def print_stage(self, message):
        """[STAGE] メッセージ（シアン色）"""
        print(f"{self.CYAN}[STAGE]{self.NC} {message}")
    
    def print_timing(self, message):
        """[TIMING] メッセージ（マゼンタ色）"""
        print(f"{self.MAGENTA}[TIMING]{self.NC} {message}")
