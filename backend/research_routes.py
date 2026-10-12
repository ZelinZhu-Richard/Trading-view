"""Local-only Run/Cancel, retained inputs/results, and job-scoped progress events."""
import asyncio
import csv
import io
import json

from fastapi import APIRouter, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from .research import ResearchService
from .research_models import (
    Contribution,
    EquityPoint,
    Fill,
    Position,
    ResearchJob,
    ResearchRequest,
    ResearchResult,
    SimulationOrder,
    Trade,
)

CSV_MODELS = {'orders': SimulationOrder, 'fills': Fill, 'trades': Trade,
              'equity': EquityPoint, 'positions': Position, 'contributions': Contribution}


def routes(service: ResearchService, origins: set[str]):
    router = APIRouter(prefix='/api/research')

    @router.get('', response_model=list[ResearchJob])
    def jobs():
        return service.jobs()

    @router.post('', response_model=ResearchJob)
    async def run(request: ResearchRequest):
        return await service.submit(request)

    @router.get('/{identifier}', response_model=ResearchJob)
    def job(identifier: str):
        return service.job(identifier)

    @router.post('/{identifier}/cancel', response_model=ResearchJob)
    async def cancel(identifier: str):
        return await service.cancel(identifier)

    @router.get('/{identifier}/result', response_model=ResearchResult)
    def result(identifier: str):
        return service.result(identifier)

    @router.get('/{identifier}/snapshot')
    def snapshot(identifier: str):
        return service.verify_snapshot(identifier)

    @router.get('/{identifier}/output')
    def output(identifier: str):
        return service.output(identifier)

    @router.get('/{identifier}/export/{table}')
    def export(identifier: str, table: str):
        result = service.result(identifier)
        if table == 'json':
            return FileResponse(service.directory(identifier)/'result.json', media_type='application/json',
                filename=f'market-workbench-{identifier}.json')
        if table not in CSV_MODELS:
            raise ValueError('Choose json, orders, fills, trades, equity, positions, or contributions')
        records = result.final_portfolio.positions if table == 'positions' else getattr(result, table)
        rows = [record.model_dump(mode='json') for record in records]
        stream = io.StringIO(newline='')
        writer = csv.DictWriter(stream, fieldnames=list(CSV_MODELS[table].model_fields))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False, sort_keys=True)
                if isinstance(value, (dict, list)) else value for key, value in row.items()})
        return Response(stream.getvalue(), media_type='text/csv', headers={
            'Content-Disposition': f'attachment; filename="{identifier}-{table}.csv"'})

    @router.websocket('/{identifier}/events')
    async def events(socket: WebSocket, identifier: str):
        if socket.headers.get('origin') not in origins:
            await socket.close(code=1008)
            return
        try:
            service.job(identifier)
        except KeyError:
            await socket.close(code=1008)
            return
        await socket.accept()
        revision = -1
        try:
            while True:
                value = service.job(identifier)
                if value.revision != revision:
                    await socket.send_json({'type': 'research-progress', 'job_id': identifier,
                        'job': value.model_dump(mode='json')})
                    revision = value.revision
                try:
                    message = await asyncio.wait_for(socket.receive_text(), timeout=.5)
                    if message == 'unsubscribe':
                        await socket.close()
                        return
                except TimeoutError:
                    continue
        except WebSocketDisconnect:
            return

    return router
