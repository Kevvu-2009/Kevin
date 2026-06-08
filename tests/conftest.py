import pandas as pd
import pytest

from quantbot.data.synthetic import generate_ohlcv


@pytest.fixture(scope="session")
def ohlcv() -> pd.DataFrame:
    return generate_ohlcv(n=2500, timeframe="4h", seed=3)


@pytest.fixture(scope="session")
def small_ohlcv() -> pd.DataFrame:
    return generate_ohlcv(n=600, timeframe="1h", seed=5)
