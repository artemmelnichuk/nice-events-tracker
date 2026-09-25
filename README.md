# Nice Events Tracker

A personal tool that collects upcoming concerts around Nice and the Côte d'Azur from several public sources, merges the same event when more than one site lists it, and keeps a running Excel dataset that I review and rate. Built as a hands-on project in data pipelines, scraping and agent-driven development, and developed with [Claude Code](https://claude.com/claude-code).

> Personal, non-commercial project. Read [Responsible use](#responsible-use) before running it.

## Status

Works end to end on a few hundred upcoming events. Runs are started by hand: no scheduler and no push notifications yet (see the [Roadmap](#roadmap)).

## What it does

- **Collectors.** One adapter per source behind a common `BaseCollector` interface: plain HTTP with BeautifulSoup for server-rendered pages, headless Playwright for sites that reject plain HTTP clients or render in the browser.
- **Cross-source deduplication.** The same concert often appears on two or three sites under different titles ("Ninho – Quatro Tour" vs "Ninho @ Palais Nikaïa", "Isha & Limsa" vs "LIMSA + ISHA"). Records are grouped by date and merged on title, word prefix, reordered words or shared venue, keeping the richest fields of each.
- **Stable identity.** An event keeps its id when a new source joins it or its title or URL changes, so reruns update rows instead of duplicating them and my ratings stay attached.
- **Ranking.** Themes I consistently dislike sink to the bottom of the workbook (config-driven), events that already ended are not added, cancellations are flagged.
- **Excel output.** A raw workbook per run and a processed workbook merged across runs.
- **Manual channel.** Events from sources that can't or shouldn't be scraped go into `config/manual_events.yaml` and flow through the same pipeline.
- **Review loop.** A small private review UI (a Claude artifact with a persistent database) collects thumbs up/down. `scripts/sync_diff.py` works out what to write to it: only new documents and changed collector fields, never a rating and never a delete.

## Pipeline

```text
collectors ─▶ cross-source merge ─▶ in-run dedup ─▶ drop finished ─▶ merge into stored workbook ─▶ theme ranking ─▶ Excel
(per source)  (title/date/venue)    (by URL)                        (stable ids, absorbs duplicates)
```

### Example

Four invented listings (fictional artist, venues and URLs) for the same day, run through the real `merge_cross_source_duplicates`:

| Source | Title as listed | Theme | Venue | Price |
|---|---|---|---|---|
| explorenicecotedazur | Marlowe & the Tides — Blue Hour Tour | Jazz and blues | – | – |
| songkick | Marlowe & the Tides @ Salle Fictive | – | Salle Fictive | – |
| panda_events | MARLOWE & THE TIDES | – | Salle Fictive | from 18 € |
| songkick | Quartet Nocturne @ Halle du Port | – | Halle du Port | – |

Result: two rows.

| Source | Title | Theme | Venue | Price |
|---|---|---|---|---|
| explorenicecotedazur+panda_events+songkick | Marlowe & the Tides | Jazz and blues | Salle Fictive | from 18 € |
| songkick | Quartet Nocturne @ Halle du Port | – | Halle du Port | – |

The first three share a date and a title (exactly, or as a word prefix), so they become one row that takes the theme from one source, the venue from another and the price from the third. The all-caps title is replaced by the mixed-case one. The fourth is a different act on the same day and stays separate. The rules are covered in `tests/test_cross_source_dedup.py` and `tests/test_second_pass_dedup.py`.

## Sources

| Source | How | Notes |
|---|---|---|
| Nice Côte d'Azur tourist office | HTTP | Official agenda; category filtered client-side |
| Opéra de Nice | HTTP | Programme with categories |
| Panda Events | HTTP | Club and mid-size venues; real prices on almost every card |
| Cannes tourist office | HTTP | Concert detected from the detail page; includes nearby communes |
| Menton tourist office | HTTP | Same platform as Cannes; several nearby communes |
| Songkick | Playwright | Nice city page (JSON-LD). See [Responsible use](#responsible-use) |
| HelloAsso | Playwright | Hand-picked organizers only (JSON-LD). See [Responsible use](#responsible-use) |
| Manual entries | YAML | For events from sources that aren't scraped |

Not used: Resident Advisor, Shotgun and Instagram (bot protection and/or terms rule scraping out). Antibes has an adapter in the code but is switched off: its legal notice forbids extracting from its database without agreement.

## Quick start (Windows)

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m playwright install chromium
.venv\Scripts\python scripts\collector.py
```

Output goes to `data/raw/nice_events_raw.xlsx` and `data/processed/nice_events_processed.xlsx` (gitignored). A partial run (`--source X`) refreshes X's fields on rows already merged from several sources and keeps what the other sources contributed (theme, venue, ...); run all sources to re-decide a merge from scratch.

Tests run offline on saved markup and fake sessions:

```bash
.venv\Scripts\python -m unittest discover -s tests
```

## Responsible use

- Personal, non-commercial use. The data files are not committed (`data/` is gitignored) and nothing is republished.
- One run a day at most, a pause between requests, and no more than around a hundred requests per source per run.
- The HTTP adapters identify themselves (`nice-events-tracker; personal project`). The two browser adapters (Songkick, HelloAsso) use a standard Chrome User-Agent, because those sites reject plain HTTP clients.
- Terms differ by source. The tourist-office notices restrict reproduction and publication of their content and say nothing about automated access. HelloAsso's terms contain no scraping clause I could find. **Songkick's terms prohibit scrapers and automated data mining without written consent.** I use the Songkick and HelloAsso adapters for my own private use and accept that risk myself. If you fork this, decide for yourself: each is a single line in `config/settings.yaml`, and Songkick in particular should not be run publicly, commercially or at any volume.
- New sources get a manual review of `robots.txt` and the site's legal notice first. That review is why Resident Advisor was never added and Antibes was switched off.

## Built with Claude Code

I set the requirements, choose and vet the sources, rate events, and make the calls on scope and legal risk; Claude Code implements and tests. [`CLAUDE.md`](CLAUDE.md) holds the standing rules for the agent: work in an isolated git worktree, run the full test suite, and merge to `master` only when it is green and, where practical, after a live smoke test against the real source. Two of the sources (Antibes, Menton) were added that way.

## Roadmap

- [x] Concerts from several sources with cross-source deduplication.
- [x] Broaden geography from Nice to the wider Côte d'Azur (Cannes, Menton done).
- [ ] Broaden from concerts to the full event taxonomy (festivals, markets, exhibitions, sports, gastronomy).
- [ ] Broaden geography further (Grasse, Monaco, nearby major cities), preferably from open data such as DATAtourisme rather than scraping.
- [ ] Add more sources, dedup across them, automate a daily run, and (maybe) push notifications for new events.
- [ ] A separate, related project: a music-festival tracker across Europe, reusing the same core once it's proven here.

## Project layout

```text
collectors/   one adapter per source, plus BaseCollector
core/         EventRecord, ids, dedup and merge, Excel storage, filters, ranking, sync diff
scripts/      collector.py (main run), sync_diff.py, add_manual_events.py, drop_source.py
config/       settings.yaml (sources, disliked themes), manual_events.yaml
tests/        unit tests
scrape_mvp.py the original single-source prototype, kept for reference
```
