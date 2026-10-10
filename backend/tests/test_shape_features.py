import numpy as np

from ml.shape_features import classify, shape_features


def test_thin_line_is_linear():
    m = np.zeros((64, 64), bool)
    m[30:32, 4:60] = True
    f = shape_features(m)
    assert f.linearity > 0.9 and f.width_km < 8


def test_blob_is_not_linear():
    yy, xx = np.mgrid[:64, :64]
    m = (yy - 32) ** 2 + (xx - 32) ** 2 < 15 ** 2
    assert shape_features(m).linearity < 0.2


def test_rules():
    assert classify(0.95, 3.0) == "Contrail, attributed"
    assert classify(0.95, None) == "Contrail, unattributed"
    assert classify(0.4, 3.0) == "Natural cirrus"
