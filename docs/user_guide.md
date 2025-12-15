# User Guide

This guide covers how to use the CLI and web interfaces on edge devices, and how to access the cloud UI.

## CLI (Edge device)

Start the CLI interactive menu on an edge device container or local environment:

```bash
python edge/edge_app.py --cli
```

Menu actions include:

- Create Report — enter `report_id`, `title`, `content`, `classification` (CUI|IL4|IL5)
- View Reports — list all local reports with sync status and metadata
- Update Report — choose a report by ID and edit fields; updates create new version
- Delete Report — soft delete a report (sets `is_deleted`)
- Sync to Cloud — triggers sync of unsynchronized reports, shows success/failure summary

Tips:

- `report_id` must be alphanumeric with optional hyphens.
- Title max length 255, content max length 2000.
- Authentication errors will trigger token regeneration and a single retry; see troubleshooting below.

## Web interface (Edge device)

Run the edge web server:

```bash
python edge/edge_app.py --web
```

Open your browser to `http://localhost:5000` (or the configured `EDGE_WEB_PORT`) to view and manage local reports. Use the Create/Edit/Delete buttons in the UI; Sync to Cloud triggers a sync and shows per-report status.

## Cloud web interface

When the docker-compose stack is running, access the cloud UI on `https://localhost:8443` (browser may prompt for self-signed cert). The cloud UI lets headquarters staff view latest reports, all versions, and deleted items (when requested).

## Troubleshooting

- Authentication errors (401): Check edge token logs and ensure keys exist in `edge/keys` and containers have mounted them. Tokens are regenerated automatically when possible.
- Sync failures / retries: Check logs in the containers. Edge logs at `/app/data/edge.log`, cloud logs at `/app/data/cloud.log` (these paths are persisted via docker volumes in `docker-compose.yml`).
- Rate limiting (429): Reduce sync frequency or batch updates; rate limiting is per-edge-device.
- DB connectivity: Health endpoint `/api/health` returns DB connectivity status; cloud returns 503 if DB unreachable.

## Screenshots and Examples

Placeholders for screenshots:

- `docs/screenshots/edge_cli.png` — CLI menu example
- `docs/screenshots/edge_web.png` — Edge web interface
- `docs/screenshots/cloud_web.png` — Cloud UI

If you'd like, I can add example screenshots (I can capture them locally if you want).
