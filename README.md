# competitie-sync

Export one team's match schedule from **toernooi.nl** as a Google-Calendar-importable
`.ics` file. Re-running keeps event IDs stable, so re-importing **updates** existing
events (changed times/venues) instead of creating duplicates.

## Requirements

- Python 3.9+ (uses the standard library only; `zoneinfo` for timezone handling).
- Internet access.

Optional: install `certifi` for a reliable TLS certificate bundle (recommended on
macOS). The script works without it and falls back gracefully.

```bash
pip install -r requirements.txt
```

## Usage

```bash
python3 competitie_sync.py
```

You'll be prompted step by step:

1. **Sport** — pick from the list (e.g. Badminton).
2. **League** — type a keyword (e.g. `Vlaamse interclubcompetitie 2026`) and pick a result.
3. **Club** — pick your club from the league's clubs.
4. **Team** — pick the team.

The script writes `<team-name>.ics` in the current directory, e.g. `herne-1h-19.ics`.

## Excel availability sheet

`competitie_excel.py` uses the **same interactive flow** but writes a
"wie wanneer competitie" planning grid as `.xlsx` instead of an `.ics`:

```bash
pip install -r requirements.txt   # installs openpyxl
python3 competitie_excel.py
```

It produces `<team-name>-wiewanneercomp.xlsx` with:

- One **column per match** headed `weekday dd/mm/yyyy HH:MM vs Opponent`
  (Dutch weekday; time omitted when unknown).
- A **Locatie** row (`thuis`/`uit`) derived from home/away.
- An **Eten** row and **basis**/**reserve** player blocks to fill in by hand.
- A small legend: `x` = kan meedoen, `?` = nog niet zeker, blank = kan niet meedoen.

## Import into Google Calendar

1. Open [Google Calendar](https://calendar.google.com) → gear icon → **Settings**.
2. **Import & export** → **Import** → choose the `.ics` file → pick a calendar → **Import**.

## Keeping the calendar in sync

Match times and venues can change during the season. To sync:

1. Re-run `python3 competitie_sync.py` and select the same team.
2. Import the regenerated `.ics` again.

Because each event has a stable ID (`match-<league>-<match>@toernooi.nl`), Google
Calendar updates the existing events rather than duplicating them.

> Note: importing does not delete events that were removed upstream; it only adds
> and updates. Tip: import each team into its own dedicated Google calendar so you
> can wipe and re-import cleanly if needed.

## Event details

- **Title**: `Home team - Away team`
- **Time**: match start (Europe/Brussels), fixed **3-hour** duration.
- **Location**: venue name.
- **Description**: pool, round, and a link to the match page.
