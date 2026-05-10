from abc import ABC, abstractmethod
from dataclasses import dataclass
import pandas as pd


@dataclass
class StrategySignal:
    fired: bool
    direction: str | None        # "CALL" or "PUT" or None
    points: int                  # Confidence points contributed
    reason: str                  # Human-readable label
    details: dict | None = None  # Extra metadata


class BaseStrategy(ABC):
    name: str = "base"
    max_points: int = 0

    @abstractmethod
    def evaluate(self, candles: pd.DataFrame, oi_data: dict | None = None) -> StrategySignal:
        """
        Evaluate strategy against latest candle data.
        Returns a StrategySignal with fired=True if conditions are met.
        """
        ...
