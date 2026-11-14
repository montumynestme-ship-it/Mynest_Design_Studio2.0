"""CLI script to evaluate YOLO detector and produce visual debugger overlays."""

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from PIL import Image

from app.core.config import ML_DATASET_DIR, ML_MODELS_DIR
from app.services.ml.annotation import GroundTruthAnnotation
from app.services.ml.evaluation import evaluate_predictions
from app.services.ml.visual_debugger import render_visual_debugger_overlay
from app.services.ml.yolo_detector import YoloDetector


def _load_yolo_labels(label_file: Path, img_w: int, img_h: int) -> list[GroundTruthAnnotation]:
    """Parse standard YOLO txt label file into GroundTruthAnnotation list."""
    from app.data.classes import class_id_to_name

    annos: list[GroundTruthAnnotation] = []
    if not label_file.exists():
        return annos

    for line in label_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 5:
            cid = int(parts[0])
            cx_n, cy_n, w_n, h_n = [float(p) for p in parts[1:5]]
            annos.append(
                GroundTruthAnnotation(
                    class_id=cid,
                    class_name=class_id_to_name(cid),
                    cx=cx_n * img_w,
                    cy=cy_n * img_h,
                    w=w_n * img_w,
                    h=h_n * img_h,
                    rotation=0.0,
                    confidence=1.0,
                )
            )
    return annos


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate YOLO detector on test floor plans")
    parser.add_argument("--model", type=str, default=str(ML_MODELS_DIR / "floorplan_detector" / "weights" / "best.pt"))
    parser.add_argument("--dataset", type=str, default=str(ML_DATASET_DIR))
    parser.add_argument("--split", type=str, default="test", choices=["train", "val", "test"])
    parser.add_argument("--output", type=str, default="expected-vs-predicted.png")
    parser.add_argument("--conf", type=float, default=0.30)
    args = parser.parse_args()

    dataset_dir = Path(args.dataset)
    images_dir = dataset_dir / "images" / args.split
    labels_dir = dataset_dir / "labels" / args.split

    if not images_dir.exists():
        print(f"Error: Split images directory {images_dir} does not exist.")
        sys.exit(1)

    image_files = sorted(images_dir.glob("*.png"))
    if not image_files:
        print(f"No images found in {images_dir}.")
        sys.exit(1)

    detector = YoloDetector(model_path=args.model)

    all_gt: list[GroundTruthAnnotation] = []
    all_pred: list[GroundTruthAnnotation] = []

    first_image: Image.Image | None = None
    first_report = None

    print(f"Evaluating {len(image_files)} floor-plan images from {args.split} split...")

    for idx, img_path in enumerate(image_files):
        img = Image.open(img_path).convert("RGB")
        w, h = img.size
        lbl_path = labels_dir / f"{img_path.stem}.txt"

        gt_list = _load_yolo_labels(lbl_path, w, h)
        pred_list = detector.detect(img, confidence_threshold=args.conf)

        all_gt.extend(gt_list)
        all_pred.extend(pred_list)

        if idx == 0:
            first_image = img
            first_report = evaluate_predictions(gt_list, pred_list)

    overall_report = evaluate_predictions(all_gt, all_pred)

    print("\n" + "=" * 50)
    print(f"EVALUATION RESULTS ({args.split.upper()} SPLIT)")
    print("=" * 50)
    print(f"Ground Truth Items: {overall_report.total_gt}")
    print(f"Predicted Items:    {overall_report.total_pred}")
    print(f"True Positives:     {overall_report.tp}")
    print(f"False Positives:    {overall_report.fp}")
    print(f"False Negatives:    {overall_report.fn}")
    print(f"Precision:          {overall_report.precision:.2%}")
    print(f"Recall:             {overall_report.recall:.2%}")
    print(f"F1 Score:           {overall_report.f1_score:.2%}")
    print(f"Mean Pos Error:     {overall_report.mean_position_error_mm:.1f} mm")
    print(f"Diagnostics:        {overall_report.diagnostics_counts}")
    print("=" * 50)

    # Generate visual debugger output for first sample
    if first_image and first_report:
        out_file = Path(args.output)
        render_visual_debugger_overlay(first_image, first_report, output_path=out_file)
        print(f"\nVisual Debugger overlay saved to: {out_file.resolve()}")


if __name__ == "__main__":
    main()
