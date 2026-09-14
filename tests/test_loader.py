from pathlib import Path

from imagegen.loader import load_events


def test_load_events_resolves_legacy_speaker_image_to_website_repo(tmp_path: Path) -> None:
    events_file = tmp_path / "events.yml"
    events_file.write_text(
        """
- id: 46
  title: "Event"
  talks:
    - title: "Talk 1"
      speaker: "Speaker 1"
      image: "/assets/speaker-images/46-1.png"
""".strip(),
        encoding="utf-8",
    )

    events = load_events(str(events_file))

    assert events[0].talks[0].image == (
        "https://raw.githubusercontent.com/CloudNativeLinz/"
        "cloudnativelinz.github.io/refs/heads/main/images/speakers/46-1.png"
    )


def test_load_events_resolves_canonical_speaker_image_to_website_repo(tmp_path: Path) -> None:
    events_file = tmp_path / "events.yml"
    events_file.write_text(
        """
- id: 99
  title: "Event"
  talks:
  - title: "Talk 1"
    speaker: "Speaker 1"
    image: "/images/speakers/profile.webp"
""".strip(),
        encoding="utf-8",
    )

    events = load_events(str(events_file))

    assert events[0].talks[0].image == (
        "https://raw.githubusercontent.com/CloudNativeLinz/"
        "cloudnativelinz.github.io/refs/heads/main/images/speakers/profile.webp"
    )


def test_load_events_preserves_external_speaker_image_url(tmp_path: Path) -> None:
    events_file = tmp_path / "events.yml"
    events_file.write_text(
        """
- id: 99
  title: "Event"
  talks:
  - title: "Talk 1"
    speaker: "Speaker 1"
    image: "https://example.com/profile.jpg"
""".strip(),
        encoding="utf-8",
    )

    events = load_events(str(events_file))

    assert events[0].talks[0].image == "https://example.com/profile.jpg"


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
