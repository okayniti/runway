"""
Train the Bi-LSTM cash-flow forecaster and evaluate it on a held-out,
chronologically split test set.

The data is split into three chronological chunks — train / validation /
test, in that time order — not shuffled: the earliest windows are used for
training, the next chunk for validation during training, and the most
recent windows are held out as the final test set. Shuffling would let the
model train on windows that overlap in time with its own test set
(leakage). The validation split exists purely to print a train-vs-val loss
curve during training so overfitting/underfitting is visible as it
happens, separate from the final test-set evaluation.

Usage:
    python model/train.py --data-csv data/synthetic_transactions.csv
"""

from __future__ import annotations

import argparse
import copy
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

try:
    from .dataset import FEATURE_COLUMNS, build_daily_features, build_windows
    from .model import BiLSTMForecaster
except ImportError:  # running as `python model/train.py`, not `-m model.train`
    from dataset import FEATURE_COLUMNS, build_daily_features, build_windows
    from model import BiLSTMForecaster


def set_seed(seed: int) -> None:
    """Seed numpy and torch so a training run is reproducible end to end."""
    np.random.seed(seed)
    torch.manual_seed(seed)


def chronological_split(
    X: np.ndarray, y: np.ndarray, holdout_fraction: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Split windows by time, not randomly: the earliest `1 - holdout_fraction`
    of windows become the first split, the most recent `holdout_fraction`
    become the second. Used twice by main() to carve train/val/test out of
    one chronologically ordered array.

    Returns (X_first, y_first, X_second, y_second).
    """
    split_idx = int(len(X) * (1 - holdout_fraction))
    if split_idx <= 0 or split_idx >= len(X):
        raise ValueError(
            f"holdout_fraction={holdout_fraction} leaves no samples in one "
            f"of the two splits (total samples={len(X)}). Generate more "
            "data or adjust the split."
        )
    return X[:split_idx], y[:split_idx], X[split_idx:], y[split_idx:]


def fit_mean_std(array: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Fit per-feature (or per-horizon-step) mean/std, keeping the last axis."""
    reduce_axes = tuple(range(array.ndim - 1))
    mean = array.mean(axis=reduce_axes, keepdims=True)
    std = array.std(axis=reduce_axes, keepdims=True)
    std = np.where(std == 0, 1.0, std)
    return mean.astype(np.float32), std.astype(np.float32)


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    """Compute RMSE, MAE, and R2 over all predicted values, flattened across
    samples and horizon steps into one pooled set of errors."""
    y_true_flat = y_true.reshape(-1)
    y_pred_flat = y_pred.reshape(-1)
    errors = y_pred_flat - y_true_flat

    rmse = float(np.sqrt(np.mean(errors**2)))
    mae = float(np.mean(np.abs(errors)))

    ss_res = float(np.sum(errors**2))
    ss_tot = float(np.sum((y_true_flat - y_true_flat.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    return {"rmse": rmse, "mae": mae, "r2": r2}


def diagnose_loss_curve(losses: list[float]) -> str:
    """Compare the average loss over the first and last 20% of epochs to
    give a plain-language read on the training curve, since eyeballing a
    long printed list is easy to get wrong."""
    n = len(losses)
    chunk = max(1, n // 5)
    early = float(np.mean(losses[:chunk]))
    late = float(np.mean(losses[-chunk:]))
    if early == 0:
        return "flat (zero loss throughout -- check for a bug)"
    relative_change = (late - early) / early
    if relative_change < -0.10:
        return f"decreasing ({early:.4f} -> {late:.4f}, {relative_change:+.1%})"
    if relative_change > 0.10:
        return f"DIVERGING ({early:.4f} -> {late:.4f}, {relative_change:+.1%})"
    return f"flat ({early:.4f} -> {late:.4f}, {relative_change:+.1%})"


def print_sample_predictions(y_test: np.ndarray, preds: np.ndarray, num_samples: int = 5) -> None:
    """Print predicted vs. actual for a spread of real test samples, so a
    human can sanity-check whether predictions are even in the right range
    — not just whether the aggregate metrics look reasonable."""
    horizon = y_test.shape[1]
    indices = np.linspace(0, len(y_test) - 1, num=min(num_samples, len(y_test)), dtype=int)
    print(f"\nSample predictions vs. actual (change in cash position over the {horizon}-day horizon, original units):")
    print(f"  {'test idx':>8}  {'day 1 pred':>14}  {'day 1 actual':>14}  {'day ' + str(horizon) + ' pred':>14}  {'day ' + str(horizon) + ' actual':>14}")
    for idx in indices:
        print(
            f"  {idx:8d}  {preds[idx, 0]:14,.2f}  {y_test[idx, 0]:14,.2f}  "
            f"{preds[idx, -1]:14,.2f}  {y_test[idx, -1]:14,.2f}"
        )


def main() -> None:
    """CLI entry point: load data, train with a validation split, evaluate
    on the held-out test split, print RMSE/MAE/R2 plus diagnostics (loss
    curve, sample predictions), and save a checkpoint. See module
    docstring for usage."""
    import sys as _sys

    # Same fix as agent/wrapper.py's CLI entry point: force UTF-8 stdout so
    # redirected output can't fall back to a codepage that mangles any
    # non-ASCII character a future print statement here might introduce.
    if hasattr(_sys.stdout, "reconfigure"):
        _sys.stdout.reconfigure(encoding="utf-8")

    project_root = Path(__file__).resolve().parent.parent

    parser = argparse.ArgumentParser(description="Train the Bi-LSTM cash-flow forecaster.")
    parser.add_argument(
        "--data-csv", default=str(project_root / "data" / "synthetic_transactions.csv")
    )
    parser.add_argument("--lookback", type=int, default=30, help="Days of history per input window.")
    parser.add_argument("--horizon", type=int, default=14, help="Days ahead to forecast.")
    parser.add_argument("--test-fraction", type=float, default=0.2)
    parser.add_argument(
        "--val-fraction",
        type=float,
        default=0.15,
        help="Fraction of the remaining (non-test) windows held out for validation during training.",
    )
    parser.add_argument(
        "--hidden-size",
        type=int,
        default=16,
        help="LSTM hidden size per direction. Kept small relative to the recommended "
        "~1000-day synthetic dataset size (a few hundred train windows) to avoid "
        "overfitting -- 4,350 params at the default vs. 147,406 at hidden_size=64/"
        "num_layers=2, which drove test R2 to -11.4 (see project history).",
    )
    parser.add_argument("--num-layers", type=int, default=1)
    parser.add_argument("--dropout", type=float, default=0.3)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--epochs", type=int, default=150)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument(
        "--weight-decay",
        type=float,
        default=1e-3,
        help="L2 regularization on the optimizer, to further guard against overfitting.",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--checkpoint-dir", default=str(Path(__file__).resolve().parent / "checkpoints")
    )
    args = parser.parse_args()

    set_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    transactions = pd.read_csv(args.data_csv)
    daily = build_daily_features(transactions)
    X, y = build_windows(daily, args.lookback, args.horizon)

    X_trainval, y_trainval, X_test, y_test = chronological_split(X, y, args.test_fraction)
    X_train, y_train, X_val, y_val = chronological_split(X_trainval, y_trainval, args.val_fraction)
    print(f"train windows: {len(X_train)}  val windows: {len(X_val)}  test windows: {len(X_test)}")

    x_mean, x_std = fit_mean_std(X_train)
    y_mean, y_std = fit_mean_std(y_train)

    X_train_norm = ((X_train - x_mean) / x_std).astype(np.float32)
    X_val_norm = ((X_val - x_mean) / x_std).astype(np.float32)
    X_test_norm = ((X_test - x_mean) / x_std).astype(np.float32)
    y_train_norm = ((y_train - y_mean) / y_std).astype(np.float32)
    y_val_norm = ((y_val - y_mean) / y_std).astype(np.float32)

    train_dataset = TensorDataset(torch.from_numpy(X_train_norm), torch.from_numpy(y_train_norm))
    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True)
    X_val_tensor = torch.from_numpy(X_val_norm).to(device)
    y_val_tensor = torch.from_numpy(y_val_norm).to(device)

    model = BiLSTMForecaster(
        input_size=X.shape[-1],
        horizon=args.horizon,
        hidden_size=args.hidden_size,
        num_layers=args.num_layers,
        dropout=args.dropout,
    ).to(device)
    num_params = sum(p.numel() for p in model.parameters())
    print(f"model parameters: {num_params:,}  (train windows: {len(X_train)})")

    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)

    train_losses: list[float] = []
    val_losses: list[float] = []
    best_val_loss = float("inf")
    best_epoch = 0
    best_state_dict = copy.deepcopy(model.state_dict())

    for epoch in range(1, args.epochs + 1):
        model.train()
        epoch_loss = 0.0
        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            optimizer.zero_grad()
            preds = model(xb)
            loss = criterion(preds, yb)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item() * xb.size(0)
        epoch_loss /= len(train_dataset)
        train_losses.append(epoch_loss)

        model.eval()
        with torch.no_grad():
            val_loss = criterion(model(X_val_tensor), y_val_tensor).item()
        val_losses.append(val_loss)

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_epoch = epoch
            best_state_dict = copy.deepcopy(model.state_dict())

        if epoch == 1 or epoch % 10 == 0 or epoch == args.epochs:
            print(f"epoch {epoch:4d}/{args.epochs}  train_mse={epoch_loss:.4f}  val_mse={val_loss:.4f}")

    print(f"\nTrain loss curve: {diagnose_loss_curve(train_losses)}")
    print(f"Val loss curve:   {diagnose_loss_curve(val_losses)}")
    print(
        f"Best val_mse={best_val_loss:.4f} at epoch {best_epoch}/{args.epochs} "
        f"(final epoch val_mse={val_losses[-1]:.4f}) -- using best-epoch weights for "
        "test evaluation and the saved checkpoint, not the final epoch's, since the "
        "val curve above shows overfitting past that point."
    )
    model.load_state_dict(best_state_dict)

    model.eval()
    with torch.no_grad():
        preds_norm = model(torch.from_numpy(X_test_norm).to(device)).cpu().numpy()
    preds = preds_norm * y_std + y_mean

    metrics = compute_metrics(y_test, preds)
    print("\nHeld-out test metrics (change in cash position over the horizon, original units):")
    print(f"  RMSE: {metrics['rmse']:.2f}")
    print(f"  MAE:  {metrics['mae']:.2f}")
    print(f"  R2:   {metrics['r2']:.4f}")

    print_sample_predictions(y_test, preds)

    checkpoint_dir = Path(args.checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = checkpoint_dir / "bilstm_cashflow.pt"

    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "config": {
                "input_size": X.shape[-1],
                "horizon": args.horizon,
                "lookback": args.lookback,
                "hidden_size": args.hidden_size,
                "num_layers": args.num_layers,
                "dropout": args.dropout,
                "feature_columns": FEATURE_COLUMNS,
            },
            "x_mean": x_mean,
            "x_std": x_std,
            "y_mean": y_mean,
            "y_std": y_std,
            "test_metrics": metrics,
        },
        checkpoint_path,
    )
    print(f"\nSaved checkpoint to {checkpoint_path}")


if __name__ == "__main__":
    main()
