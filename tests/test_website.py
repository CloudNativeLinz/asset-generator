from datetime import date
from pathlib import Path

import pytest
import yaml
from PIL import Image
from typer.testing import CliRunner

from imagegen.cli import app
from imagegen.loader import load_events, resolve_event_images
from imagegen.website import generate_website_images

TODAY = date(2026, 11, 5)


def write_events(path: Path, events: list[dict]) -> str:
    path.write_text(yaml.safe_dump(events), encoding="utf-8")
    return str(path)


@pytest.fixture
def render_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    calls: list[tuple] = []

    def fake_render(event, preset, **kwargs):
        calls.append((event, preset, kwargs))
        size = (1080, 610) if preset == "meetup-website" else (1166, 200)
        return Image.new("RGB", size)

    monkeypatch.setattr("imagegen.website.render_promotion", fake_render)
    return calls


def test_change_detection_normalizes_data_and_preserves_website_metadata(
    tmp_path: Path, render_calls: list[tuple]
) -> None:
    base = write_events(
        tmp_path / "base.yml",
        [
            {"id": 1, "date": TODAY, "doors_open": "17:30", "host": None},
            {"id": 2, "title": "Old"},
            {"id": 3, "description": "Old website metadata"},
            {"id": 9},
        ],
    )
    current = write_events(
        tmp_path / "current.yml",
        [
            {"id": 4},
            {"id": 3, "description": "New website metadata"},
            {"id": 2, "title": "New"},
            {"host": "", "time": "17:30", "date": TODAY.isoformat(), "id": "1"},
        ],
    )
    result = generate_website_images(
        current, str(tmp_path / "out"), base_events_file=base, today=TODAY
    )
    assert result.generated == [4, 3, 2]
    assert result.skipped == {1: "unchanged"}
    assert len(render_calls) == 6


@pytest.mark.parametrize("base_content", [None, "", "# empty\n", "[]\n"])
def test_absent_or_empty_base_means_all_changed(
    tmp_path: Path, render_calls: list[tuple], base_content: str | None
) -> None:
    current = write_events(tmp_path / "events.yml", [{"id": 1}])
    base = None
    if base_content is not None:
        path = tmp_path / "base.yml"
        path.write_text(base_content, encoding="utf-8")
        base = str(path)
    assert generate_website_images(
        current, str(tmp_path / "out"), base_events_file=base, today=TODAY
    ).generated == [1]


def test_date_cutoff_and_opt_out(tmp_path: Path, render_calls: list[tuple]) -> None:
    current = write_events(
        tmp_path / "events.yml",
        [
            {"id": 1, "date": "2026-11-04"},
            {"id": 2, "date": TODAY},
            {"id": 3, "date": "2026-11-06"},
            {"id": 4},
            {"id": 5, "date": None},
            {"id": 6, "generate_images": False},
        ],
    )
    result = generate_website_images(current, str(tmp_path / "out"), today=TODAY)
    assert result.generated == [2, 3, 4, 5]
    assert result.skipped == {1: "past event", 6: "generate_images: false"}
    assert not load_events(current)[0].generate_images


@pytest.mark.parametrize("field", ["title", "speaker", "image", "description"])
def test_nested_talk_changes_are_detected(
    tmp_path: Path, render_calls: list[tuple], field: str
) -> None:
    base = write_events(tmp_path / "base.yml", [{"id": 1, "talks": [{field: "before"}]}])
    current = write_events(tmp_path / "events.yml", [{"id": 1, "talks": [{field: "after"}]}])
    result = generate_website_images(
        current, str(tmp_path / "out"), base_events_file=base, today=TODAY
    )
    assert result.generated == [1]


def test_explicit_ids_bypass_only_change_detection(
    tmp_path: Path, render_calls: list[tuple]
) -> None:
    current = write_events(
        tmp_path / "events.yml",
        [
            {"id": 1},
            {"id": 2, "date": "2020-01-01"},
            {"id": 3, "generate_images": False},
            {"id": 4},
        ],
    )
    result = generate_website_images(
        current,
        str(tmp_path / "out"),
        base_events_file=str(tmp_path / "missing-base.yml"),
        today=TODAY,
        event_ids=[1, 1, 2, 3],
    )
    assert result.generated == [1]
    assert result.skipped == {2: "past event", 3: "generate_images: false", 4: "not requested"}


def test_native_output_naming_and_format(tmp_path: Path, render_calls: list[tuple]) -> None:
    current = write_events(tmp_path / "events.yml", [{"id": 7}])
    out = tmp_path / "images" / "events"
    generate_website_images(current, str(out), today=TODAY)
    assert {path.name for path in out.iterdir()} == {"7.jpg", "7-teaser.jpg"}
    for filename, size in [("7.jpg", (1080, 610)), ("7-teaser.jpg", (1166, 200))]:
        with Image.open(out / filename) as image:
            assert image.format == "JPEG"
            assert image.size == size
    assert [preset for _, preset, _ in render_calls] == ["meetup-website", "teaser"]
    assert all(
        kwargs == {"variant": "auto", "output_format": "jpg"} for _, _, kwargs in render_calls
    )


def test_real_render_uses_local_portrait(tmp_path: Path) -> None:
    portrait = tmp_path / "images" / "speakers" / "photo.png"
    portrait.parent.mkdir(parents=True)
    Image.new("RGB", (200, 300), "red").save(portrait)
    current = write_events(
        tmp_path / "events.yml",
        [{"id": 7, "talks": [{"speaker": "Speaker", "image": "/images/speakers/photo.png"}]}],
    )
    generate_website_images(current, str(tmp_path / "out"), site_root=str(tmp_path), today=TODAY)
    with Image.open(tmp_path / "out" / "7.jpg") as image:
        red, green, blue = image.getpixel((145, 180))
        assert red > 240 and green < 10 and blue < 10


def test_site_root_resolves_all_image_fields_without_mutating_data(tmp_path: Path) -> None:
    image = tmp_path / "images" / "speakers" / "photo.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"local image")
    source = "/images/speakers/photo.png"
    raw = [
        {
            "id": 1,
            "sponsor_logo": source,
            "sponsors": [{"logo": source}],
            "talks": [
                {
                    "image": "/assets/speaker-images/photo.png",
                    "images": [source, "/images/speakers/missing.png", "https://example.com/a.png"],
                }
            ],
        }
    ]
    resolved = resolve_event_images(raw, str(tmp_path))[0]
    assert resolved["sponsor_logo"] == str(image.resolve())
    assert resolved["sponsors"][0]["logo"] == str(image.resolve())
    talk = resolved["talks"][0]
    assert talk["image"] == str(image.resolve())
    assert talk["images"][0] == str(image.resolve())
    assert talk["images"][1].endswith("/images/speakers/missing.png")
    assert talk["images"][1].startswith("https://raw.githubusercontent.com/")
    assert talk["images"][2] == "https://example.com/a.png"
    assert raw[0]["sponsor_logo"] == source


def test_site_root_rejects_path_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="escapes --site-root"):
        resolve_event_images([{"talks": [{"image": "/images/../../secret.png"}]}], str(tmp_path))


def test_cli_repeatable_ids_and_summary(tmp_path: Path, render_calls: list[tuple]) -> None:
    current = write_events(tmp_path / "events.yml", [{"id": 1}, {"id": 2}, {"id": 3}])
    result = CliRunner().invoke(
        app,
        [
            "website-images",
            "--events-file",
            current,
            "--out-dir",
            str(tmp_path / "out"),
            "--today",
            TODAY.isoformat(),
            "--base-events-file",
            current,
            "--event-id",
            "1",
            "--event-id",
            "2",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Generated 2 event(s): 1, 2" in result.output
    assert "Skipped 1 event(s): 3 (not requested)" in result.output


@pytest.mark.parametrize("contents", ["", "[]", "# empty\n"])
def test_empty_current_is_success_without_remote_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, contents: str
) -> None:
    def unexpected_fetch():
        pytest.fail("Empty current file must not fetch remote events")

    monkeypatch.setattr("imagegen.loader._fetch_remote_events", unexpected_fetch)
    current = tmp_path / "events.yml"
    current.write_text(contents, encoding="utf-8")
    result = CliRunner().invoke(
        app,
        [
            "website-images",
            "--events-file",
            str(current),
            "--out-dir",
            str(tmp_path / "out"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Generated 0 event(s): none" in result.output
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    "contents,error",
    [
        ("{}", "YAML list"),
        ("false", "YAML list"),
        ("- invalid", "event mappings"),
        ("- id: 1\n- id: 1", "Duplicate event"),
        ("- id: 1\n  date: tomorrow", "invalid date"),
        ("[invalid", "Error"),
    ],
)
def test_cli_reports_invalid_input(tmp_path: Path, contents: str, error: str) -> None:
    current = tmp_path / "events.yml"
    current.write_text(contents, encoding="utf-8")
    result = CliRunner().invoke(
        app,
        [
            "website-images",
            "--events-file",
            str(current),
            "--out-dir",
            str(tmp_path / "out"),
        ],
    )
    assert result.exit_code != 0
    assert error in result.output


def test_cli_unknown_id_and_invalid_today(tmp_path: Path) -> None:
    current = write_events(tmp_path / "events.yml", [{"id": 1}])
    args = ["website-images", "--events-file", current, "--out-dir", str(tmp_path / "out")]
    unknown = CliRunner().invoke(app, [*args, "--event-id", "99"])
    assert unknown.exit_code != 0
    assert "Unknown --event-id: 99" in unknown.output
    invalid = CliRunner().invoke(app, [*args, "--today", "tomorrow"])
    assert invalid.exit_code != 0
    assert "YYYY-MM-DD" in invalid.output


def test_no_changes_leaves_existing_outputs_untouched(
    tmp_path: Path, render_calls: list[tuple]
) -> None:
    current = write_events(tmp_path / "events.yml", [{"id": 1}])
    out = tmp_path / "out"
    out.mkdir()
    existing = out / "1.jpg"
    existing.write_bytes(b"manual image")
    result = generate_website_images(current, str(out), base_events_file=current, today=TODAY)
    assert result.generated == []
    assert result.skipped == {1: "unchanged"}
    assert existing.read_bytes() == b"manual image"
    assert not render_calls


def test_cli_missing_input_fails(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "website-images",
            "--events-file",
            str(tmp_path / "missing.yml"),
            "--out-dir",
            str(tmp_path / "out"),
        ],
    )
    assert result.exit_code != 0
    assert "missing.yml" in result.output
