# Kalshi / Polymarket Arb Scanner

Runs every 15 minutes via GitHub Actions and publishes results to GitHub Pages.

## Files

| File | Purpose |
|------|---------|
| `compare8.py` | Original scanner script (runs locally) |
| `export_json.py` | Headless version — fetches all markets, writes `data.json` |
| `index.html` | Web UI — reads `data.json` and renders tables |
| `.github/workflows/scan.yml` | Runs `export_json.py` on a schedule and commits `data.json` |

## Setup

1. Upload all files to a **public** GitHub repo
2. Go to **Settings → Pages** → Source: Deploy from branch `main` / folder `/ (root)`
3. Go to **Actions** tab → click the workflow → **Run workflow** to trigger the first run
4. Your page will be live at `https://YOUR-USERNAME.github.io/REPO-NAME/`

The workflow runs every 15 minutes automatically after that.
