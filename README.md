# dartscore

Lokales Auto-Scoring-System für Steeldart mit drei Kameras – ähnlich wie Autodarts, aber komplett offline, mit lokalen Profilen und Statistiken. Anforderungen und Roadmap: [docs/PRD.md](docs/PRD.md).

## Aufbau

| Ordner | Inhalt |
| --- | --- |
| `backend/` | Python-Paket `dartscore`: FastAPI-Server, Spiellogik (`game`), Erkennung (`vision`), Persistenz (`storage`) |
| `frontend/` | Web-Oberfläche (React + TypeScript + Vite), responsiv für Handy, Tablet, Desktop und TV |
| `docs/` | PRD und weitere Dokumentation |
| `config.example.toml` | Beispielkonfiguration (Server, Kameras, Logging) |

## Voraussetzungen

- [uv](https://docs.astral.sh/uv/) (installiert Python 3.12 automatisch)
- Node.js ≥ 20 mit npm
- `make`

## Einrichten

```bash
make install
cp config.example.toml config.toml
make hooks
```

`make hooks` installiert die Git-Hooks, die vor jedem Commit formatieren, linten und Typen prüfen.

## Entwickeln

Backend und Frontend in zwei Terminals starten:

```bash
make dev-backend
```

```bash
make dev-frontend
```

Die Oberfläche läuft dann auf http://localhost:5173 und leitet `/api` und `/ws` an das Backend auf Port 8000 weiter. Andere Geräte im Heimnetz erreichen sie über die IP des Rechners.

## Prüfen

```bash
make check
```

Führt Lint, Typprüfung, Tests und den Frontend-Build aus.

## Konfiguration

Die Konfiguration wird in dieser Reihenfolge gesucht: `--config <pfad>`, Umgebungsvariable `DARTSCORE_CONFIG`, `./config.toml`. Einzelne Werte lassen sich per Umgebungsvariable überschreiben, verschachtelte Schlüssel mit `__`:

```bash
DARTSCORE_SERVER__PORT=9000 DARTSCORE_LOGGING__LEVEL=DEBUG make dev-backend
```

Mit `logging.json_output = true` schreibt der Server JSON-Logs, z. B. für den Betrieb als systemd-Dienst.
