"""Deliberately synthetic, deterministic data for examples and verification."""
import math
import random
from datetime import UTC, datetime, timedelta

from .models import Bar, Instrument
from .store import Store


def example_dataset(store: Store):
    instrument = Instrument(id='EXAMPLE:DEMO', symbol='DEMO', name='Synthetic research example',
                            exchange='EXAMPLE', asset_class='other', quote_currency='USD',
                            timezone='UTC', calendar='24/7', quantity_step='0.001')
    rng = random.Random(42)
    start = datetime(2025, 1, 1, tzinfo=UTC)
    bars = []
    price = 100
    for i in range(365):
        op = price
        price = max(20, op + .06 + math.sin(i / 14) * .42 + rng.gauss(0, .85))
        bars.append(Bar(start=int((start + timedelta(days=i)).timestamp()),
                        end=int((start + timedelta(days=i + 1)).timestamp()),
                        open=round(op, 2), close=round(price, 2),
                        high=round(max(op, price) + rng.uniform(.2, 1.9), 2),
                        low=round(min(op, price) - rng.uniform(.2, 1.9), 2),
                        volume=rng.randint(100_000, 900_000), source='fixture',
                        feed='deterministic-example', adjustment='raw'))
    return store.save_dataset(instrument, '1d', bars,
                              ['Synthetic demonstration data; not a real instrument or live feed.'])
