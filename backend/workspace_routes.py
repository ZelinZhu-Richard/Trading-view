"""Focused collection endpoints share the workspace's single revision authority."""
from fastapi import APIRouter

from .models import DrawingsDocument, WatchlistsDocument, Workspace
from .store import Store


def routes(store: Store) -> APIRouter:
    router = APIRouter(prefix='/api')

    def watchlists_view(workspace: Workspace) -> WatchlistsDocument:
        return WatchlistsDocument(workspace_revision=workspace.revision, watchlists=workspace.watchlists,
                                 active_watchlist=workspace.active_watchlist)

    def save(workspace: Workspace, revision: int) -> Workspace:
        return Workspace.model_validate(store.save_document(
            'workspace', workspace.id, workspace.model_dump(mode='json'), revision))

    @router.get('/watchlists/{workspace_id}', response_model=WatchlistsDocument)
    def read_watchlists(workspace_id: str):
        return watchlists_view(store.workspace(workspace_id))

    @router.put('/watchlists/{workspace_id}', response_model=WatchlistsDocument)
    def replace_watchlists(workspace_id: str, value: WatchlistsDocument):
        body = store.workspace(workspace_id).model_dump(mode='json')
        body.update(watchlists=[w.model_dump(mode='json') for w in value.watchlists],
                    active_watchlist=value.active_watchlist)
        return watchlists_view(save(Workspace.model_validate(body), value.workspace_revision))

    def chart(workspace: Workspace, chart_id: str):
        found = next((c for c in workspace.charts if c.id == chart_id), None)
        if found is None:
            raise KeyError('Chart does not exist in this workspace')
        return found

    @router.get('/drawings/{workspace_id}/{chart_id}', response_model=DrawingsDocument)
    def read_drawings(workspace_id: str, chart_id: str):
        workspace = store.workspace(workspace_id)
        return DrawingsDocument(workspace_revision=workspace.revision, drawings=chart(workspace, chart_id).drawings)

    @router.put('/drawings/{workspace_id}/{chart_id}', response_model=DrawingsDocument)
    def replace_drawings(workspace_id: str, chart_id: str, value: DrawingsDocument):
        workspace = store.workspace(workspace_id)
        chart(workspace, chart_id).drawings = value.drawings
        saved = save(workspace, value.workspace_revision)
        return DrawingsDocument(workspace_revision=saved.revision, drawings=chart(saved, chart_id).drawings)

    return router
