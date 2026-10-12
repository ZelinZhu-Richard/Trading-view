from fastapi import APIRouter
from pydantic import BaseModel

from .accounts import AccountService
from .research_models import (
    AccountCancel,
    AccountOrder,
    AccountRequest,
    AccountSeek,
    AccountView,
    PaperAccount,
)


class AccountRevision(BaseModel):
    revision: int


class AccountPause(AccountRevision):
    paused: bool


def routes(service: AccountService):
    router = APIRouter(prefix='/api/accounts')

    @router.get('', response_model=list[PaperAccount])
    def accounts():
        return service.accounts()

    @router.post('', response_model=AccountView)
    def create(request: AccountRequest):
        return service.create(request)

    @router.get('/{identifier}', response_model=AccountView)
    def get(identifier: str):
        return service.view(identifier)

    @router.post('/{identifier}/seek', response_model=AccountView)
    def seek(identifier: str, request: AccountSeek):
        return service.seek(identifier, request.time, request.revision)

    @router.post('/{identifier}/orders', response_model=AccountView)
    def order(identifier: str, request: AccountOrder):
        return service.order(identifier, request.order, request.revision)

    @router.post('/{identifier}/cancel', response_model=AccountView)
    def cancel(identifier: str, request: AccountCancel):
        return service.cancel(identifier, request.order_id, request.revision)

    @router.post('/{identifier}/pause', response_model=AccountView)
    def pause(identifier: str, request: AccountPause):
        return service.pause(identifier, request.revision, request.paused)

    @router.post('/{identifier}/refresh', response_model=AccountView)
    def refresh(identifier: str, request: AccountRevision):
        return service.refresh_paper(identifier, request.revision)

    return router
