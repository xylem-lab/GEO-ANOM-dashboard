"""
Fine-tune the poultry-house U-Net on notebook 09's training data (notebook 10).

Same architecture and input as the published model (detect.load_model: resnet18 U-Net,
4 bands scaled to [0, 1], 2 classes), starting from its weights, so the result drops into
the existing pipeline unchanged (run_pipeline(checkpoint=...)).

    loaders(...)       random augmented crops for training (2023 drawn more often),
                       fixed centre crops for validation
    train(...)         AdamW, cross-entropy + Dice on the house class, pixels marked 255
                       ignored; scores validation every epoch (epoch 0 = the published model),
                       keeps the best epoch by validation F1; resumable from last.pt
    pixel_scores(...)  house-pixel precision / recall / F1 / IoU, ignoring 255
    score_area(...)    the real test: houses found and detections confirmed, on whole
                       held-out counties, the same way notebook 05 scores
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from geo_anom.task1 import training as T

IGNORE = T.IGNORE


# ── data ───────────────────────────────────────────────────────────────────────

def loaders(data_dir: Path, plan: pd.DataFrame, batch_size: int = 16, samples_per_epoch: int = 4000,
            year_weight: dict | None = None, kind_weight: dict | None = None, workers: int = 2, seed: int = 0):
    """(train_loader, val_loader). Training draws `samples_per_epoch` crops with replacement,
    windows weighted by year and kind (default: 2023 twice as often -- it's the photo
    the model has to work on)."""
    import torch
    from torch.utils.data import DataLoader, WeightedRandomSampler

    year_weight = year_weight or {"2023": 2.0}
    kind_weight = kind_weight or {}
    tr = T.ChipDataset(data_dir, plan, "train", train=True, cache=False)
    va = T.ChipDataset(data_dir, plan, "val", train=False, cache=False)
    if not len(tr) or not len(va):
        raise ValueError(f"no training data found under {data_dir} (train {len(tr)}, val {len(va)}) -- run notebook 09")
    by_path = {str(T._paths(data_dir, r)[0]): r for _, r in plan.iterrows()}
    w = []
    for ip, _ in tr.items:
        r = by_path[str(ip)]
        w.append(year_weight.get(str(r["year"]), 1.0) * kind_weight.get(r["kind"], 1.0))
    g = torch.Generator().manual_seed(seed)
    sampler = WeightedRandomSampler(torch.tensor(w, dtype=torch.double), samples_per_epoch, replacement=True, generator=g)
    kw = dict(num_workers=workers, pin_memory=torch.cuda.is_available(), persistent_workers=workers > 0)
    return (DataLoader(tr, batch_size=batch_size, sampler=sampler, drop_last=True, **kw),
            DataLoader(va, batch_size=batch_size, shuffle=False, **kw))


# ── loss and scores ────────────────────────────────────────────────────────────

def loss_fn(logits, target, house_weight: float = 2.0, dice_weight: float = 0.5):
    """Cross-entropy (house pixels weighted up) + soft Dice on the house class; 255 ignored."""
    import torch
    import torch.nn.functional as F

    w = torch.tensor([1.0, house_weight], device=logits.device)
    ce = F.cross_entropy(logits, target, weight=w, ignore_index=IGNORE)
    valid = (target != IGNORE).float()
    p = F.softmax(logits, dim=1)[:, 1] * valid
    t = (target == 1).float() * valid
    inter = (p * t).sum()
    dice = 1 - (2 * inter + 1) / (p.sum() + t.sum() + 1)
    return ce + dice_weight * dice


def pixel_scores(model, loader, device) -> dict:
    """House-class pixel precision / recall / F1 / IoU over a loader (argmax, 255 ignored)."""
    import torch

    tp = fp = fn = 0
    model.eval()
    with torch.no_grad():
        for x, y in loader:
            pred = model(x.to(device)).argmax(1).cpu()
            v = y != IGNORE
            tp += int(((pred == 1) & (y == 1) & v).sum())
            fp += int(((pred == 1) & (y == 0) & v).sum())
            fn += int(((pred == 0) & (y == 1) & v).sum())
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": p, "recall": r, "f1": 2 * p * r / (p + r) if p + r else 0.0,
            "iou": tp / (tp + fp + fn) if tp + fp + fn else 0.0}


# ── training ───────────────────────────────────────────────────────────────────

def train(model, device, train_loader, val_loader, out_dir: Path, epochs: int = 15,
          lr: float = 3e-4, encoder_lr: float = 1e-4, weight_decay: float = 1e-4, log=print,
          meta: dict | None = None) -> pd.DataFrame:
    """Fine-tune in place. Writes out_dir/best.pt (Robinson's checkpoint format, so
    detect.load_model reads it), last.pt (to resume), history.csv. Returns the history."""
    import torch

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    enc = [p for n, p in model.named_parameters() if n.startswith("encoder.")]
    rest = [p for n, p in model.named_parameters() if not n.startswith("encoder.")]
    opt = torch.optim.AdamW([{"params": enc, "lr": encoder_lr}, {"params": rest, "lr": lr}], weight_decay=weight_decay)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=max(epochs, 1))
    use_amp = device.type == "cuda"
    scaler = (torch.amp.GradScaler("cuda", enabled=use_amp) if hasattr(torch, "amp") and hasattr(torch.amp, "GradScaler")
              else torch.cuda.amp.GradScaler(enabled=use_amp))

    hist_path, last = out_dir / "history.csv", out_dir / "last.pt"
    hist = pd.read_csv(hist_path).to_dict("records") if hist_path.exists() else []
    start = 1
    if last.exists():
        st = torch.load(last, map_location="cpu")
        model.load_state_dict(st["model_checkpoint"]); opt.load_state_dict(st["optimizer"])
        sched.load_state_dict(st["scheduler"]); start = st["epoch"] + 1
        log(f"resuming after epoch {st['epoch']}")
    if not hist:
        s = pixel_scores(model, val_loader, device)
        hist.append({"epoch": 0, "train_loss": None, **{f"val_{k}": v for k, v in s.items()}, "seconds": 0})
        log(f"epoch 0 (published model): val F1 {s['f1']:.3f}  P {s['precision']:.3f}  R {s['recall']:.3f}")
        pd.DataFrame(hist).to_csv(hist_path, index=False)
    best = max(h["val_f1"] for h in hist)

    for ep in range(start, epochs + 1):
        t0, losses = time.time(), []
        model.train()
        for x, y in train_loader:
            x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
            opt.zero_grad(set_to_none=True)
            with torch.autocast(device_type="cuda", enabled=use_amp):
                loss = loss_fn(model(x), y)
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            losses.append(float(loss.detach()))
        sched.step()
        s = pixel_scores(model, val_loader, device)
        rec = {"epoch": ep, "train_loss": float(np.mean(losses)), **{f"val_{k}": v for k, v in s.items()},
               "seconds": round(time.time() - t0)}
        hist.append(rec)
        pd.DataFrame(hist).to_csv(hist_path, index=False)
        mark = ""
        if s["f1"] > best:
            best = s["f1"]
            torch.save({"model_checkpoint": model.state_dict(), "epoch": ep, "val": s, **(meta or {})}, out_dir / "best.pt")
            mark = "  <- best"
        torch.save({"model_checkpoint": model.state_dict(), "optimizer": opt.state_dict(),
                    "scheduler": sched.state_dict(), "epoch": ep}, last)
        log(f"epoch {ep}: loss {rec['train_loss']:.3f}  val F1 {s['f1']:.3f}  P {s['precision']:.3f}  "
            f"R {s['recall']:.3f}  ({rec['seconds']} s){mark}")
    if not (out_dir / "best.pt").exists():
        log("no epoch beat the published model on validation -- best.pt not written")
    return pd.DataFrame(hist)


# ── the real test: whole held-out counties ─────────────────────────────────────

def score_area(det, gt, area, confirmed=None, rejected=None) -> dict:
    """Score detections the way notebook 05 does, plus notebook 07's labels.

    found      traced houses (centre inside `area`) touched by a detection
    real       detections touching a traced house or a 07-confirmed house
    wrong      detections touching a 07-rejected detection and no house
    unchecked  the rest (new to this model, or never shown in 07)
    precision is given as a range: unchecked counted as wrong (low) / right (high)."""
    import geopandas as gpd

    g = gt[gt.centroid.within(area)]
    d = det[det.centroid.within(area)].reset_index(drop=True) if len(det) else det
    n = len(d)
    if not n:
        return {"traced": len(g), "detections": 0, "found": 0, "recall": 0.0, "real": 0, "wrong": 0,
                "unchecked": 0, "precision_low": None, "precision_high": None}
    hit = gpd.sjoin(d[["geometry"]], g[["geometry"]], predicate="intersects")
    real = set(hit.index)
    if confirmed is not None and len(confirmed):
        real |= set(gpd.sjoin(d[["geometry"]], confirmed[["geometry"]], predicate="intersects").index)
    wrong = set()
    if rejected is not None and len(rejected):
        wrong = set(gpd.sjoin(d[["geometry"]], rejected[["geometry"]], predicate="intersects").index) - real
    unchecked = n - len(real) - len(wrong)
    return {"traced": len(g), "detections": n, "found": hit.index_right.nunique(),
            "recall": hit.index_right.nunique() / len(g) if len(g) else None,
            "real": len(real), "wrong": len(wrong), "unchecked": unchecked,
            "precision_low": len(real) / n, "precision_high": (len(real) + unchecked) / n,
            "_unchecked_index": sorted(set(range(n)) - real - wrong)}


def save_meta(path: Path, **kw):
    Path(path).write_text(json.dumps(kw, indent=2, default=str))
