"""Causal public context for explicitly executed, trusted local Python scripts."""
from __future__ import annotations

import json
import math
import random
from bisect import bisect_right
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType

from .indicators import evaluate
from .models import IndicatorInstance, IndicatorRequest, StrategyDefinition
from .research_models import OrderRequest
from .scripts import analyze_script, validate_parameters
from .simulation import Simulation


@dataclass(frozen=True)
class HistoricalBar:
    start: int
    end: int
    open: float
    high: float
    low: float
    close: float
    volume: float | None
    source: str
    feed: str
    adjustment: str
    complete: bool = True

    @classmethod
    def from_bar(cls, bar):
        return cls(**bar.model_dump(exclude={'schema_version'}))


class Context:
    """Snapshots returned here cannot mutate the engine. This is not a security sandbox."""
    def __init__(self, simulation: Simulation, parameters: dict, subscriptions: list[str] | None = None):
        self._simulation = simulation
        self._indicators = {}
        self.parameters = MappingProxyType(dict(parameters))
        self.subscriptions = tuple(subscriptions or sorted(simulation.views))
        if set(self.subscriptions)-set(simulation.views):
            raise ValueError('Script subscriptions must belong to the selected dataset universe')
        self.random = random.Random(simulation.settings.seed)
        self.state = {}
        self.logs = []
        self.plots = []
        self.dropped_logs = 0
        self.dropped_plots = 0

    @property
    def clock(self):
        return datetime.fromtimestamp(self._simulation.clock, UTC)

    @property
    def timestamp(self):
        return self._simulation.clock

    @property
    def instruments(self):
        return MappingProxyType({key: view.dataset.instrument.model_copy(deep=True)
                                 for key, view in self._simulation.views.items()})

    @property
    def portfolio(self):
        return self._simulation.portfolio()

    @property
    def orders(self):
        return tuple(order.model_copy(deep=True) for order in self._simulation.orders)

    @property
    def fills(self):
        return tuple(fill.model_copy(deep=True) for fill in self._simulation.fills)

    def history(self, instrument_id: str, count: int | None = None):
        if instrument_id not in self._simulation.history:
            raise ValueError('Instrument is outside the selected universe')
        if count is not None and (not isinstance(count, int) or isinstance(count, bool) or count < 1):
            raise ValueError('History count must be a positive integer')
        values = self._simulation.history[instrument_id]
        return tuple(HistoricalBar.from_bar(bar) for bar in (values[-count:] if count else values))

    def indicator(self, instrument_id: str, definition_id: str, parameters: dict | None = None,
                  count: int | None = None):
        """Source-index values only. Ichimoku display shifts never affect availability.

        Shared built-ins are prefix-causal (tested independently). Cache their full
        immutable input calculation once, exposing only source values completed now.
        Custom Python indicators instead execute once per causal completion event.
        """
        if instrument_id not in self._simulation.views:
            raise ValueError('Instrument is outside the selected universe')
        if count is not None and (not isinstance(count, int) or isinstance(count, bool) or count < 1):
            raise ValueError('Indicator count must be a positive integer')
        key = (instrument_id, definition_id, json.dumps(parameters or {}, sort_keys=True, allow_nan=False))
        if key not in self._indicators:
            view = self._simulation.views[instrument_id]
            response = evaluate(IndicatorRequest(dataset_id=view.dataset.id, instances=[IndicatorInstance(
                id='sdk', definition_id=definition_id, parameters=parameters or {})]), view.dataset, view.bars)
            result = response.results[0]
            if result.status != 'ready':
                raise ValueError(result.message)
            self._indicators[key] = response
        response = self._indicators[key]
        end = bisect_right(response.available_at, self.timestamp)
        start = max(0, end-count) if count else 0
        return MappingProxyType({line.output_id: tuple(line.values[start:end]) for line in response.results[0].lines})

    def order(self, instrument_id: str, side: str, quantity, **settings):
        return self._simulation.submit(OrderRequest(instrument_id=instrument_id, side=side, quantity=quantity, **settings))

    def cancel(self, order_id: str):
        return self._simulation.cancel(order_id)

    def log(self, *values):
        if len(self.logs) >= 5000:
            self.dropped_logs += 1
            return
        text = ' '.join(str(value) for value in values)
        self.logs.append({'time': self.timestamp, 'message': text[:4000], 'truncated': len(text) > 4000})

    def plot(self, name: str, value: float | None, instrument_id: str | None = None):
        if not isinstance(name, str) or not name or len(name) > 120:
            raise ValueError('Plot names must contain 1–120 characters')
        if instrument_id is not None and instrument_id not in self._simulation.views:
            raise ValueError('Plot instrument is outside the selected universe')
        if value is not None:
            value = float(value)
            if not math.isfinite(value):
                raise ValueError('Plot values must be finite or None')
        if len(self.plots) >= 100000:
            self.dropped_plots += 1
            return
        self.plots.append({'time': self.timestamp, 'name': name, 'value': value, 'instrument_id': instrument_id})


class ScriptRuntime:
    """Instantiate only in an explicitly launched research worker (or a dedicated test)."""
    def __init__(self, simulation: Simulation, script: StrategyDefinition, parameters: dict | None = None):
        analysis = analyze_script(script)
        if not analysis.valid:
            raise ValueError('; '.join(d.message for d in analysis.diagnostics if d.severity == 'error'))
        self.ctx = Context(simulation, validate_parameters(analysis.parameters, parameters if parameters is not None else script.parameters), script.subscriptions)
        self.simulation, self.script = simulation, script
        self.namespace = {'__name__': '__workbench_script__', '__file__': 'strategy.py'}
        exec(compile(script.source, 'strategy.py', 'exec'), self.namespace)  # noqa: S102 -- explicit trusted-code runner
        required = 'on_bars' if script.kind == 'strategy' else 'calculate'
        if not callable(self.namespace.get(required)):
            raise TypeError(f'{required} is not callable after loading the script')
        for name in ('initialize', 'finalize'):
            if name in self.namespace and not callable(self.namespace[name]):
                raise ValueError(f'{name} must be a function')
        if 'initialize' in self.namespace:
            self.namespace['initialize'](self.ctx)

    def on_bars(self, bars):
        batch = {key: HistoricalBar.from_bar(bar) for key, bar in bars.items() if key in self.ctx.subscriptions}
        if not batch:
            return
        if self.script.kind == 'strategy':
            self.namespace['on_bars'](self.ctx, MappingProxyType(batch))
        else:
            values = self.namespace['calculate'](self.ctx)
            if not isinstance(values, dict):
                raise ValueError('calculate(ctx) must return a dictionary of named scalar outputs')
            for name, value in values.items():
                self.ctx.plot(name, value)

    def finish(self):
        if 'finalize' in self.namespace:
            self.namespace['finalize'](self.ctx)
        if self.ctx.dropped_logs or self.ctx.dropped_plots:
            self.ctx.logs.append({'time': self.ctx.timestamp, 'message':
                f'Output limits reached: {self.ctx.dropped_logs} log lines and {self.ctx.dropped_plots} plot points omitted.', 'truncated': True})
