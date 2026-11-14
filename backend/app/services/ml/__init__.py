"""MyNest ML/DL Floor-Plan Object Detection & Auto-Annotation System."""

from app.services.ml.annotation import GroundTruthAnnotation
from app.services.ml.dataset_generator import SyntheticFloorPlanGenerator, generate_yolo_dataset
from app.services.ml.detector import FloorPlanDetector
from app.services.ml.evaluation import DiagnosticStatus, EvaluationReport, evaluate_predictions
from app.services.ml.inference import FloorPlanInferenceService
from app.services.ml.scene_bridge import detections_to_canonical_json, detections_to_layout_items
from app.services.ml.svg_rasterizer import get_furniture_image, render_svg_to_image
from app.services.ml.visual_debugger import render_visual_debugger_overlay
from app.services.ml.yolo_detector import YoloDetector

__all__ = [
    "FloorPlanDetector",
    "YoloDetector",
    "FloorPlanInferenceService",
    "SyntheticFloorPlanGenerator",
    "generate_yolo_dataset",
    "GroundTruthAnnotation",
    "evaluate_predictions",
    "EvaluationReport",
    "DiagnosticStatus",
    "render_visual_debugger_overlay",
    "get_furniture_image",
    "render_svg_to_image",
    "detections_to_canonical_json",
    "detections_to_layout_items",
]
