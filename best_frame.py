"""
best_frame.py — 여러 프레임/크롭 중 가장 선명한(흔들림 적은) 한 장 선택

사진 방식(스틸 전송)에서 모션블러를 줄이기 위해, 전주당 확보된 여러 크롭 중
Laplacian variance(초점/선명도 지표)가 가장 높은 프레임을 골라 서버로 보낸다.
"""
import cv2
import numpy as np


def sharpness(img: np.ndarray) -> float:
    """Laplacian variance — 값이 클수록 선명(초점 잘 맞음)."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def select_best(frames):
    """frames 중 가장 선명한 (frame, sharpness) 반환. 비어있으면 (None, -1)."""
    best, best_s = None, -1.0
    for f in frames:
        if f is None:
            continue
        s = sharpness(f)
        if s > best_s:
            best, best_s = f, s
    return best, best_s


def encode_jpeg(img: np.ndarray, quality: int = 90):
    """이미지를 JPEG 바이트로 인코딩. 실패 시 None."""
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    return buf.tobytes() if ok else None
