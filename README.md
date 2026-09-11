# Nice Events Tracker

A personal tool for tracking interesting events around Nice, France — starting with concerts, expanding later to other event types, the wider Côte d'Azur, and nearby major cities.

## Status

Stage 1 (MVP): [scrape_mvp.py](scrape_mvp.py) pulls concert listings from the official [Nice Côte d'Azur Tourist Office](https://www.explorenicecotedazur.com/en/events/all-events/) event calendar and saves them to an Excel file. No architecture yet on purpose — this proves the source works end to end on real data before designing a reusable data model/collector structure.

## Roadmap

- Broaden from concerts to the full event taxonomy (festivals, markets, exhibitions, sports, gastronomy).
- Broaden geography from Nice to the wider Côte d'Azur, then nearby major cities.
- Add more sources, dedup across them, automate a daily run, and (maybe) push notifications for new events.
- A separate, related project: a music-festival tracker across Europe, reusing the same core once it's proven here.

## Usage

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python scrape_mvp.py
```

Output goes to `data/nice_concerts_raw.xlsx` (gitignored — regenerate anytime by re-running the script).
