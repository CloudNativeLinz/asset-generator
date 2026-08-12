from pathlib import Path
from types import SimpleNamespace

from imagegen.loader import load_events


def test_load_events_prefers_local_speaker_image_for_remote_url(
    tmp_path: Path, monkeypatch
) -> None:
    events_file = tmp_path / "events.yml"
    events_file.write_text(
        """
- id: 46
  title: "Event"
  talks:
    - title: "Talk 1"
      speaker: "Speaker 1"
      image: "https://example.com/first.jpg"
    - title: "Talk 2"
      speaker: "Speaker 2"
      image: "https://example.com/second.jpg"
""".strip(),
        encoding="utf-8",
    )

    assets_dir = tmp_path / "assets" / "speaker-images"
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / "46-1.jpg").write_bytes(b"jpeg-placeholder")
    (assets_dir / "46-2.jpg").write_bytes(b"jpeg-placeholder")

    monkeypatch.chdir(tmp_path)

    events = load_events(str(events_file))

    assert events[0].talks[1].image == "/assets/speaker-images/46-2.jpg"


def test_load_events_downloads_remote_speaker_image_when_missing(
    tmp_path: Path, monkeypatch
) -> None:
    events_file = tmp_path / "events.yml"
    events_file.write_text(
        """
- id: 99
  title: "Event"
  talks:
  - title: "Talk 1"
    speaker: "Speaker 1"
    image: "https://example.com/profile"
""".strip(),
        encoding="utf-8",
    )

    def fake_get(url: str, timeout: int):
        assert url == "https://example.com/profile"
        assert timeout == 20
        return SimpleNamespace(
            status_code=200,
            content=b"fake-image-bytes",
            headers={"content-type": "image/jpeg"},
        )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("imagegen.loader.requests.get", fake_get)

    events = load_events(str(events_file))

    assert events[0].talks[0].image == "/assets/speaker-images/99-1.jpg"
    assert (tmp_path / "assets" / "speaker-images" / "99-1.jpg").exists()


def test_load_events_accepts_null_host_values(tmp_path: Path) -> None:
    events_file = tmp_path / "events.yml"
    events_file.write_text(
        """
- id: 7
  title: "Event with no host"
  host: null
  talks: []
""".strip(),
        encoding="utf-8",
    )

    events = load_events(str(events_file))

    assert len(events) == 1
    assert events[0].host == ""


def test_load_events_accepts_time_and_venue(tmp_path: Path) -> None:
    events_file = tmp_path / "events.yml"
    events_file.write_text(
        """
- id: 8
  title: "Save the Date"
  date: "2026-09-16"
  time: "17:30"
  venue: "Netcetera"
  address: "Example Street 1, 4020 Linz"
  host: "Netcetera"
  talks: []
""".strip(),
        encoding="utf-8",
    )

    event = load_events(str(events_file))[0]

    assert event.time == "17:30"
    assert event.venue == "Netcetera"
    assert event.address == "Example Street 1, 4020 Linz"


def test_load_events_normalizes_null_time_and_venue(tmp_path: Path) -> None:
    events_file = tmp_path / "events.yml"
    events_file.write_text(
        """
- id: 9
  title: "Event with incomplete details"
  time: null
  venue: null
  address: null
  talks: []
""".strip(),
        encoding="utf-8",
    )

    event = load_events(str(events_file))[0]

    assert event.time == ""
    assert event.venue == ""
    assert event.address == ""


def test_load_events_maps_doors_open_to_time(tmp_path: Path) -> None:
    events_file = tmp_path / "events.yml"
    events_file.write_text(
        """
- id: 10
  title: "Event using website schema"
  doors_open: "17:30"
  talks: []
""".strip(),
        encoding="utf-8",
    )

    event = load_events(str(events_file))[0]

    assert event.time == "17:30"
