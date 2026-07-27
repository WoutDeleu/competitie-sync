#!/usr/bin/env python3
"""competitie-sync — build a Google-Calendar-importable .ics for one team's
matches on toernooi.nl.

Interactive flow: sport -> league -> club -> team -> writes <team>.ics.
Re-running regenerates the file with stable event UIDs so re-importing updates
existing calendar events instead of duplicating them.

Standard library only. Python 3.9+ (needs zoneinfo).
"""

from __future__ import annotations

import html
import http.cookiejar
import re
import ssl
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("Europe/Brussels")
except Exception:  # pragma: no cover - fallback if tzdata missing
    _TZ = None

BASE = "https://www.toernooi.nl"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
MATCH_DURATION = timedelta(hours=3)

# Sport name -> sport-selection id (from /sportselection/setsportselection/<id>)
SPORTS = [
    ("Badminton", 2),
    ("Tennis", 0),
    ("Squash", 1),
    ("Tafeltennis", 3),
    ("Volleybal", 4),
    ("Voetbal", 5),
    ("Hockey", 6),
    ("Basketbal", 7),
    ("Handbal", 8),
    ("Korfbal", 9),
    ("Darts", 11),
    ("Racketlon", 12),
    ("Judo", 13),
    ("Padel", 15),
    ("Pickleball", 16),
]


# --------------------------------------------------------------------------- #
# HTTP session
# --------------------------------------------------------------------------- #
def _make_ssl_context():
    """Verified TLS context, preferring certifi's CA bundle when available.

    macOS python.org builds often lack a linked system CA bundle, which breaks
    the default context; certifi provides one.
    """
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


class Session:
    """Handles the cookiewall, sport selection and raw HTTP requests."""

    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self._ctx = _make_ssl_context()
        self._insecure_warned = False
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar),
            urllib.request.HTTPSHandler(context=self._ctx),
        )
        self._accept_cookies()

    def _open(self, req):
        try:
            return self.opener.open(req, timeout=30)
        except urllib.error.URLError as exc:
            if isinstance(getattr(exc, "reason", None), ssl.SSLCertVerificationError):
                # Fall back to an unverified context for this public,
                # read-only site so the tool keeps working when the local
                # CA bundle is missing.
                if not self._insecure_warned:
                    print(
                        "  [warning] TLS certificate could not be verified; "
                        "continuing without verification.",
                        file=sys.stderr,
                    )
                    self._insecure_warned = True
                self._ctx = ssl._create_unverified_context()
                self.opener = urllib.request.build_opener(
                    urllib.request.HTTPCookieProcessor(self.jar),
                    urllib.request.HTTPSHandler(context=self._ctx),
                )
                return self.opener.open(req, timeout=30)
            raise

    def _request(self, url, data=None, headers=None):
        if url.startswith("/"):
            url = BASE + url
        hdrs = {"User-Agent": USER_AGENT}
        if headers:
            hdrs.update(headers)
        body = data.encode() if isinstance(data, str) else data
        req = urllib.request.Request(url, data=body, headers=hdrs)
        with self._open(req) as resp:
            return resp.read().decode("utf-8", "replace")

    def get(self, url):
        return self._request(url)

    def post(self, url, fields, ajax=False):
        data = urllib.parse.urlencode(fields, doseq=True)
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if ajax:
            headers["X-Requested-With"] = "XMLHttpRequest"
        return self._request(url, data=data, headers=headers)

    def _accept_cookies(self):
        # Accept all cookie purposes to obtain the `st` session cookie.
        try:
            self.post(
                "/cookiewall/Save",
                [("CookiePurposes", v) for v in (1, 2, 4, 8, 16)],
            )
        except Exception:
            pass  # even on non-2xx the cookie is usually set

    def select_sport(self, sport_id):
        self.get(f"/sportselection/setsportselection/{sport_id}?returnUrl=%2Fleagues")


# --------------------------------------------------------------------------- #
# Data models
# --------------------------------------------------------------------------- #
@dataclass
class League:
    id: str
    name: str
    org: str


@dataclass
class Club:
    id: str
    name: str


@dataclass
class Team:
    id: str
    name: str


@dataclass
class Match:
    match_id: str
    date: str        # dd-mm-yyyy
    time: str        # HH:MM or ""
    home: str
    away: str
    location: str
    pool: str
    round: str


# --------------------------------------------------------------------------- #
# Parsing helpers
# --------------------------------------------------------------------------- #
def _clean(text):
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()





def parse_leagues_detailed(page):
    """Parse league search results into [League].

    Each result is a <li class="list__item"> block containing a
    <a ... class="media__link" title="<name>"> and an org/location subheading.
    """
    leagues = []
    seen = set()
    for item in re.split(r'<li class="list__item">', page):
        m = re.search(
            r'/sport/tournament\?id=([0-9A-Fa-f-]{36})"\s+title="([^"]+)"'
            r'\s+class="media__link"',
            item,
        )
        if not m:
            continue
        gid = m.group(1).upper()
        if gid in seen:
            continue
        seen.add(gid)
        name = html.unescape(m.group(2)).strip()
        org = ""
        om = re.search(
            r'media__subheading"[^>]*>.*?nav-link__value">(.*?)</span>', item, re.S
        )
        if om:
            org = _clean(om.group(1))
        leagues.append(League(id=gid, name=name, org=org))
    return leagues


def parse_clubs(page):
    clubs = {}
    for m in re.finditer(
        r'club\.aspx\?id=[0-9A-Fa-f-]{36}&(?:amp;)?club=(\d+)"[^>]*>(.*?)</a>',
        page,
        re.S,
    ):
        cid = m.group(1)
        name = _clean(m.group(2))
        if name and cid not in clubs:
            clubs[cid] = Club(id=cid, name=name)
    return sorted(clubs.values(), key=lambda c: c.name.lower())


def parse_teams(page):
    teams = {}
    for m in re.finditer(
        r'team\.aspx\?id=[0-9A-Fa-f-]{36}&(?:amp;)?team=(\d+)"[^>]*>(.*?)</a>',
        page,
        re.S,
    ):
        tid = m.group(1)
        name = _clean(m.group(2))
        if name and tid not in teams:
            teams[tid] = Team(id=tid, name=name)
    return list(teams.values())


def parse_team_detail(page):
    """Return (team_name, draw_number) from a team.aspx page."""
    name = None
    mt = re.search(r"Team:\s*(.*?)\s*-\s*[^<]*?</title>", page)
    if mt:
        name = _clean(mt.group(1))
    md = re.search(r"draw\.aspx\?id=[0-9A-Fa-f-]{36}&(?:amp;)?draw=(\d+)", page)
    draw = md.group(1) if md else None
    return name, draw


def parse_schedule(page):
    """Parse drawmatches.aspx into [Match]."""
    pool = ""
    cap = re.search(r"<caption>(.*?)</caption>", page, re.S)
    if cap:
        pool = _clean(cap.group(1))
        pool = re.sub(r"^Wedstrijdoverzicht van\s*", "", pool)

    i = page.find('class="ruler matches"')
    if i < 0:
        return []
    end = page.find("</table>", i)
    table = page[i:end]

    matches = []
    for row in re.finditer(r"<tr>(.*?)</tr>", table, re.S):
        r = row.group(1)
        if "teammatch.aspx" not in r:
            continue  # header / empty row

        mid = re.search(r"teammatch\.aspx\?id=[0-9A-Fa-f-]{36}&(?:amp;)?match=(\d+)", r)
        match_id = mid.group(1) if mid else ""

        # planned time cell: "ma 7-9-2026 <span class="time">20:10</span>"
        pt = re.search(r'class="plannedtime"[^>]*>(.*?)</td>', r, re.S)
        date, time = "", ""
        if pt:
            cell = pt.group(1)
            dm = re.search(r"(\d{1,2}-\d{1,2}-\d{4})", cell)
            if dm:
                date = dm.group(1)
            tm = re.search(r'class="time"[^>]*>\s*(\d{1,2}:\d{2})', cell)
            if not tm:
                tm = re.search(r"(\d{1,2}:\d{2})", _clean(cell))
            if tm:
                time = tm.group(1)

        # round: first align="right" cell after plannedtime holds "Ronde"
        rnd = ""
        rm = re.search(r'</td>\s*<td align="right">(\d+)</td>', r)
        if rm:
            rnd = rm.group(1)

        teams = re.findall(r'class="teamname"[^>]*>(.*?)</a>', r, re.S)
        home = _clean(teams[0]) if len(teams) >= 1 else ""
        away = _clean(teams[1]) if len(teams) >= 2 else ""

        loc = ""
        lm = re.search(r'location\.aspx\?[^"]*"[^>]*>(.*?)</a>', r, re.S)
        if lm:
            loc = _clean(lm.group(1))

        matches.append(
            Match(
                match_id=match_id,
                date=date,
                time=time,
                home=home,
                away=away,
                location=loc,
                pool=pool,
                round=rnd,
            )
        )
    return matches


def filter_team_matches(matches, team_name):
    return [m for m in matches if team_name in (m.home, m.away)]


# --------------------------------------------------------------------------- #
# ICS generation
# --------------------------------------------------------------------------- #
def _ics_escape(text):
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _fold(line):
    # RFC 5545: fold lines longer than 75 octets.
    out = []
    while len(line.encode("utf-8")) > 75:
        # find a cut that keeps <=75 bytes
        cut = 75
        while len(line[:cut].encode("utf-8")) > 75:
            cut -= 1
        out.append(line[:cut])
        line = " " + line[cut:]
    out.append(line)
    return "\r\n".join(out)


def _to_utc(date, time):
    d, mth, y = (int(x) for x in date.split("-"))
    hh, mm = (int(x) for x in time.split(":"))
    naive = datetime(y, mth, d, hh, mm)
    if _TZ is not None:
        return naive.replace(tzinfo=_TZ).astimezone(timezone.utc)
    # Fallback: assume CEST/CET offset unavailable -> treat as UTC+2
    return (naive - timedelta(hours=2)).replace(tzinfo=timezone.utc)


def build_ics(matches, team_name, league_id):
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//competitie-sync//toernooi.nl//NL",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_ics_escape(team_name)}",
    ]
    skipped = 0
    for m in matches:
        if not m.date or not m.time:
            skipped += 1
            continue
        start = _to_utc(m.date, m.time)
        end = start + MATCH_DURATION
        summary = f"{m.home} - {m.away}"
        url = f"{BASE}/sport/teammatch.aspx?id={league_id}&match={m.match_id}"
        desc_parts = [p for p in (m.pool, f"Ronde {m.round}" if m.round else "", url) if p]
        desc = " | ".join(desc_parts)
        uid = f"match-{league_id}-{m.match_id}@toernooi.nl"
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now}",
            f"DTSTART:{start.strftime('%Y%m%dT%H%M%SZ')}",
            f"DTEND:{end.strftime('%Y%m%dT%H%M%SZ')}",
            f"SUMMARY:{_ics_escape(summary)}",
        ]
        if m.location:
            lines.append(f"LOCATION:{_ics_escape(m.location)}")
        lines.append(f"DESCRIPTION:{_ics_escape(desc)}")
        lines.append(f"URL:{url}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(l) for l in lines) + "\r\n", skipped


def slugify(name):
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = re.sub(r"[^\w\s-]", "", name).strip().lower()
    return re.sub(r"[-\s]+", "-", name) or "team"


# --------------------------------------------------------------------------- #
# Interactive UI
# --------------------------------------------------------------------------- #
def choose(items, label, render):
    if not items:
        print(f"No {label} found.")
        sys.exit(1)
    for idx, it in enumerate(items, 1):
        print(f"  {idx:>3}. {render(it)}")
    while True:
        raw = input(f"Select {label} [1-{len(items)}] (q to quit): ").strip()
        if raw.lower() == "q":
            sys.exit(0)
        if raw.isdigit() and 1 <= int(raw) <= len(items):
            return items[int(raw) - 1]
        print("  Invalid choice, try again.")


def select_team_matches(session):
    """Run the interactive sport -> league -> club -> team flow.

    Returns (team_name, team_matches, league). Exits the process on
    unrecoverable conditions (no draw, no matches).
    """
    # 1. Sport
    print("Sports:")
    sport = choose(SPORTS, "sport", lambda s: s[0])
    session.select_sport(sport[1])

    # 2. League
    while True:
        query = input("\nSearch leagues (name keyword): ").strip()
        if not query:
            print("  Please enter a search term.")
            continue
        page = session.post(
            "/find/league/DoSearch",
            {
                "LeagueFilter.Q": query,
                "LeagueFilter.CountryCode": "",
                "LeagueFilter.StatusFilterID": "false",
                "Page": "1",
            },
            ajax=True,
        )
        leagues = parse_leagues_detailed(page)
        if leagues:
            break
        print("  No leagues found — try another keyword.")
    print(f"\nLeagues matching '{query}':")
    league = choose(leagues, "league", lambda l: f"{l.name}  [{l.org}]" if l.org else l.name)

    # 3. Club
    clubs = parse_clubs(session.get(f"/sport/clubs.aspx?id={league.id}"))
    print(f"\nClubs in {league.name}:")
    club = choose(clubs, "club", lambda c: c.name)

    # 4. Team
    teams = parse_teams(
        session.get(f"/sport/clubteams.aspx?id={league.id}&cid={club.id}")
    )
    print(f"\nTeams for {club.name}:")
    team = choose(teams, "team", lambda t: t.name)

    # 5. Resolve pool + schedule
    detail = session.get(f"/sport/team.aspx?id={league.id}&team={team.id}")
    team_name, draw = parse_team_detail(detail)
    team_name = team_name or team.name
    if not draw:
        print("Could not determine this team's pool/draw.")
        sys.exit(1)

    schedule = parse_schedule(
        session.get(f"/sport/drawmatches.aspx?id={league.id}&draw={draw}")
    )
    team_matches = filter_team_matches(schedule, team_name)
    if not team_matches:
        print(f"No matches found for {team_name}.")
        sys.exit(1)

    return team_name, team_matches, league


def main():
    print("competitie-sync — toernooi.nl team calendar exporter\n")
    session = Session()

    team_name, team_matches, league = select_team_matches(session)

    ics, skipped = build_ics(team_matches, team_name, league.id)
    filename = f"{slugify(team_name)}.ics"
    with open(filename, "w", encoding="utf-8", newline="") as fh:
        fh.write(ics)

    scheduled = len(team_matches) - skipped
    print(f"\nWrote {filename}: {scheduled} events", end="")
    if skipped:
        print(f" ({skipped} match(es) without a date/time skipped)", end="")
    print(".")
    print("Import it into Google Calendar; re-run later to sync updated times.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(130)
