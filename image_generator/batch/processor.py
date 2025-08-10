from common.logger import ColorLogger
from typing import Dict, Any
from ..core.generator import HybridBijoImageGeneratorV7, GenerationType

class BatchProcessor:
    """バッチ処理ラッパー"""
    def __init__(self, generator: HybridBijoImageGeneratorV7, config: Dict[str, Any]):
        self.generator = generator
        self.config = config
        self.logger = ColorLogger()
        
        # generatorインスタンスの検証とデバッグ出力
        self.logger.print_status(f"Generator type: {type(self.generator).__name__}")
        available_methods = [m for m in dir(self.generator) if not m.startswith('_') and callable(getattr(self.generator, m))]
        self.logger.print_status(f"Available methods: {available_methods}")
        
        # 必要なメソッドの存在確認
        if not hasattr(self.generator, 'generate_hybrid_image'):
            raise AttributeError(f"generator instance lacks 'generate_hybrid_image' method. "
                               f"Available methods: {available_methods}")

    def generate_hybrid_image(self, gen_type: GenerationType, count: int) -> int:
        """単発生成 + 後続処理呼び出し"""
        # 正しいメソッド名を使用
        return self.generator.generate_hybrid_image(gen_type, count)

    def generate_hybrid_batch(self, genre: str, count: int) -> int:
        """指定ジャンルでバッチ実行"""
        # ジャンル名に対応する GenerationType を探索
        gt = next((g for g in self.generator.generation_types if g.name == genre), None)
        if not gt:
            self.logger.print_error(f"未定義ジャンル: {genre}")
            return 0
        
        # generate_hybrid_imageメソッドを使用
        return self.generator.generate_hybrid_image(gt, count)

    def generate_daily_hybrid_batch(self) -> None:
        """日次バッチ呼び出し"""
        # 日次バッチ用の適切なメソッドを確認
        if hasattr(self.generator, 'generate_daily_batch'):
            self.generator.generate_daily_batch()
        elif hasattr(self.generator, 'generate_daily_hybrid_batch'):
            self.generator.generate_daily_hybrid_batch()
        else:
            self.logger.print_error("日次バッチ用メソッドが見つかりません")
            # フォールバック：複数ジャンルで個別実行
            batch_size = self.config.get('generation', {}).get('batch_size', 5)
            total_success = 0
            
            for gt in self.generator.generation_types:
                success = self.generator.generate_hybrid_image(gt, 1)
                total_success += success
                
            self.logger.print_success(f"フォールバック日次バッチ完了: {total_success}件")
