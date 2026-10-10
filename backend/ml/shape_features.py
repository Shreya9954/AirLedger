"""Shape cues that separate contrails from natural cirrus, plus the rule-based placeholder classifier.

Contrails are long, thin and straight; natural cirrus is broad and curved. A matching advected
flight track is the strongest single cue. The planned model is a segmentation network (e.g. a
U-Net) trained on OpenContrails; these features remain useful for attribution and QA.
Mirrors frontend/js/ui/lab.js classify().
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

GOES_PIXEL_KM = 2.0  # ABI infrared pixel size near nadir


@dataclass
class ShapeFeatures:
    linearity: float   # 0 = round blob, 1 = perfect line
    length_km: float
    width_km: float


def shape_features(component: np.ndarray, pixel_km: float = GOES_PIXEL_KM) -> ShapeFeatures:
    """Features of one connected region (boolean mask) from the eigenvalues of its pixel cloud."""
    ys, xs = np.nonzero(component)
    if len(xs) < 3:
        return ShapeFeatures(0.0, 0.0, 0.0)
    pts = np.stack([xs, ys], axis=1).astype(float)
    pts -= pts.mean(axis=0)
    ev = np.sort(np.linalg.eigvalsh(np.cov(pts.T)))[::-1]
    major, minor = np.sqrt(np.maximum(ev, 0))
    linearity = float(1 - minor / major) if major > 0 else 0.0
    length = 4 * major * pixel_km            # ~full extent of a uniform line
    width = len(xs) * pixel_km ** 2 / max(length, pixel_km)
    return ShapeFeatures(linearity, float(length), float(width))


def classify(linearity: float, track_offset_km: float | None, mixed_with_cirrus: bool = False) -> str:
    straight = linearity > 0.7
    matched = track_offset_km is not None and track_offset_km < 10
    if straight and matched:
        return "Contrail over cirrus" if mixed_with_cirrus else "Contrail, attributed"
    if straight:
        return "Contrail, unattributed"
    return "Natural cirrus"
