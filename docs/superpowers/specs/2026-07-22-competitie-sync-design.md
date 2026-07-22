# competitie-sync — Design

Date: 2026-07-22

## Purpose

A single-file Python 3 script (standard library only) that interactively walks a
user from sport → league → club → team on toernooi.nl and writes an importable
`.ics` calendar file of that team's full-season matches. Re-running regenerates
the file with **stable event UIDs**, so re-importing into Google Calendar updates
existing events instead of creating duplicates.

## Interactive flow

1. **Sport** — pick from a fixed list (Badminton, Tennis, …). Required because
   league search is scoped to the currently selected sport.
2. **League** — enter a search term; the script queries the league search and
   lists matching leagues; user picks one.
3. **Club** — the script lists all clubs in the league; user picks one.
4. **Team** — the script lists that club's teams; user picks one.
5. The script resolves the team's pool, fetches the full pool schedule, filters
   the team's matches, and writes `<team-name>.ics`.

## Data sources (toernooi.nl)

All requests require first passing the cookiewall (POST `/cookiewall/Save` to
obtain the `st` cookie) and selecting a sport
(`/sportselection/setsportselection/<id>`).

| Step | Endpoint |
|------|----------|
| League search | `POST /find/league/DoSearch` with `LeagueFilter.Q`; results link to `/sport/tournament?id=<GUID>` |
| Clubs | `GET /sport/clubs.aspx?id=<GUID>` → `club.aspx?...&club=<n>` |
| Club teams | `GET /sport/clubteams.aspx?id=<GUID>&cid=<n>` → `team.aspx?...&team=<n>` |
| Team detail | `GET /sport/team.aspx?id=<GUID>&team=<n>` → team display name + pool `draw=<n>` |
| Full schedule | `GET /sport/drawmatches.aspx?id=<GUID>&draw=<n>` → all pool matches |

A team belongs to exactly one pool (`draw`). The full schedule is obtained from
`drawmatches.aspx` and filtered to rows where the team is home or away. Each match
row provides: date, time (may be absent/TBD), pool name (from the table caption),
home team, away team, venue, and a stable `match=<id>` identifier.

## Components (one file, focused functions)

- `Session` — cookiewall handling, sport selection, GET/POST via `urllib`.
- `SPORTS` — name → sport-selection id map.
- `search_leagues(q)`, `list_clubs(gid)`, `list_teams(gid, cid)`,
  `get_team(gid, tid)`, `fetch_schedule(gid, draw)` — fetch + parse, return
  dataclasses.
- `filter_team_matches(matches, team_name)`.
- `build_ics(matches, team_name, gid)`.
- `main()` — interactive prompt loop with numeric selection.

## Event format

- **Summary**: `Home - Away`
- **Start**: match date + time in `Europe/Brussels`, converted to UTC (`zoneinfo`)
  and emitted as `...Z` to avoid VTIMEZONE ambiguity.
- **Duration**: fixed 3 hours.
- **Location**: venue name.
- **Description**: pool name, round, match number, source URL.
- **UID**: `match-<GUID>-<matchid>@toernooi.nl` — stable across runs.

Matches without a scheduled date are skipped with a warning (cannot place on a
calendar).

## Sync behaviour

Re-run → regenerated `.ics` → re-import into Google Calendar. Stable UIDs mean
changed times/venues update the existing event. Google import does not remove
events deleted upstream (documented limitation).

## Error handling

Clear messages for: empty search results, network/HTTP errors, empty schedules,
invalid menu input (re-prompt). No third-party dependencies.
