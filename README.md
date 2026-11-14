# concert-alerts

Get a message when an artist in your music library announces a concert in your country.

It reads your artists (a [Navidrome](https://www.navidrome.org/) database or a plain text list),
checks Ticketmaster, Resident Advisor and DICE, and sends a digest of new and changed dates
through any command you choose (by default [Hermes](https://github.com/NousResearch/hermes-agent)
to Telegram). It runs once, so schedule it daily with systemd or cron.

```
Concerts · 1/1 · 2 new dates
Next 365 days · ★ preferred areas · local times

Four Tet · 2 dates
• 27 Nov 2026 · ★ Barcelona · Razzmatazz · 23:00 · Event / tickets
• 29 Nov 2026 · Valencia · Sala X · 22:00 · Event / tickets

Source: Resident Advisor, Ticketmaster
```

## Install

Python 3.11+.

```sh
uv tool install git+https://github.com/mateo19182/concert-alerts
# or: pipx install git+https://github.com/mateo19182/concert-alerts
```

## Configure

```sh
install -d -m 700 ~/.config/concert-alerts
install -m 600 examples/config.example.json ~/.config/concert-alerts/config.json
```

The configuration must be mode 600 because it holds your Ticketmaster key. Relative paths are
resolved from its directory. Use `--config PATH` or `CONCERT_ALERTS_CONFIG` to put it elsewhere.

| Key | Default | Meaning |
| --- | --- | --- |
| `navidrome_db` | | Navidrome's `navidrome.db`, opened read-only. |
| `artists_file` | | Instead of Navidrome: one artist per line, optionally `name<TAB>MusicBrainz ID`; `#` lines are comments. |
| `ticketmaster_api_key` | | Consumer Key of a free [Ticketmaster developer](https://developer.ticketmaster.com/) app. |
| `country` | `ES` | ISO 3166 code; only venues confirmed in this country are kept. |
| `timezone` | `Europe/Madrid` | Used when a DICE start time has no offset. |
| `preferred_areas` | `[]` | Areas marked ★ and always shown. See below. |
| `max_nationwide_dates` | `3` | Artists with more upcoming dates than this are only shown in preferred areas. `0` shows everything. |
| `lookahead_days` | `365` | Search window, 1–730. |
| `ra_enabled` | `false` | Add Resident Advisor. |
| `dice_enabled`, `dice_notify` | `false` | Add DICE to the report; `dice_notify` also sends its dates. |
| `dice_places` | Spanish cities | City slugs that select DICE event URLs, required outside Spain. |
| `dice_page_budget` | `150` | DICE event pages fetched per run. |
| `artist_overrides` | `{}` | Provider artist ID → library artist ID, for ambiguous names. |
| `notify_command` | `["hermes", "send", "-q", "--to", "telegram"]` | Run with the message appended as the last argument. Exit 0 means delivered. |
| `user_agent` | `concert-alerts/<version>` | Sent to RA and DICE. |
| `state_db`, `report` | `state/events.db`, `state/latest.json` | Delivery history and the last report. |

A preferred area matches on any of its city names, state/province names, state codes
(Ticketmaster's, without the country prefix) or postcode prefixes. The first matching area
labels the event. [`examples/preferred-areas.spain.json`](examples/preferred-areas.spain.json)
covers Galicia, Madrid and Barcelona:

```json
"preferred_areas": [
  {"label": "Madrid", "cities": ["Madrid"], "states": ["Comunidad de Madrid"],
   "state_codes": ["M", "MD"], "postcodes": ["28"]}
]
```

Messages are Telegram HTML (`<b>`, `<a>`), at most about 3,800 characters each. Any notifier that
accepts that works, for example a short script calling the Telegram Bot API.

## Run

```sh
concert-alerts library        # check the artist list
concert-alerts sync           # dry run: writes the report, sends nothing
concert-alerts sync --send    # send pending dates and mark them delivered
```

Review `state/latest.json` before the first `--send`: `events` are the matches,
`unresolved_artists` are provider names that matched nothing or more than one artist, and
`sources` shows each provider's status. A dry run never consumes pending dates.

[`deploy/`](deploy) has systemd user units for a daily run at 18:00 and a failure alert.
Copy them to `~/.config/systemd/user/`, adjust the paths and the alert command, then
`systemctl --user enable --now concert-alerts.timer`.

## How it decides what to send

- **Matching.** MusicBrainz IDs when the provider gives them, otherwise exact names after Unicode
  and case normalisation. No fuzzy matching, no splitting of "A, B" credits, no guessing from event
  titles. Ambiguous names need an `artist_overrides` entry (`ra:<id>`, `dice:<slug>` or the
  Ticketmaster attraction ID).
- **Updates.** A date is sent again only if its date, time, venue, matched lineup or status
  (cancelled, postponed, rescheduled) changes. Going on sale, title or URL changes are not updates.
  A listing that disappears is never reported as cancelled.
- **Duplicates.** The same show from two sources (same local date and time, city, venue and a shared
  artist) is merged and alerted once.
- **Long tours.** Artists with many dates are limited to preferred areas; hidden dates stay pending,
  and each group says how many other dates were hidden.
- **Failures.** A source that fails is reported in the run and, when sending, in an extra
  "check incomplete" message; the others still run. If all fail, nothing is sent and the command
  exits non-zero. Every run writes `run-status.json` beside the report. Delivery is at least once.

## Sources

- **Ticketmaster** [Discovery API](https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/):
  throttled to its 5 requests/second and bounded per run; large windows are split to stay under
  its 1,000-result paging limit.
- **Resident Advisor**: RA's unofficial GraphQL endpoint, using the query approach of
  [Cuepoint](https://github.com/danilenzo/cuepoint) (MIT, see `THIRD_PARTY_NOTICES`). Covers every
  RA area in the country. Only linked RA artists are matched. Results are cached for six hours.
- **DICE**: DICE's public sitemaps and the schema.org data on each event page, two seconds between
  requests, only new or changed pages. DICE has no public listings API; the author uses it with
  DICE's permission, so ask DICE before enabling it. Fill the cache once outside the timer with
  `concert-alerts dice-cache --pages 1500`.

Coverage is never complete: other ticket sites, unlinked artists and undated announcements are
missed. No result means unknown, not "no concerts".

## Development

```sh
uv sync --group dev
uv run pytest -q
```

Tests use fixture libraries, mocked HTTP and fake notifiers; they make no network calls.
