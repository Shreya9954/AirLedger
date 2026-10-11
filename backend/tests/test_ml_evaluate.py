import numpy as np

from ml.evaluate import evaluate_record, main, regions

H = W = 64


def write_record(folder, contrail_rows=(30, 32), cirrus=True):
    """A tiny OpenContrails-style record: one straight labelled contrail and one blob of cirrus,
    both thin ice (BT11 − BT12 = 2 K), on clear sky (0 K)."""
    folder.mkdir(parents=True)
    line = np.zeros((H, W), bool)
    line[contrail_rows[0]:contrail_rows[1], 4:60] = True
    yy, xx = np.mgrid[:H, :W]
    blob = (yy - 12) ** 2 + (xx - 14) ** 2 < 8 ** 2
    ice = line | (blob if cirrus else False)
    b14 = np.full((H, W), 280.0)
    b15 = b14 - np.where(ice, 2.0, 0.0)
    for n, band in ((11, np.full((H, W), 275.0)), (14, b14), (15, b15)):
        np.save(folder / f"band_{n:02d}.npy", np.repeat(band[..., None], 8, axis=-1))
    for n in (8, 9, 10, 12, 13, 16):
        np.save(folder / f"band_{n:02d}.npy", np.zeros((H, W, 8)))
    np.save(folder / "human_pixel_masks.npy", line[..., None].astype(np.int32))
    return folder


def test_regions_splits_and_drops_small():
    m = np.zeros((10, 10), bool)
    m[0, 0] = True
    m[5:8, 5:8] = True
    assert [r.sum() for r in regions(m, min_px=4)] == [9]


def test_record_scores(tmp_path):
    got = evaluate_record(write_record(tmp_path / "rec1"))
    assert got == {"contrails": 1, "contrails_recognised": 1, "other_ice": 1, "other_ice_called_contrail": 0}


def test_cli_reports(tmp_path, capsys):
    write_record(tmp_path / "data" / "rec1")
    assert main([str(tmp_path / "data")]) == 0
    out = capsys.readouterr().out
    assert "1 of 1 (100%)" in out and "0 of 1 (0%)" in out
