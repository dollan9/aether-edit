"""
AETHER-EDIT: Vision Telemetry Analyzer
OpenCV Scene Cut Detection, Motion Vector Scoring, Dominant RGB Calculation,
and Object/Face Bounding Box Detection (Sampled Every 5 Frames)
"""

import logging
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np

from core.schema import BoundingBox, SceneCut, VisualTelemetry

logger = logging.getLogger("aether_edit.vision_analyzer")


class VisionAnalyzer:
    """Performs frame-by-frame visual telemetry extraction using OpenCV."""

    def __init__(self) -> None:
        # Load OpenCV Haar Cascades for reliable, offline face and person detection
        try:
            self._face_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            )
        except Exception:
            self._face_cascade = None

        # Initialize HOG pedestrian detector
        try:
            self._hog = cv2.HOGDescriptor()
            self._hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        except Exception:
            self._hog = None

    def analyze_video(
        self, video_path: Path, sample_interval: int = 5, cut_threshold: float = 30.0
    ) -> VisualTelemetry:
        """
        Analyze video for scene cuts, motion scores, dominant RGB, and bounding boxes.
        `sample_interval`: Sample objects every N frames (default 5).
        """
        telemetry = VisualTelemetry()
        cap = cv2.VideoCapture(str(video_path.resolve()))
        if not cap.isOpened():
            logger.error(f"Cannot open video for vision analysis: {video_path}")
            return telemetry

        fps = cap.get(cv2.CAP_PROP_FPS) or 60.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1920)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1080)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

        prev_gray: Optional[np.ndarray] = None
        prev_hist: Optional[np.ndarray] = None

        current_scene_idx = 1
        scene_start_frame = 0
        scene_motion_scores: List[float] = []
        scene_colors: List[np.ndarray] = []

        frame_idx = 0
        boxes_dict: Dict[int, List[BoundingBox]] = {}

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # Convert to RGB & Grayscale for analysis
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            # Downsample for high-speed motion & cut detection
            small_gray = cv2.resize(gray, (160, 90))
            hsv = cv2.cvtColor(cv2.resize(frame, (160, 90)), cv2.COLOR_BGR2HSV)
            hist = cv2.calcHist([hsv], [0, 1], None, [16, 16], [0, 180, 0, 256])
            cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)

            # 1. Motion Score Calculation
            motion_score = 0.0
            if prev_gray is not None:
                frame_diff = cv2.absdiff(small_gray, prev_gray)
                motion_score = float(np.mean(frame_diff))
                scene_motion_scores.append(motion_score)

            # Sample dominant color
            scene_colors.append(np.mean(frame, axis=(0, 1)))

            # 2. Scene Cut Detection
            is_cut = False
            if prev_hist is not None:
                diff = cv2.compareHist(hist, prev_hist, cv2.HISTCMP_CHISQR)
                if diff > cut_threshold and (frame_idx - scene_start_frame) > 15:
                    is_cut = True

            if is_cut and frame_idx > scene_start_frame:
                start_sec = scene_start_frame / fps
                end_sec = frame_idx / fps
                avg_motion = float(np.mean(scene_motion_scores)) if scene_motion_scores else 0.0
                mean_bgr = np.mean(scene_colors, axis=0) if scene_colors else [0, 0, 0]
                dominant_rgb = [int(mean_bgr[2]), int(mean_bgr[1]), int(mean_bgr[0])]

                telemetry.scene_cuts.append(
                    SceneCut(
                        scene_index=current_scene_idx,
                        start_frame=scene_start_frame,
                        end_frame=frame_idx,
                        start_sec=round(start_sec, 3),
                        end_sec=round(end_sec, 3),
                        avg_motion_score=round(avg_motion, 2),
                        dominant_rgb=dominant_rgb,
                    )
                )
                current_scene_idx += 1
                scene_start_frame = frame_idx
                scene_motion_scores.clear()
                scene_colors.clear()

            prev_gray = small_gray
            prev_hist = hist

            # 3. Bounding Box Detection (Sampled every N frames)
            if frame_idx % sample_interval == 0:
                frame_boxes = self._detect_frame_objects(frame, gray, width, height)
                if frame_boxes:
                    boxes_dict[frame_idx] = frame_boxes

            frame_idx += 1

        # Final scene cut flush
        if frame_idx > scene_start_frame:
            start_sec = scene_start_frame / fps
            end_sec = frame_idx / fps
            avg_motion = float(np.mean(scene_motion_scores)) if scene_motion_scores else 0.0
            mean_bgr = np.mean(scene_colors, axis=0) if scene_colors else [0, 0, 0]
            dominant_rgb = [int(mean_bgr[2]), int(mean_bgr[1]), int(mean_bgr[0])]

            telemetry.scene_cuts.append(
                SceneCut(
                    scene_index=current_scene_idx,
                    start_frame=scene_start_frame,
                    end_frame=frame_idx,
                    start_sec=round(start_sec, 3),
                    end_sec=round(end_sec, 3),
                    avg_motion_score=round(avg_motion, 2),
                    dominant_rgb=dominant_rgb,
                )
            )

        cap.release()
        telemetry.bounding_boxes = boxes_dict
        return telemetry

    def _detect_frame_objects(
        self, frame: np.ndarray, gray: np.ndarray, width: int, height: int
    ) -> List[BoundingBox]:
        boxes: List[BoundingBox] = []

        # Face detection
        if self._face_cascade is not None:
            faces = self._face_cascade.detectMultiScale(
                gray, scaleFactor=1.15, minNeighbors=4, minSize=(30, 30)
            )
            for (x, y, w, h) in faces:
                norm_box = [
                    round(x / width, 4),
                    round(y / height, 4),
                    round((x + w) / width, 4),
                    round((y + h) / height, 4),
                ]
                boxes.append(BoundingBox(label="face", confidence=0.88, bbox_norm=norm_box))

        # Pedestrian / person detection
        if self._hog is not None and len(boxes) == 0:
            rects, weights = self._hog.detectMultiScale(
                frame, winStride=(8, 8), padding=(4, 4), scale=1.1
            )
            for rect, weight in zip(rects, weights):
                if weight > 0.4:
                    x, y, w, h = rect
                    norm_box = [
                        round(x / width, 4),
                        round(y / height, 4),
                        round((x + w) / width, 4),
                        round((y + h) / height, 4),
                    ]
                    boxes.append(
                        BoundingBox(label="person", confidence=round(float(weight), 2), bbox_norm=norm_box)
                    )

        return boxes
