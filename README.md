# competitie-sync

Export one team's match schedule from **toernooi.nl** as a Google-Calendar-importable
`.ics` file. Re-running keeps event IDs stable, so re-importing **updates** existing
events (changed times/venues) instead of creating duplicates.

## Requirements

- Python 3.9+ (uses the standard library only; `zoneinfo` for timezone handling).
- Internet access.

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
