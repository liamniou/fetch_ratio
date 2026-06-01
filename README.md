# fetch_ratio

Prometheus exporter that scrapes private tracker profile pages for ratio/uploaded/downloaded metrics.

Image: `ghcr.io/liamniou/fetch_ratio:latest`. Configure via env vars `SITES_CONFIG` (JSON array) and optional `DISCORD_WEBHOOK_URL`. See `main.py` for the site object schema.
