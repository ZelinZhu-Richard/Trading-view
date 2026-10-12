# Market Workbench contribution instructions

## Scope and saved state

- Read `goal.md` for agreed scope and `docs/progress.md` for the current state.
- Keep implementation, scripts, documentation and evidence together in this repository.
- Preserve unrelated parent REA source and user changes. Do not access protected holdout data for development; inherited workspace and holdout rules still apply.
- Keep `data/`, credentials, local environments, browser profiles, generated builds and binary captures out of Git. Never print saved provider keys or copy them into test fixtures.
- Preserve historical evidence. Clearly distinguish actual provider/browser observations from fixtures, inferences and unverified behavior.
- Windows execution and actual Alpaca IEX trade delivery remain required checks. Further Edge verification was waived by the user. Do not mark the whole goal complete without resolving its remaining requirements.
- No real brokerage orders, paid purchases or deployment are authorized by the product goal. Commit and push only when the user requests it.

## Development and checks

Use Python 3.12, `.nvmrc`, and `package.json#packageManager`. Install locked dependencies with `uv sync --locked` and `npm ci`. Run `npm run dev` from the repository root to start the loopback backend and frontend; avoid duplicate servers.

Run checks appropriate to the change:

- Backend and actual worker processes: `uv run pytest`.
- Frontend helpers: `npm test`.
- TypeScript and built app: `npm run build`.
- Specification coverage and evidence links: `uv run python scripts/check-acceptance.py`.
- After backend model changes, regenerate browser contracts with `uv run python scripts/generate-contracts.py`.

When changing `goal.md`, review the affected entries in `docs/requirements.json` and update its source hash and exact requirement text. Preserve unresolved acceptance items. Use Conventional Commit subjects and state only validation actually performed.
