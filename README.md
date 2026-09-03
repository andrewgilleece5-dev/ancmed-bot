# Diplomacy vs. Bots — Ancient Mediterranean (and more)

Play full games of Diplomacy against simple AI on maps that webDiplomacy's bot
games don't offer — starting with **Ancient Mediterranean**, plus Classic
(Europe), Pure and Modern.

- **Engine / adjudication / maps / board rendering:** the open-source
  [`diplomacy`](https://github.com/diplomacy/diplomacy) package (DATC-compliant).
- **AI:** a map-agnostic *DumbBot*-style heuristic (`server/bot.py`). Weak to
  moderate — it fights, holds ground and grabs centres, but it doesn't
  negotiate, coordinate across powers, or look ahead. A `Bot` base class is in
  place so a stronger engine can drop in later.
- **Server:** a thin FastAPI app. One game object per game id, kept in memory and
  mirrored to disk so a refresh resumes.
- **UI:** one static HTML page — pick a map and a power, then choose an order for
  each unit from a dropdown and submit. The bots move, the board re-renders.

## Run it locally

Requires Python 3.9 (see `.python-version`; 3.9–3.11 work).

```bash
python -m venv .venv
# Windows:
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m uvicorn server.app:app --port 8000
# macOS / Linux:
# .venv/bin/pip install -r requirements.txt
# .venv/bin/python -m uvicorn server.app:app --port 8000
```

Open <http://localhost:8000>.

Run the tests with `python -m pytest`.

## Deploy

The repo is a self-contained Docker image (`Dockerfile`) that listens on `$PORT`.

### Render (free tier)

1. Push this repo to GitHub.
2. Edit `render.yaml` — set `ANCMED_SOURCE_URL` to your repo URL (the app footer
   links there to satisfy the AGPL "offer source" clause).
3. In Render: **New ▸ Blueprint**, point it at the repo, **Apply**.

Render's free plan has no persistent disk, so saved games are lost when the
instance sleeps. For durable games, upgrade the service and add the `disk:`
block noted in `render.yaml`.

### Fly.io / Railway / anywhere else

Any host that builds a Dockerfile works:

```bash
fly launch --dockerfile Dockerfile          # Fly
railway up                                    # Railway
docker build -t ancmed-bot . && docker run -p 8000:8000 ancmed-bot   # local
```

Set `ANCMED_DATA_DIR` to a writable path (a mounted volume for persistence) and
`ANCMED_SOURCE_URL` to your public source repo.

## How the bot works

`DumbBot` in `server/bot.py`, each phase:

1. **Value every province.** A supply centre is worth a lot if an enemy owns it,
   less if it's neutral, little if it's a quiet centre of ours (don't camp), a
   lot again if it's ours *and* an enemy is next door (defend it).
2. **Build a potential field.** Each province inherits the value of the best
   supply centre reachable from it, decayed by distance. From any square at least
   one neighbour is worth more, so units keep advancing toward the nearest prize.
3. **Order each unit** onto its best-valued legal destination (softmax-sampled so
   games diverge), nudged by local force balance, avoiding self-bounces.
4. **Add supports** for the strongest contested moves.
5. **Retreats** go to the best adjacent province, else disband. **Builds** go to
   the most valuable home centres (fleet if coastal); **disbands** remove the
   least useful units.

Everything is derived from `game.map` + `game.get_state()`, so the same code runs
unchanged on every map.

## Adding a map

Any map the `diplomacy` package ships with a matching SVG template in
`diplomacy/maps/svg/` can be added to `PLAYABLE_MAPS` in `server/app.py`
(currently `ancmed`, `standard`, `pure`, `modern`). Maps without an SVG template
adjudicate fine but won't render.

## Licence

This project builds on `diplomacy`, which is **AGPL-3.0**, so this project is
distributed under the **AGPL-3.0** too (`LICENSE`). If you deploy it publicly you
must offer users the source — hence `ANCMED_SOURCE_URL` and the footer link.
