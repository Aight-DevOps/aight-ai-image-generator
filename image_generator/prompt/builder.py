#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PromptBuilder - プロンプト構築機能（完全版）
ランダム要素統合とネガティブプロンプト強化 + ポーズ指定モード修正版
"""

import os
from common.logger import ColorLogger

class HandFootEmbeddingManager:
    """手足強化用Embedding管理クラス"""

    def __init__(self, config: dict, logger):
        self.config = config
        self.logger = logger
        self.hf_config = config.get('hand_foot_enhancement', {})
        self.embeddings_enabled = self.hf_config.get('use_embeddings', False)
        self.global_enabled = self.hf_config.get('enabled', False)
        self.embedding_files = self.hf_config.get('embedding_files', [])
        self.placement = self.hf_config.get('embedding_placement', 'negative_prompt')

    def validate_embedding_files(self) -> bool:
        """embeddingファイルの存在確認"""
        if not self.embeddings_enabled:
            return True

        missing_files = []
        for embedding in self.embedding_files:
            file_path = embedding.get('file_path', '')
            if file_path and not os.path.exists(file_path):
                missing_files.append(f"{embedding.get('name', 'unknown')} at {file_path}")

        if missing_files:
            self.logger.print_warning("Missing embedding files:")
            for file in missing_files:
                self.logger.print_warning(f" ✗ {file}")
            self.logger.print_warning("Download from: https://civitai.com/models/116230/bad-hands-5")
            return False

        return True

    def get_embedding_tokens(self) -> str:
        """使用するembeddingトークンを取得"""
        if not self.embeddings_enabled or not self.global_enabled:
            return ""

        if not self.validate_embedding_files():
            return ""

        tokens = []
        for embedding in self.embedding_files:
            name = embedding.get('name', '')
            weight = embedding.get('weight', 1.0)
            condition = embedding.get('condition', 'always')

            # 条件チェック
            if condition == 'hands_enhancement_enabled' and not self.global_enabled:
                continue

            # トークン形式の決定
            if weight != 1.0:
                token = f"({name}:{weight})"
            else:
                token = name

            tokens.append(token)

        result = ", ".join(tokens)
        if result:
            self.logger.print_status(f"✓ Embedding tokens applied: {result}")
        return result

class PromptBuilder:
    """プロンプト構築クラス（完全版・ポーズ指定モード修正版）"""

    def __init__(self, config: dict, prompts_data: dict, gen_types_data: dict):
        self.config = config
        self.prompts_data = prompts_data
        self.gen_types_data = gen_types_data
        self.logger = ColorLogger()

        # プロンプトデータ初期化
        self.quality_prompts = prompts_data.get('quality_prompts', {})
        self.face_prompts = prompts_data.get('face_prompts', {})
        self.body_prompts = prompts_data.get('body_prompts', {})
        self.user_prompts = prompts_data.get('user_prompts', {})
        self.negative_prompts = prompts_data.get('negative_prompts', {})
        self.anatomy_prompts = prompts_data.get('anatomy_prompts', {})
        self.single_person_prompts = prompts_data.get('single_person_prompts', {})

        # 手足強化設定
        self.hand_foot_enhancement = config.get('hand_foot_enhancement', {})
        self.hand_foot_enabled = self.hand_foot_enhancement.get('enabled', True)

    def build_prompts(self, gen_type, mode="auto"):
        """プロンプト構築メイン（ランダム要素統合版）"""
        try:
            # 基本プロンプト構築
            base_prompt = self._build_base_prompt(gen_type)

            # ランダム要素追加（重要な修正点）
            random_elements = self._get_random_elements_prompt(gen_type)

            # 年齢プロンプト
            age_prompt = self._get_age_prompt(gen_type)

            # LoRAプロンプト
            lora_prompt = self._get_lora_prompt(gen_type)

            # 手足強化プロンプト
            hand_foot_prompt = self._get_hand_foot_prompt()

            # 最終プロンプト統合
            final_prompt = f"{base_prompt}, {random_elements}, {age_prompt}, {lora_prompt}, {hand_foot_prompt}".strip(', ')

            # ネガティブプロンプト構築（強化版）
            negative_prompt = self._build_comprehensive_negative_prompt(gen_type)
            adetailer_negative = self._build_adetailer_negative_prompt(gen_type)

            self.logger.print_success(f"✅ プロンプト構築完了 (長さ: {len(final_prompt)})")
            self.logger.print_status(f"🔧 ランダム要素: {random_elements[:100]}...")

            return final_prompt, negative_prompt, adetailer_negative

        except Exception as e:
            self.logger.print_error(f"❌ プロンプト構築エラー: {e}")
            # フォールバック
            return gen_type.prompt, gen_type.negative_prompt, ""

    def _build_base_prompt(self, gen_type):
        """基本プロンプト構築"""
        parts = [
            self.quality_prompts.get('sdxl_unified', ''),
            str(gen_type.prompt) if gen_type.prompt else '',
            self.face_prompts.get('sdxl_unified', ''),
            self.body_prompts.get('sdxl_unified', ''),
            self.anatomy_prompts.get('accurate_hands', ''),
            self.anatomy_prompts.get('accurate_feet', ''),
            self.anatomy_prompts.get('perfect_anatomy', ''),
            self.anatomy_prompts.get('neck_position', ''),
            self.anatomy_prompts.get('skeletal_structure', ''),
            self.anatomy_prompts.get('full_anatomy', ''),
            self.single_person_prompts.get('solo_emphasis', ''),
            self.user_prompts.get('nsfw_content', ''),
            self.user_prompts.get('ethnicity', '')
        ]

        valid_parts = [p for p in parts if p and p.strip()]
        return ', '.join(valid_parts)

    def _get_random_elements_prompt(self, gen_type, pose_mode=None):
        """ランダム要素プロンプト取得（pose_mode対応版）"""
        from ..randomization.element_generator import RandomElementGenerator

        # ランダム要素ジェネレーター初期化
        if not hasattr(self, '_element_generator'):
            import yaml
            try:
                with open('config/random_elements.yaml', 'r', encoding='utf-8') as f:
                    random_data = yaml.safe_load(f)
                
                self._element_generator = RandomElementGenerator(
                    random_data.get('specific_random_elements', {}),
                    random_data.get('general_random_elements', {}),
                    history_file=None
                )
                self.logger.print_status("🎲 RandomElementGenerator初期化完了")
            except Exception as e:
                self.logger.print_warning(f"⚠️ ランダム要素読み込みエラー: {e}")
                return ""

        # ★ 重要な修正点: pose_modeを渡す
        try:
            random_prompt = self._element_generator.generate_elements(gen_type, pose_mode=pose_mode)
            self.logger.print_status(f"🎲 ランダム要素生成: {random_prompt[:50]}...")
            return random_prompt
        except Exception as e:
            self.logger.print_warning(f"⚠️ ランダム要素生成エラー: {e}")
            return ""

    def _get_age_prompt(self, gen_type):
        """年齢プロンプト生成"""
        if hasattr(gen_type, 'age_range') and gen_type.age_range:
            import random
            min_age, max_age = gen_type.age_range
            selected_age = random.randint(min_age, max_age)
            return f"BREAK, {selected_age} years old"
        return ""

    def _get_lora_prompt(self, gen_type):
        """LoRAプロンプト生成"""
        if not hasattr(gen_type, 'lora_settings') or not gen_type.lora_settings:
            return ""

        lora_prompts = []
        for lora_setting in gen_type.lora_settings:
            lora_id = lora_setting.get('lora_id')
            strength_range = lora_setting.get('strength_range', [0.5, 1.0])
            
            if not lora_id:
                continue

            # 強度ランダム選択
            import random
            min_strength, max_strength = strength_range
            steps = int((max_strength - min_strength) / 0.01) + 1
            strength = min_strength + random.randint(0, steps - 1) * 0.01
            strength = round(strength, 2)

            lora_prompt = f"<lora:{lora_id}:{strength}>"
            lora_prompts.append(lora_prompt)

        return ', '.join(lora_prompts)

    def _get_hand_foot_prompt(self):
        """手足強化プロンプト"""
        if not self.hand_foot_enabled:
            return ""

        hand_prompts = self.hand_foot_enhancement.get('hand_specific_prompts', [])
        foot_prompts = self.hand_foot_enhancement.get('foot_specific_prompts', [])
        all_prompts = hand_prompts + foot_prompts

        return ', '.join(all_prompts)

    def _build_comprehensive_negative_prompt(self, gen_type):
        """包括的ネガティブプロンプト構築（embedding対応版）"""
        negative_parts = []

        # 基本ネガティブプロンプト
        base_negative = self.negative_prompts.get('comprehensive', '')
        if base_negative:
            negative_parts.append(base_negative)

        # 生成タイプ固有のネガティブプロンプト
        if hasattr(gen_type, 'negative_prompt') and gen_type.negative_prompt:
            negative_parts.append(gen_type.negative_prompt)

        # 手足強化用ネガティブプロンプト
        if self.hand_foot_enabled:
            hand_foot_negative = self.negative_prompts.get('hand_foot_negative', '')
            neck_skeleton_negative = self.negative_prompts.get('neck_skeleton_negative', '')
            
            if hand_foot_negative:
                negative_parts.append(hand_foot_negative)
            if neck_skeleton_negative:
                negative_parts.append(neck_skeleton_negative)

        # Embedding統合
        embedding_manager = HandFootEmbeddingManager(self.config, self.logger)
        embedding_tokens = embedding_manager.get_embedding_tokens()
        if embedding_tokens and embedding_manager.placement == 'negative_prompt':
            negative_parts.append(embedding_tokens)

        return ', '.join(negative_parts)

    def _build_adetailer_negative_prompt(self, gen_type):
        """ADetailer用ネガティブプロンプト構築"""
        adetailer_parts = []

        # ADetailer基本ネガティブ
        ad_negative = self.negative_prompts.get('adetailer_negative', '')
        if ad_negative:
            adetailer_parts.append(ad_negative)

        # 生成タイプ固有のネガティブプロンプト
        if hasattr(gen_type, 'negative_prompt') and gen_type.negative_prompt:
            adetailer_parts.append(gen_type.negative_prompt)

        # 手足強化用ネガティブプロンプト
        if self.hand_foot_enabled:
            hand_foot_negative = self.negative_prompts.get('hand_foot_negative', '')
            if hand_foot_negative:
                adetailer_parts.append(hand_foot_negative)

        return ', '.join(adetailer_parts)

    def build_complete_prompts(self, gen_type, mode="auto", pose_mode=None, pose_manager=None, **kwargs):
        """完全統合型プロンプト構築（ポーズ指定モード修正版）"""
        try:
            # 1. 基本プロンプト
            base_prompt = self._build_base_prompt(gen_type)

            # 2. ランダム要素 (重要な修正)
            random_elements = ""
            if kwargs.get('include_random_elements', True):
                # ★ 重要な修正点: pose_modeを渡す
                random_elements = self._get_random_elements_prompt(gen_type, pose_mode=pose_mode)

            # 3-6. 他のプロンプト要素（既存通り）
            age_prompt = ""
            if kwargs.get('include_age', True):
                age_prompt = self._get_age_prompt(gen_type)

            lora_prompt = ""
            if kwargs.get('include_lora', True):
                lora_prompt = self._get_lora_prompt(gen_type)

            pose_prompt = ""
            if kwargs.get('include_pose', True):
                # ★ 修正: pose_managerを直接使用
                pose_prompt = self._get_pose_prompt(gen_type, pose_manager)

            hand_foot_prompt = self._get_hand_foot_prompt()

            # 7-8. 統合処理（既存通り）
            embedding_manager = HandFootEmbeddingManager(self.config, self.logger)
            embedding_tokens = embedding_manager.get_embedding_tokens()

            prompt_parts = [
                base_prompt,
                random_elements,
                age_prompt,
                hand_foot_prompt,
                pose_prompt,
                lora_prompt
            ]

            if embedding_tokens and embedding_manager.placement == 'positive_prompt':
                prompt_parts.append(embedding_tokens)

            final_prompt = ', '.join([part for part in prompt_parts if part and part.strip()])

            # 9. ネガティブプロンプト（既存通り）
            negative_prompt = self._build_comprehensive_negative_prompt(gen_type)
            adetailer_negative = self._build_adetailer_negative_prompt(gen_type)

            self.logger.print_success(f"✅ 完全統合プロンプト構築完了 (長さ: {len(final_prompt)})")
            self.logger.print_status(f"🎲 ランダム要素: {random_elements[:50]}...")

            return final_prompt, negative_prompt, adetailer_negative

        except Exception as e:
            self.logger.print_error(f"❌ 完全統合プロンプト構築エラー: {e}")
            return gen_type.prompt, gen_type.negative_prompt, ""

    def _get_pose_prompt(self, gen_type, pose_manager=None):
        """ポーズプロンプト取得（修正版・pose_manager直接使用）"""
        try:
            if pose_manager:
                # ★ 修正: 渡されたpose_managerを使用
                pose_prompt = pose_manager.generate_pose_prompt(gen_type)
                if pose_prompt:
                    self.logger.print_status(f"🎯 ポーズプロンプト生成: {pose_prompt}")
                return pose_prompt
            else:
                self.logger.print_warning("⚠️ PoseManagerが提供されていません")
                return ""
        except Exception as e:
            self.logger.print_warning(f"⚠️ ポーズプロンプト生成エラー: {e}")
            return ""
