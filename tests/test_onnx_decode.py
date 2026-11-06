"""ONNX post-processing tests with synthetic tensors; no onnxruntime required."""
import numpy as np

from sdk.backend.onnx import _decode


def _tensor() -> np.ndarray:
    d = np.zeros((84, 2), dtype=np.float32)
    d[0, 0], d[1, 0], d[2, 0], d[3, 0] = 320, 240, 64, 32
    d[4, 0] = 0.9  # person
    d[0, 1], d[1, 1], d[2, 1], d[3, 1] = 100, 100, 20, 20
    d[6, 1] = 0.5  # car
    return d


def test_decodes_channels_first_layout():
    dets = _decode(_tensor()[None], scale=1.0, left=0, top=0, conf=0.4)
    assert {d.cls_name for d in dets} == {"person", "car"}
    person = next(d for d in dets if d.cls_name == "person")
    assert (person.bbox_2d.x, person.bbox_2d.y) == (288.0, 224.0)
    assert (person.bbox_2d.w, person.bbox_2d.h) == (64.0, 32.0)


def test_decodes_channels_last_layout():
    dets = _decode(_tensor().T[None], scale=1.0, left=0, top=0, conf=0.4)
    assert {d.cls_name for d in dets} == {"person", "car"}


def test_applies_letterbox_scale_and_padding():
    dets = _decode(_tensor()[None], scale=2.0, left=10, top=20, conf=0.4)
    person = next(d for d in dets if d.cls_name == "person")
    assert (person.bbox_2d.x, person.bbox_2d.y) == ((288 - 10) / 2, (224 - 20) / 2)


def test_filters_low_confidence_and_caps_max_det():
    dets = _decode(_tensor()[None], scale=1.0, left=0, top=0, conf=0.6)
    assert [d.cls_name for d in dets] == ["person"]
    capped = _decode(_tensor()[None], scale=1.0, left=0, top=0, conf=0.4, max_det=1)
    assert len(capped) == 1
    assert capped[0].cls_name == "person"
