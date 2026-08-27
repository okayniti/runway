"""
Bi-LSTM regression model for multi-day cash-flow forecasting.

Given the past `lookback` days of daily cash-flow features, predicts the net
cash position for each of the next `horizon` days in a single forward pass
(direct multi-output regression, not autoregressive step-by-step decoding).
"""

from __future__ import annotations

import torch
from torch import nn


class BiLSTMForecaster(nn.Module):
    """Bidirectional LSTM encoder + MLP head for multi-day cash-flow forecasting.

    See the module docstring for the forecasting approach; `forward()` for
    how the encoder's final states are combined into the horizon output.
    """

    def __init__(
        self,
        input_size: int,
        horizon: int,
        hidden_size: int = 64,
        num_layers: int = 2,
        dropout: float = 0.2,
    ) -> None:
        """
        Parameters
        ----------
        input_size : number of features per day (see model.dataset.FEATURE_COLUMNS).
        horizon : number of future days to predict in one forward pass.
        hidden_size : LSTM hidden state size per direction.
        num_layers : number of stacked LSTM layers.
        dropout : applied between stacked LSTM layers (if num_layers > 1) and in the head.
        """
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.head = nn.Sequential(
            nn.Linear(hidden_size * 2, hidden_size),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_size, horizon),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (batch, lookback, input_size) -> (batch, horizon)."""
        _, (h_n, _) = self.lstm(x)
        # h_n: (num_layers * 2, batch, hidden_size). Use the last layer's
        # forward and backward final hidden states — each has seen the full
        # sequence in its own direction — rather than slicing raw LSTM
        # output, which would pair a full-context forward state with a
        # single-timestep backward state.
        forward_last = h_n[-2]
        backward_last = h_n[-1]
        final_state = torch.cat([forward_last, backward_last], dim=1)
        return self.head(final_state)
