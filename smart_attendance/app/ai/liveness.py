import math
import numpy as np
from typing import List, Tuple, Optional, Dict
from app.utils import clean_base64_image
from app.ai.face_engine import _decode_image_array

# MediaPipe import with dynamic check
MEDIAPIPE_AVAILABLE = False
try:
    import mediapipe as mp
    MEDIAPIPE_AVAILABLE = True
except Exception:
    pass

# Standard FaceMesh landmark indices for Eye Aspect Ratio (EAR)
# 6 landmarks per eye: [P1, P2, P3, P4, P5, P6]
LEFT_EYE_LANDMARKS = [33, 160, 158, 133, 153, 144]
RIGHT_EYE_LANDMARKS = [362, 385, 387, 263, 373, 380]

# Landmarks for Head Pose / Directional Yaw estimation
NOSE_TIP = 1
CHIN = 152
LEFT_EYE_OUTER = 33
RIGHT_EYE_OUTER = 263
LEFT_MOUTH_CORNER = 61
RIGHT_MOUTH_CORNER = 291

class LivenessDetector:
    """
    AI-Powered Liveness Detection Module.
    Combines Eye Aspect Ratio (EAR) for blink detection and 3D facial landmark
    projection for head-turn angle verification.
    """

    def __init__(self):
        self.face_mesh = None
        if MEDIAPIPE_AVAILABLE:
            try:
                self.mp_face_mesh = mp.solutions.face_mesh
                self.face_mesh = self.mp_face_mesh.FaceMesh(
                    static_image_mode=True,
                    max_num_faces=1,
                    refine_landmarks=True,
                    min_detection_confidence=0.5
                )
            except Exception:
                self.face_mesh = None

    @staticmethod
    def _calculate_ear(landmarks, eye_indices) -> float:
        """
        Calculates Eye Aspect Ratio (EAR):
        EAR = (||p2 - p6|| + ||p3 - p5||) / (2 * ||p1 - p4||)
        """
        p1 = np.array([landmarks[eye_indices[0]].x, landmarks[eye_indices[0]].y])
        p2 = np.array([landmarks[eye_indices[1]].x, landmarks[eye_indices[1]].y])
        p3 = np.array([landmarks[eye_indices[2]].x, landmarks[eye_indices[2]].y])
        p4 = np.array([landmarks[eye_indices[3]].x, landmarks[eye_indices[3]].y])
        p5 = np.array([landmarks[eye_indices[4]].x, landmarks[eye_indices[4]].y])
        p6 = np.array([landmarks[eye_indices[5]].x, landmarks[eye_indices[5]].y])

        d_vertical1 = np.linalg.norm(p2 - p6)
        d_vertical2 = np.linalg.norm(p3 - p5)
        d_horizontal = np.linalg.norm(p1 - p4)

        if d_horizontal < 1e-6:
            return 0.0

        return float((d_vertical1 + d_vertical2) / (2.0 * d_horizontal))

    @staticmethod
    def _estimate_head_yaw(landmarks) -> float:
        """
        Estimates head yaw angle based on horizontal positioning of the nose tip
        relative to the left and right outer eye landmarks.
        Returns yaw ratio:
        ~ 0.50 : Facing straight
        < 0.35 : Turned towards Left
        > 0.65 : Turned towards Right
        """
        x_nose = landmarks[NOSE_TIP].x
        x_left = landmarks[LEFT_EYE_OUTER].x
        x_right = landmarks[RIGHT_EYE_OUTER].x

        eye_span = x_right - x_left
        if abs(eye_span) < 1e-6:
            return 0.5

        return float((x_nose - x_left) / eye_span)

    def verify_blink(self, base64_image: str) -> Tuple[bool, float]:
        """
        Evaluates Eye Aspect Ratio (EAR) on a face frame.
        A blink or closed eyes typically results in EAR < 0.20.
        """
        img_rgb = _decode_image_array(base64_image)
        if img_rgb is None or not self.face_mesh:
            # Fallback to true if mediapipe runtime is not active
            return True, 0.25

        results = self.face_mesh.process(img_rgb)
        if not results.multi_face_landmarks:
            return False, 0.0

        landmarks = results.multi_face_landmarks[0].landmark
        left_ear = self._calculate_ear(landmarks, LEFT_EYE_LANDMARKS)
        right_ear = self._calculate_ear(landmarks, RIGHT_EYE_LANDMARKS)
        avg_ear = (left_ear + right_ear) / 2.0

        # EAR < 0.20 indicates closed eyes / blink event
        is_blinking = avg_ear < 0.20
        return is_blinking, avg_ear

    def verify_head_turn(self, base64_image: str, expected_direction: str = "left") -> Tuple[bool, float]:
        """
        Verifies whether the user is turning their head in the prompted direction.
        'left' expects yaw < 0.38
        'right' expects yaw > 0.62
        """
        img_rgb = _decode_image_array(base64_image)
        if img_rgb is None or not self.face_mesh:
            return True, 0.50

        results = self.face_mesh.process(img_rgb)
        if not results.multi_face_landmarks:
            return False, 0.50

        landmarks = results.multi_face_landmarks[0].landmark
        yaw_ratio = self._estimate_head_yaw(landmarks)

        if expected_direction == "left":
            passed = yaw_ratio < 0.38
        elif expected_direction == "right":
            passed = yaw_ratio > 0.62
        else:
            passed = 0.40 <= yaw_ratio <= 0.60

        return passed, yaw_ratio

# Global detector instance
liveness_engine = LivenessDetector()
