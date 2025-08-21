#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RandomElementGenerator - ランダム要素生成（完全版）
髪型、髪質、髪色、服装、ポーズなどの要素をランダム選択
"""

import random
import json
from common.logger import ColorLogger

class RandomElementGenerator:
    """ランダム要素生成クラス（完全版）"""
    
    def __init__(self, specific_elements: dict, general_elements: dict, history_file: str = None):
        self.specific_elements = specific_elements
        self.general_elements = general_elements
        self.history_file = history_file
        self.logger = ColorLogger()
        
        # 使用履歴管理
        self.usage_history = {}
        
        self.logger.print_success("✅ RandomElementGenerator初期化完了")

    def generate_elements(self, gen_type, pose_mode=None, max_general: int = 3) -> str:
        """ランダム要素生成メイン（pose_mode対応版）"""
        additional_prompt_parts = []
        try:
            # 生成タイプのランダム要素を処理
            if hasattr(gen_type, 'random_elements') and gen_type.random_elements:
                # ★ 重要な修正点: ポーズ検出モード時は「poses」を除外
                element_types = gen_type.random_elements.copy()
                if pose_mode == "detection" and "poses" in element_types:
                    element_types.remove("poses")
                    self.logger.print_status(f"🚫 ポーズ検出モードのため「poses」要素をスキップしました")
                
                for element_type in element_types:
                    element_text = self._generate_single_element(element_type)
                    if element_text:
                        additional_prompt_parts.append(element_text)
                    self.logger.print_status(f"🎲 {element_type}: {element_text}")
                    
            # 結果統合
            result = ', '.join(additional_prompt_parts)
            self.logger.print_success(f"✅ ランダム要素生成完了: {len(additional_prompt_parts)}個")
            return result
        except Exception as e:
            self.logger.print_error(f"❌ ランダム要素生成エラー: {e}")
            return ""


    def _generate_single_element(self, element_type: str) -> str:
        """単一要素のランダム生成"""
        try:
            # specific_elementsから取得を試行
            element_options = self.specific_elements.get(element_type)
            
            if not element_options:
                # general_elementsから取得を試行
                element_options = self.general_elements.get(element_type)
            
            if not element_options:
                self.logger.print_warning(f"⚠️ 要素が見つかりません: {element_type}")
                return ""
            
            # 髪型の特殊処理（length + style構造）
            if element_type == 'hairstyles':
                return self._generate_hairstyle(element_options)
            
            # 通常のリスト要素処理
            if isinstance(element_options, list):
                selected = random.choice(element_options)
                return str(selected).strip()
            
            # 辞書形式の要素処理
            if isinstance(element_options, dict):
                # 辞書の値をリスト化して選択
                all_values = []
                for key, values in element_options.items():
                    if isinstance(values, list):
                        all_values.extend(values)
                    else:
                        all_values.append(str(values))
                
                if all_values:
                    selected = random.choice(all_values)
                    return str(selected).strip()
            
            return ""
            
        except Exception as e:
            self.logger.print_warning(f"⚠️ 要素生成エラー ({element_type}): {e}")
            return ""

    def _generate_hairstyle(self, hairstyle_options) -> str:
        """髪型の特殊生成処理"""
        try:
            if not isinstance(hairstyle_options, list):
                return ""
            
            # ランダムに髪の長さを選択
            length_option = random.choice(hairstyle_options)
            
            if not isinstance(length_option, dict):
                return str(length_option)
            
            length = length_option.get('length', '')
            styles = length_option.get('style', [])
            
            if not styles:
                return length
            
            # ランダムにスタイルを選択
            selected_style = random.choice(styles)
            
            return f"{length}, {selected_style}"
            
        except Exception as e:
            self.logger.print_warning(f"⚠️ 髪型生成エラー: {e}")
            return ""

    def get_usage_stats(self) -> dict:
        """使用統計取得"""
        return {
            'total_generated': len(self.usage_history),
            'element_counts': dict(self.usage_history)
        }
