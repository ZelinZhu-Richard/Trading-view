"""Deterministic currency routes from completed, explicitly supplied price series."""
from bisect import bisect_right
from collections import deque
from decimal import Decimal, localcontext

from .models import DatasetView
from .money import decimal
from .research_models import FXConversion, FXLeg


class MissingConversion(ValueError):
    pass


class FXBook:
    def __init__(self, datasets: list[DatasetView], max_age: int | None = None):
        self.sources = []
        self.max_age = max_age
        for view in sorted(datasets, key=lambda v: (v.dataset.instrument.id, v.dataset.id)):
            instrument = view.dataset.instrument
            if instrument.base_currency and instrument.asset_class in ('forex', 'crypto'):
                bars = [bar for bar in view.bars if bar.complete]
                self.sources.append((view.dataset, bars, [bar.end for bar in bars]))

    def conversion(self, source: str, target: str, at: int, purpose: str) -> FXConversion:
        if source == target:
            return FXConversion(at=at, from_currency=source, to_currency=target, rate=Decimal(1), purpose=purpose)
        graph = {}
        with localcontext() as context:
            context.prec = 34
            for dataset, bars, times in self.sources:
                index = bisect_right(times, at)-1
                if index < 0:
                    continue
                bar = bars[index]
                if self.max_age is not None and at-bar.end > self.max_age:
                    continue
                base, quote = dataset.instrument.base_currency, dataset.instrument.quote_currency
                for a, b, inverse in ((base, quote, False), (quote, base, True)):
                    leg = FXLeg(from_currency=a, to_currency=b,
                        rate=Decimal(1)/decimal(bar.close) if inverse else decimal(bar.close),
                        instrument_id=dataset.instrument.id, dataset_id=dataset.id, dataset_hash=dataset.hash,
                        source=dataset.source, feed=dataset.feed, available_at=bar.end,
                        age_seconds=at-bar.end, inverse=inverse)
                    graph.setdefault(a, []).append(leg)
            queue = deque([(source, Decimal(1), [])])
            seen = {source}
            while queue:
                currency, rate, legs = queue.popleft()
                for leg in sorted(graph.get(currency, []), key=lambda x: (x.to_currency, x.instrument_id, x.dataset_id)):
                    if leg.to_currency in seen:
                        continue
                    path = [*legs, leg]
                    combined = rate*leg.rate
                    if leg.to_currency == target:
                        return FXConversion(at=at, from_currency=source, to_currency=target,
                            rate=combined, legs=path, purpose=purpose)
                    seen.add(leg.to_currency)
                    queue.append((leg.to_currency, combined, path))
        raise MissingConversion(f'No completed conversion path from {source} to {target} at {at}')
