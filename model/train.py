"""
Train the Bi-LSTM cash-flow forecaster and evaluate it on a held-out,
chronologically split test set.

The train/test split is by time, not random shuffling: the earliest windows
are used for training and the most recent windows are held out, since
shuffling would let the model train on windows that overlap in time with
its own test set (leakage).

Usage:
    python model/train.py --data-csv data/synthetic_transactions.csv
"""

from __future__ import annotations

import argparse
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
    np.random.seed(seed)
    torch.manual_seed(seed)


def chronological_split(
    X: np.ndarray, y: np.ndarray, test_fraction: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    split_idx = int(len(X) * (1 - test_fraction))
    if split_idx <= 0 or split_idx >= len(X):
        raise ValueError(
            f"test_fraction={test_fraction} leaves no samples in train or "
            f"test split (total samples={len(X)}). Generate more data or "
            "adjust the split."
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
    y_true_flat = y_true.reshape(-1)
    y_pred_flat = y_pred.reshape(-1)
    errors = y_pred_flat - y_true_flat

    rmse = float(np.sqrt(np.mean(errors**2)))
    mae = float(np.mean(np.abs(errors)))

    ss_res = float(np.sum(errors**2))
    ss_tot = float(np.sum((y_true_flat - y_true_flat.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    return {"rmse": rmse, "mae": mae, "r2": r2}


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent

    parser = argparse.ArgumentParser(description="Train the Bi-LSTM cash-flow forecaster.")
    parser.add_argument(
        "--data-csv", default=str(project_root / "data" / "synthetic_transactions.csv")
    )
    parser.add_argument("--lookback", type=int, default=30, help="Days of history per input window.")
    parser.add_argument("--horizon", type=int, default=14, help="Days ahead to forecast.")
    parser.add_argument("--test-fraction", type=float, default=0.2)
    parser.add_argument("--hidden-size", type=int, default=64)
    parser.add_argument("--num-layers", type=int, default=2)
    parser.add_argument("--dropout", type=float, default=0.2)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--epochs", type=int, default=150)
    parser.add_argument("--lr", type=float, default=1e-3)
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

    X_train, y_train, X_test, y_test = chronological_split(X, y, args.test_fraction)
    print(f"train windows: {len(X_train)}  test windows: {len(X_test)}")

    x_mean, x_std = fit_mean_std(X_train)
    y_mean, y_std = fit_mean_std(y_train)

    X_train_norm = ((X_train - x_mean) / x_std).astype(np.float32)
    X_test_norm = ((X_test - x_mean) / x_std).astype(np.float32)
    y_train_norm = ((y_train - y_mean) / y_std).astype(np.float32)

    train_dataset = TensorDataset(torch.from_numpy(X_train_norm), torch.from_numpy(y_train_norm))
    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True)

    model = BiLSTMForecaster(
        input_size=X.shape[-1],
        horizon=args.horizon,
        hidden_size=args.hidden_size,
        num_layers=args.num_layers,
        dropout=args.dropout,
    ).to(device)

    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    model.train()
    for epoch in range(1, args.epochs + 1):
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

        if epoch == 1 or epoch % 10 == 0 or epoch == args.epochs:
            print(f"epoch {epoch:4d}/{args.epochs}  train_mse={epoch_loss:.4f}")

    model.eval()
    with torch.no_grad():
        preds_norm = model(torch.from_numpy(X_test_norm).to(device)).cpu().numpy()
    preds = preds_norm * y_std + y_mean

    metrics = compute_metrics(y_test, preds)
    print("\nHeld-out test metrics (original cash-position units):")
    print(f"  RMSE: {metrics['rmse']:.2f}")
    print(f"  MAE:  {metrics['mae']:.2f}")
    print(f"  R2:   {metrics['r2']:.4f}")

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
