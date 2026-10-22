"""CLI script to train Ultralytics YOLO model on generated floor-plan dataset."""

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import ML_DATASET_DIR, ML_MODELS_DIR


def main() -> None:
    parser = argparse.ArgumentParser(description="Train YOLO on floor-plan dataset")
    parser.add_argument("--data", type=str, default=str(ML_DATASET_DIR / "data.yaml"), help="Path to data.yaml")
    parser.add_argument("--model", type=str, default="yolov8n.pt", help="Pretrained model weights to start from")
    parser.add_argument("--epochs", type=int, default=5, help="Number of training epochs")
    parser.add_argument("--batch", type=int, default=8, help="Batch size")
    parser.add_argument("--imgsz", type=int, default=640, help="Image size")
    parser.add_argument("--workers", type=int, default=2, help="Dataloader worker threads")
    parser.add_argument("--device", type=str, default="cpu", help="Device to train on ('cpu' or '0')")
    parser.add_argument("--output", type=str, default=str(ML_MODELS_DIR), help="Output models directory")

    args = parser.parse_args()

    try:
        from ultralytics import YOLO
    except ImportError:
        print("Error: ultralytics is not installed. Please install it with: pip install ultralytics")
        sys.exit(1)

    data_path = Path(args.data)
    if not data_path.exists():
        print(f"Error: data.yaml not found at {data_path}. Generate dataset first using generate_dataset.py.")
        sys.exit(1)

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== Starting YOLO training ===")
    print(f"Model: {args.model}")
    print(f"Data: {data_path}")
    print(f"Epochs: {args.epochs}, Batch: {args.batch}, ImgSz: {args.imgsz}")
    print(f"Device: {args.device}")

    model = YOLO(args.model)
    results = model.train(
        data=str(data_path),
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.imgsz,
        device=args.device,
        workers=args.workers,
        project=str(out_dir),
        name="floorplan_detector",
        exist_ok=True,
    )

    print("\n=== Training Completed Successfully! ===")
    best_weights = out_dir / "floorplan_detector" / "weights" / "best.pt"
    if best_weights.exists():
        print(f"Best model saved at: {best_weights.resolve()}")


if __name__ == "__main__":
    main()
