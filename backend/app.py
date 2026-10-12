from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .account_routes import routes as account_routes
from .accounts import AccountService
from .alerts import AlertService
from .candle_routes import routes as candle_routes
from .candles import CandleService
from .fixtures import example_dataset
from .indicators import evaluate, registry
from .models import (
    AlertDefinition,
    AlertEvent,
    AlertServiceStatus,
    Dataset,
    DatasetView,
    DrawingMeasurementRequest,
    ImportPreview,
    ImportRequest,
    IndicatorDefinition,
    IndicatorRequest,
    IndicatorResponse,
    Instrument,
    Interval,
    ScriptAnalysis,
    StrategyDefinition,
    Workspace,
)
from .money import position_measurement
from .normalization import aggregate, parse_import
from .providers import HistoryRequest, ProviderConfig, ProviderError, ProviderID, ProviderManager
from .research import ResearchService
from .research_routes import routes as research_routes
from .scripts import analyze_script
from .store import ConflictError, Store
from .streams import QuoteHub
from .workspace_routes import routes as workspace_routes

APP_ROOT = Path(__file__).resolve().parent.parent
ORIGINS = {'http://127.0.0.1:8000', 'http://localhost:8000',
           'http://127.0.0.1:5173', 'http://localhost:5173'}


class CommitImport(BaseModel):
    token: str


def create_app(data_root: Path | None = None):
    store = Store(data_root or APP_ROOT / 'data')
    providers = ProviderManager(store)
    quotes = QuoteHub(providers)
    alerts = AlertService(store)
    research = ResearchService(store)
    accounts = AccountService(store)
    candles = CandleService(store, providers)
    previews: dict[str, tuple] = {}

    @asynccontextmanager
    async def lifespan(app):
        candles.start()
        alerts.start()
        accounts.start()
        yield
        await research.close()
        await accounts.close()
        await alerts.close()
        await quotes.close()
        await candles.close()
        await providers.close()
        previews.clear()

    app = FastAPI(title='Market Workbench', version='0.1.0', lifespan=lifespan)
    app.state.store = store
    app.state.providers = providers
    app.state.alerts = alerts
    app.state.research = research
    app.include_router(workspace_routes(store))
    app.include_router(research_routes(research, ORIGINS))
    app.include_router(account_routes(accounts))
    app.state.accounts = accounts
    app.state.candles = candles
    app.include_router(candle_routes(candles, ORIGINS))
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])
    app.add_middleware(CORSMiddleware, allow_origins=sorted(ORIGINS), allow_methods=['GET', 'POST', 'PUT', 'DELETE'],
                       allow_headers=['Content-Type', 'X-Workbench-Request'])

    @app.middleware('http')
    async def origin_guard(request: Request, call_next):
        origin = request.headers.get('origin')
        if origin and origin not in ORIGINS:
            return JSONResponse({'detail': 'Browser origin is not allowed'}, status_code=403)
        if request.method in ('POST', 'PUT', 'DELETE') and request.headers.get('x-workbench-request') != '1':
            return JSONResponse({'detail': 'Use the Market Workbench application to submit changes'}, status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @app.exception_handler(ConflictError)
    async def conflict_handler(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=409)

    @app.exception_handler(ProviderError)
    async def provider_error_handler(request, exc):
        return JSONResponse({'detail': str(exc), 'provider': exc.provider, 'code': exc.code}, status_code=502)

    @app.exception_handler(ValueError)
    async def invalid_handler(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=422)

    @app.exception_handler(KeyError)
    async def missing_handler(request, exc):
        return JSONResponse({'detail': str(exc.args[0])}, status_code=404)

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'schema_version': 1, 'version': '0.1.0', 'mode': 'local'}

    @app.get('/api/alerts', response_model=list[AlertDefinition])
    def list_alerts():
        return alerts.definitions()

    @app.get('/api/scripts', response_model=list[StrategyDefinition])
    def list_scripts():
        return store.list_documents('script')

    @app.post('/api/scripts/analyze', response_model=ScriptAnalysis)
    def script_diagnostics(value: StrategyDefinition):
        return analyze_script(value)

    @app.get('/api/scripts/{identifier}/versions', response_model=list[StrategyDefinition])
    def script_versions(identifier: str):
        return store.document_versions('script', identifier)

    @app.put('/api/scripts/{identifier}', response_model=StrategyDefinition)
    def save_script(identifier: str, value: StrategyDefinition):
        if value.id != identifier:
            raise ValueError('Script identity does not match its destination')
        return store.save_document('script', identifier, value.model_dump(mode='json'), value.revision)

    @app.delete('/api/scripts/{identifier}')
    def delete_script(identifier: str):
        with store.connect() as db:
            db.execute("DELETE FROM documents WHERE kind='script' AND id=?", (identifier,))
        return {'status': 'deleted', 'versions_retained': True}

    @app.put('/api/alerts/{identifier}', response_model=AlertDefinition)
    def save_alert(identifier: str, value: AlertDefinition):
        if identifier != value.id:
            raise ValueError('Alert identity does not match its destination')
        return alerts.save(value)

    @app.delete('/api/alerts/{identifier}')
    def delete_alert(identifier: str):
        alerts.delete(identifier)
        return {'status': 'deleted'}

    @app.get('/api/alert-events', response_model=list[AlertEvent])
    def alert_events():
        return alerts.events()

    @app.get('/api/alert-status', response_model=AlertServiceStatus)
    def alert_status():
        return alerts.status()

    @app.get('/api/providers')
    def provider_status():
        return providers.capabilities()

    @app.put('/api/providers/{provider}/config')
    def configure_provider(provider: ProviderID, value: ProviderConfig):
        providers.configure(provider, value)
        return {'status': 'configured'}

    @app.delete('/api/providers/{provider}/config')
    def remove_provider_config(provider: ProviderID):
        providers.remove_keys(provider)
        return {'status': 'removed'}

    @app.get('/api/providers/{provider}/instruments')
    async def search_provider_instruments(provider: ProviderID, query: str = ''):
        return await providers.instruments(provider, query)

    @app.post('/api/history', response_model=Dataset)
    async def provider_history(value: HistoryRequest, request: Request):
        task = asyncio.create_task(providers.history(value))
        try:
            while not task.done():
                await asyncio.wait([task], timeout=.2)
                if await request.is_disconnected():
                    raise HTTPException(status_code=499, detail='History request cancelled')
            return await task
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    @app.get('/api/workspaces/{identifier}', response_model=Workspace)
    def workspace(identifier: str):
        return store.workspace(identifier)

    @app.put('/api/workspaces/{identifier}', response_model=Workspace)
    def save_workspace(identifier: str, value: Workspace):
        if value.id != identifier:
            raise ValueError('Workspace identity does not match its destination')
        return store.save_document('workspace', identifier, value.model_dump(mode='json'), value.revision)

    @app.get('/api/workspaces/{identifier}/export')
    def export_workspace(identifier: str):
        value = store.workspace(identifier)
        return JSONResponse(value.model_dump(mode='json'), headers={
            'Content-Disposition': 'attachment; filename="market-workbench-workspace.json"'})

    @app.get('/api/datasets', response_model=list[Dataset])
    def datasets():
        return store.datasets()

    @app.get('/api/indicators', response_model=list[IndicatorDefinition])
    def indicator_registry():
        return registry()

    @app.post('/api/drawings/measure')
    def measure_drawings(value: DrawingMeasurementRequest):
        results = {}
        for drawing in value.drawings:
            try:
                results[drawing.id] = position_measurement(drawing, value.instrument)
            except ValueError as exc:
                results[drawing.id] = {'label': str(exc), 'error': True}
        return results

    @app.post('/api/indicators/calculate', response_model=IndicatorResponse)
    def calculate_indicators(value: IndicatorRequest):
        return evaluate(value, store.dataset(value.dataset_id), store.bars(value.dataset_id))

    @app.get('/api/datasets/{identifier}', response_model=DatasetView)
    def dataset(identifier: str, cutoff: int | None = None):
        bars = store.bars(identifier)
        if cutoff is not None:
            bars = [b for b in bars if b.complete and b.end <= cutoff]
        return DatasetView(dataset=store.dataset(identifier), bars=bars)

    @app.post('/api/datasets/{identifier}/aggregate', response_model=Dataset)
    def aggregate_dataset(identifier: str, interval: Interval):
        source = store.dataset(identifier)
        bars = aggregate(store.bars(identifier), source.interval, interval, source.instrument)
        limitations = [*source.limitations, 'Aggregated from the recorded parent dataset.']
        if any(not b.complete for b in bars):
            limitations.append('Some aggregate bars are incomplete: source gaps or partial interval coverage. Incomplete bars are unavailable to completed-bar strategies.')
        return store.save_dataset(source.instrument, interval, bars,
                                  limitations, source.id)

    @app.post('/api/examples/dataset', response_model=Dataset)
    def load_example():
        return example_dataset(store)

    @app.post('/api/imports/preview', response_model=ImportPreview)
    def preview_import(value: ImportRequest):
        preview, bars = parse_import(value)
        now = time.monotonic()
        for token, entry in list(previews.items()):
            if now - entry[0] > 1800:
                previews.pop(token, None)
        if len(previews) >= 20:
            previews.pop(next(iter(previews)))
        previews[preview.token] = (now, value, preview, bars)
        return preview

    @app.post('/api/imports/commit', response_model=Dataset)
    def commit_import(value: CommitImport):
        entry = previews.get(value.token)
        if entry is None or time.monotonic() - entry[0] > 1800:
            raise HTTPException(status_code=410, detail='Preview expired; preview the file again')
        _, request, preview, bars = entry
        if not preview.can_commit:
            raise ValueError('Resolve import errors before committing the dataset')
        return store.save_dataset(request.instrument, request.interval, bars, preview.warnings)

    @app.websocket('/api/events')
    async def events(socket: WebSocket):
        if socket.headers.get('origin') not in ORIGINS:
            await socket.close(code=1008)
            return
        await socket.accept()
        subscriptions: set[str] = set()
        quote_subscriptions = {}
        send_lock = asyncio.Lock()

        async def send(value):
            async with send_lock:
                await socket.send_json(value)

        async def forward(subscription, queue):
            while True:
                message = await queue.get()
                await send({**message, 'subscription': subscription})

        async def unsubscribe(subscription):
            entry = quote_subscriptions.pop(subscription, None)
            if entry:
                token, task = entry
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                await quotes.unsubscribe(token)

        try:
            while True:
                message = await socket.receive_json()
                action, subscription = message.get('action'), message.get('subscription')
                if action == 'subscribe' and subscription == 'health':
                    subscriptions.add(subscription)
                    await send({'subscription': subscription, 'type': 'health', 'status': 'ok'})
                elif action == 'subscribe' and isinstance(subscription, str) and subscription.startswith('quote:'):
                    try:
                        instrument = Instrument.model_validate(message.get('instrument'))
                        await unsubscribe(subscription)
                        token, queue = await quotes.subscribe(message.get('provider'), instrument)
                        task = asyncio.create_task(forward(subscription, queue))
                        quote_subscriptions[subscription] = (token, task)
                    except (ValueError, TypeError, KeyError):
                        await send({'subscription': subscription, 'type': 'error', 'detail': 'Quote subscription is invalid or requires configured provider keys.'})
                elif action == 'unsubscribe' and isinstance(subscription, str):
                    subscriptions.discard(subscription)
                    await unsubscribe(subscription)
                    await send({'subscription': subscription, 'type': 'unsubscribed'})
                else:
                    await send({'type': 'error', 'detail': 'Unknown subscription command'})
        except (WebSocketDisconnect, RuntimeError):
            subscriptions.clear()
        finally:
            for subscription in list(quote_subscriptions):
                await unsubscribe(subscription)

    dist = APP_ROOT / 'dist'
    if (dist / 'assets').is_dir():
        app.mount('/assets', StaticFiles(directory=dist / 'assets'), name='assets')

    @app.get('/')
    def index():
        if not (dist / 'index.html').is_file():
            return JSONResponse({'detail': 'Frontend is not built. Run npm run dev or npm run build.'}, status_code=503)
        return FileResponse(dist / 'index.html')

    return app


app = create_app()
