from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .candles import CandleService


def routes(service: CandleService, origins):
    router = APIRouter()

    @router.get('/api/candles')
    def statuses():
        return {'running': service.loop_task is not None and not service.loop_task.done(),
                'error': service.error, 'series': list(service.states.values())}

    @router.post('/api/candles/{dataset_id}/retry')
    async def retry(dataset_id: str):
        dataset = service.store.dataset(dataset_id)
        service._validate(dataset)
        state = service._state(dataset)
        if state.series_id in service.tasks and not service.tasks[state.series_id].done():
            return state
        # Explicit retry may restart a failed check; provider-level request spacing still applies.
        state.next_check = 0
        return state

    @router.websocket('/api/candles/events')
    async def events(socket: WebSocket):
        if socket.headers.get('origin') not in origins:
            await socket.close(code=1008)
            return
        await socket.accept()
        token = None
        identities = []
        receiver = asyncio.create_task(socket.receive_json())
        try:
            while True:
                done, _ = await asyncio.wait([receiver], timeout=1)
                if done:
                    message = receiver.result()
                    action = message.get('action') if isinstance(message, dict) else None
                    if action == 'subscribe':
                        try:
                            next_ids = message.get('dataset_ids')
                            next_token = service.subscribe(next_ids)
                        except (ValueError, KeyError, TypeError) as exc:
                            await socket.send_json({'subscription': 'candles', 'type': 'error', 'detail': str(exc)})
                        else:
                            if token:
                                service.unsubscribe(token)
                            token, identities = next_token, next_ids
                    elif action == 'unsubscribe':
                        if token:
                            service.unsubscribe(token)
                        token, identities = None, []
                        await socket.send_json({'subscription': 'candles', 'type': 'unsubscribed'})
                    else:
                        await socket.send_json({'subscription': 'candles', 'type': 'error', 'detail': 'Unknown candle subscription command'})
                    receiver = asyncio.create_task(socket.receive_json())
                if token:
                    await socket.send_json({'subscription': 'candles', 'type': 'candles', 'error': service.error,
                        'states': {key: value.model_dump(mode='json') for key, value in service.status(identities).items()}})
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            receiver.cancel()
            await asyncio.gather(receiver, return_exceptions=True)
            if token:
                service.unsubscribe(token)
    return router
