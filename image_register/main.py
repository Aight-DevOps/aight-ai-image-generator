#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Hybrid Bijo Register メイン実行
- メニュー表示 & バッチ選択
"""

from common.logger import ColorLogger
from .core.register import HybridBijoRegisterV9

def main():
    logger = ColorLogger()
    logger.print_stage("🚀 Hybrid Bijo Register v9 開始")
    register = HybridBijoRegisterV9()
    genres = list(register.config['batch_directories'].keys())

    while True:
        print("\n" + "="*60)
        print("📋 ジャンル選択メニュー")
        for i, g in enumerate(genres, 1):
            print(f"{i}. {g}")
        print(f"{len(genres)+1}. 終了")
        print("="*60)

        choice = input("選択: ").strip()
        if not choice.isdigit():
            continue
        idx = int(choice)
        if idx == len(genres)+1:
            break
        if 1 <= idx <= len(genres):
            genre = genres[idx-1]
            register.process_batch(genre)
        else:
            continue

if __name__ == "__main__":
    main()
