import json
import sys
from datetime import datetime, timezone

import httpx
import pytest

from concert_alerts.__main__ import main, read_config, sync
from concert_alerts.dice import place_pattern, place_slug
from concert_alerts.events import select_events
from concert_alerts.library import Artist, ArtistIndex, artist_file_catalogue
from concert_alerts.notify import send_message
from concert_alerts.region import Region
from concert_alerts.ticketmaster import Ticketmaster


def write_config(tmp_path, **data):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data))
    path.chmod(0o600)
    return path


def test_artist_file_skips_comments_and_duplicates_and_reads_mbids(tmp_path):
    path = tmp_path / "artists.txt"
    path.write_text("# mine\nFour Tet\tmb-four-tet\n\nFour Tet\n#1 Dads\n  Vulfpeck  \n")
    artists, issues = artist_file_catalogue(path)
    assert [(a.id, a.name, a.mbid) for a in artists] == [("Four Tet", "Four Tet", "mb-four-tet"),
                                                         ("Vulfpeck", "Vulfpeck", "")]
    assert issues == []
    assert ArtistIndex(artists).match({"id": "x", "name": "VULFPECK"})[0].name == "Vulfpeck"


def test_config_needs_a_library_and_resolves_paths_beside_itself(tmp_path):
    with pytest.raises(ValueError, match="navidrome_db or artists_file"):
        read_config(write_config(tmp_path))
    config = read_config(write_config(tmp_path, artists_file="artists.txt"))
    assert config["artists_file"] == tmp_path / "artists.txt"
    assert config["state_db"] == tmp_path / "state/events.db"
    assert config["report"] == tmp_path / "state/latest.json"
    assert config["notify_command"] == ("hermes", "send", "-q", "--to", "telegram")
    for bad in ({"country": "Spain"}, {"notify_command": []}, {"preferred_areas": [{"cities": ["X"]}]}):
        with pytest.raises(ValueError):
            read_config(write_config(tmp_path, artists_file="a.txt", **bad))


def test_country_and_areas_are_configurable(event_pt):
    region = Region.from_config({"country": "pt", "preferred_areas": [
        {"label": "Lisboa", "cities": ["Lisboa"]}, {"label": "Norte", "state_codes": ["13"], "postcodes": ["4"]}]})
    index = ArtistIndex([Artist("four", "Four Tet")])
    assert select_events([event_pt], index)[0] == []  # default country is ES
    selected = select_events([event_pt], index, region)[0]
    assert selected[0]["country"] == "PT" and selected[0]["highlight"] == "Lisboa"
    assert region.highlight("Braga", state_code="PT-13") == "Norte"
    assert region.highlight("Porto", postcode="4000-123") == "Norte"
    assert region.highlight("Faro") == ""


def test_ticketmaster_queries_the_configured_country():
    def handler(request):
        assert request.url.params["countryCode"] == "PT"
        return httpx.Response(200, json={"page": {"totalElements": 0}})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    start = datetime(2027, 1, 1, tzinfo=timezone.utc)
    assert Ticketmaster("k", client=client, sleep=lambda _: None, country="PT").events(start, start) == []


def test_dice_places_are_configurable():
    lisbon = "https://dice.fm/event/abc-show-lux-fragil-lisboa-tickets"
    assert not place_slug(lisbon)
    assert place_slug(lisbon, place_pattern(["lisboa", "porto"]))


def test_sync_sends_through_the_configured_command(tmp_path, monkeypatch):
    artists = tmp_path / "artists.txt"
    artists.write_text("Four Tet\n")
    event = {"id": "1", "name": "Four Tet", "url": "https://example.com/t",
             "dates": {"start": {"localDate": "2027-07-10", "localTime": "20:00:00"}, "status": {"code": "onsale"}},
             "_embedded": {"attractions": [{"id": "a", "name": "Four Tet"}],
                           "venues": [{"name": "V", "city": {"name": "Sevilla"}, "country": {"countryCode": "ES"}}]}}
    script = tmp_path / "notify.py"
    out = tmp_path / "sent.txt"
    script.write_text(f"import sys\nopen({str(out)!r}, 'a').write(sys.argv[-1])\n")
    config = {"artists_file": artists, "state_db": tmp_path / "events.db", "report": tmp_path / "latest.json",
              "notify_command": [sys.executable, str(script)]}

    class OneEvent:
        requests = 1
        def __init__(self, key, **options): pass
        def events(self, start, end): return [event]
        def close(self): pass
    assert sync(config, send=True, provider_factory=OneEvent)["sent_events"] == 1
    assert "Four Tet" in out.read_text() and "Sevilla" in out.read_text()


def test_failing_notifier_keeps_the_notification_pending(tmp_path):
    with pytest.raises(RuntimeError, match="Notifier could not confirm"):
        send_message("hi", (sys.executable, "-c", "raise SystemExit(1)"))
    with pytest.raises(RuntimeError, match="Notifier is unavailable"):
        send_message("hi", ("definitely-not-a-command-xyz",))


def test_library_command_reads_an_artist_file(tmp_path, capsys):
    (tmp_path / "artists.txt").write_text("Four Tet\nVulfpeck\n")
    assert main(["--config", str(write_config(tmp_path, artists_file="artists.txt")), "library"]) == 0
    assert json.loads(capsys.readouterr().out)["library_artists"] == 2


@pytest.fixture
def event_pt():
    return {"id": "pt-1", "name": "Four Tet", "url": "https://example.com/t",
            "dates": {"start": {"localDate": "2027-07-10", "localTime": "20:00:00"}, "status": {"code": "onsale"}},
            "_embedded": {"attractions": [{"id": "a", "name": "Four Tet"}],
                          "venues": [{"name": "Lux", "city": {"name": "Lisboa"}, "country": {"countryCode": "PT"}}]}}
