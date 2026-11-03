"""Tests for geo_anom.task1.finetune (CPU, synthetic data, no downloads)."""

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import box

torch = pytest.importorskip("torch")

from geo_anom.task1 import finetune as F  # noqa: E402

UTM = "EPSG:32618"


def test_loss_ignores_255():
    logits = torch.zeros(1, 2, 4, 4, requires_grad=True)
    y = torch.full((1, 4, 4), 255, dtype=torch.long)
    y[0, 0, 0] = 1
    a = F.loss_fn(logits, y)
    y2 = y.clone(); y2[0, 3, 3] = 255          # changing ignored pixels changes nothing
    assert torch.isclose(a, F.loss_fn(logits, y2))
    a.backward()
    assert logits.grad is not None


def test_pixel_scores_counts_house_class_only():
    class M(torch.nn.Module):
        def forward(self, x):                  # predicts "house" on the left half
            out = torch.zeros(x.shape[0], 2, 4, 4)
            out[:, 1, :, :2] = 1
            return out
    y = torch.zeros(1, 4, 4, dtype=torch.long)
    y[0, :, 0] = 1                              # house in column 0
    y[0, :, 3] = 255                            # ignored column
    s = F.pixel_scores(M(), [(torch.zeros(1, 4, 4, 4), y)], torch.device("cpu"))
    assert s["recall"] == 1.0 and s["precision"] == 0.5


def test_score_area_uses_review_labels():
    gt = gpd.GeoDataFrame(geometry=[box(0, 0, 150, 15), box(0, 100, 150, 115)], crs=UTM)
    det = gpd.GeoDataFrame(geometry=[box(2, 1, 148, 14),          # on a traced house
                                     box(0, 300, 150, 315),       # 07-confirmed new house
                                     box(0, 500, 80, 540),        # 07-rejected
                                     box(0, 700, 150, 715)], crs=UTM)  # unchecked
    conf = gpd.GeoDataFrame(geometry=[box(1, 301, 149, 314)], crs=UTM)
    rej = gpd.GeoDataFrame(geometry=[box(0, 500, 80, 540)], crs=UTM)
    s = F.score_area(det, gt, box(-1000, -1000, 1000, 1000), conf, rej)
    assert (s["found"], s["real"], s["wrong"], s["unchecked"]) == (1, 2, 1, 1)
    assert s["recall"] == 0.5 and s["precision_low"] == 0.5 and s["precision_high"] == 0.75


def test_train_one_epoch_writes_loadable_checkpoint(tmp_path):
    import segmentation_models_pytorch as smp
    from geo_anom.task1 import detect
    model = smp.Unet(encoder_name="resnet18", encoder_depth=3, encoder_weights=None,
                     decoder_channels=(128, 64, 64), in_channels=4, classes=2)
    rng = np.random.default_rng(0)
    x = torch.from_numpy(rng.random((4, 4, 64, 64), dtype=np.float32))
    y = torch.zeros(4, 64, 64, dtype=torch.long); y[:, 20:30, 5:60] = 1
    batches = [(x[:2], y[:2]), (x[2:], y[2:])]
    hist = F.train(model, torch.device("cpu"), batches, batches, tmp_path, epochs=2, lr=1e-2, encoder_lr=1e-2, log=lambda *_: None)
    assert list(hist.epoch) == [0, 1, 2]
    assert (tmp_path / "last.pt").exists()
    if (tmp_path / "best.pt").exists():
        m, _ = detect.load_model(tmp_path / "best.pt", device=torch.device("cpu"))
        assert m is not None
