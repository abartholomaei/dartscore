# dartscore

Local auto-scoring system for steel-tip darts with three cameras - similar to Autodarts, but fully offline, with local profiles and statistics. Requirements and roadmap: [docs/PRD.md](docs/PRD.md).

## Structure

| Folder | Contents |
| --- | --- |
| `backend/` | Python package `dartscore`: FastAPI server, game logic (`game`), detection (`vision`), persistence (`storage`) |
| `frontend/` | Web UI (React + TypeScript + Vite), responsive for phone, tablet, desktop and TV |
| `docs/` | PRD and further documentation |
| `config.example.toml` | Example configuration (server, cameras, logging) |

## Requirements

- [uv](https://docs.astral.sh/uv/) (installs Python 3.12 automatically)
- Node.js ≥ 20 with npm
- `make`

## Setup

```bash
make install
cp config.example.toml config.toml
make hooks
```

`make hooks` installs the Git hooks that format, lint and type-check before every commit.

## Development

Start backend and frontend in two terminals:

```bash
make dev-backend
```

```bash
make dev-frontend
```

The UI then runs on http://localhost:5173 and proxies `/api` and `/ws` to the backend on port 8000. Other devices on the home network reach it via the computer's IP.

## Production

Build the frontend once; the backend then serves it on port 8000 (no Node.js needed on the target machine):

```bash
cd frontend && npm run build
```

```bash
make dev-backend
```

The UI is then available at http://<host>:8000.

To run it as a service, see [deploy/dartscore.service](deploy/dartscore.service). It conflicts with Autodarts, so starting one stops the other.

## UI languages

The web UI is available in English and German; the language follows the browser and can be switched in the header. Strings live in `frontend/src/i18n/locales/` (`en.ts` is the source of truth, other locales are type-checked against it). To add a language, create a new locale file and register it in `frontend/src/i18n/index.ts`.

## Checks

```bash
make check
```

Runs lint, type checking, tests and the frontend build.

## Configuration

The configuration is looked up in this order: `--config <path>`, environment variable `DARTSCORE_CONFIG`, `./config.toml`. Individual values can be overridden via environment variables, nested keys with `__`:

```bash
DARTSCORE_SERVER__PORT=9000 DARTSCORE_LOGGING__LEVEL=DEBUG make dev-backend
```

With `logging.json_output = true` the server writes JSON logs, e.g. when running as a systemd service.
