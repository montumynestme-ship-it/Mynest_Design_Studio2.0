"""CLI script to generate synthetic floor-plan training dataset."""

import argparse
import sys
from pathlib import Path

# Add backend to path so imports work
BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import ML_DATASET_DIR
from app.services.ml.dataset_generator import generate_yolo_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic YOLO floor-plan dataset")
    parser.add_argument("--output", type=str, default=str(ML_DATASET_DIR), help="Output directory")
    parser.add_argument("--samples", type=int, default=50, help="Number of floor plan images to generate")
    parser.add_argument("--train-ratio", type=float, default=0.70, help="Ratio for train split")
    parser.add_argument("--val-ratio", type=float, default=0.20, help="Ratio for val split")
    parser.add_argument("--test-ratio", type=float, default=0.10, help="Ratio for test split")
    parser.add_argument("--imgsz", type=int, default=640, help="Canvas dimension in pixels")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")

    args = parser.parse_args()
    out_dir = Path(args.output)
    print(f"Generating {args.samples} synthetic floor-plan samples into {out_dir}...")

    stats = generate_yolo_dataset(
        output_dir=out_dir,
        num_samples=args.samples,
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        test_ratio=args.test_ratio,
        canvas_size=args.imgsz,
        seed=args.seed,
    )

    print("\nDataset Generation Complete!")
    print(f"Total samples: {stats['total_samples']}")
    print(f"Total annotations: {stats['total_annotations']}")
    print(f"Splits: {stats['samples_count']}")
    print(f"data.yaml: {stats['data_yaml']}")


if __name__ == "__main__":
    main()
