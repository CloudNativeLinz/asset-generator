import json
from pathlib import Path

import pytest

from imagegen.google_slides import (
    GoogleSlidesError,
    agenda_items,
    event_replacements,
    extract_presentation_id,
    generate_google_slides,
    resolve_google_access_token,
)
from imagegen.loader import find_event, load_events


class FakeResponse:
    def __init__(self, body: dict, status_code: int = 200) -> None:
        self._body = body
        self.status_code = status_code
        self.text = json.dumps(body)

    def json(self) -> dict:
        return self._body


def test_extract_presentation_id_accepts_url_and_id() -> None:
    presentation_id = "1AbCdEfGhIjKlMnOp"

    assert extract_presentation_id(presentation_id) == presentation_id
    assert (
        extract_presentation_id(
            f"https://docs.google.com/presentation/d/{presentation_id}/edit#slide=id.p"
        )
        == presentation_id
    )

    with pytest.raises(GoogleSlidesError):
        extract_presentation_id("https://example.com/not-a-presentation")


def test_event_replacements_include_indexed_talks() -> None:
    event = find_event(load_events("_data/sample-events.yml"), 32)

    replacements = event_replacements(event)

    assert replacements["event.title"] == "Test Event"
    assert replacements["event.talk_count"] == "2"
    assert replacements["talks.1.title"] == "Test Talk 1"
    assert replacements["talks.2.speaker"] == "Test Speaker 2"


def test_agenda_items_include_talk_titles_speakers_and_timing() -> None:
    event = find_event(load_events("_data/sample-events.yml"), 32)

    assert agenda_items(event) == [
        ("18:00", "Opening"),
        ("18:10", "Test Talk 1\nTest Speaker 1"),
        ("18:55", "5-minute break"),
        ("19:00", "Test Talk 2\nTest Speaker 2"),
        ("19:45", "Raffle + networking"),
    ]


def test_explicit_access_token_does_not_require_credentials_file(monkeypatch) -> None:
    monkeypatch.delenv("GOOGLE_DRIVE_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)

    assert resolve_google_access_token(access_token="token") == "token"


def test_service_account_credentials_can_be_loaded_from_dotenv(tmp_path: Path, monkeypatch) -> None:
    credentials_path = tmp_path / "service-account.json"
    credentials_path.write_text(
        json.dumps(
            {
                "client_email": "slides@example.iam.gserviceaccount.com",
                "private_key": "private-key",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        f'GOOGLE_APPLICATION_CREDENTIALS="{credentials_path}"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GOOGLE_DRIVE_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setattr("imagegen.google_slides.jwt.encode", lambda *args, **kwargs: "assertion")

    def fake_post(url: str, *, data: dict, timeout: int) -> FakeResponse:
        return FakeResponse({"access_token": "dotenv-token"})

    monkeypatch.setattr("imagegen.google_slides.requests.post", fake_post)

    assert resolve_google_access_token() == "dotenv-token"


def test_service_account_credentials_are_exchanged_automatically(
    tmp_path: Path, monkeypatch
) -> None:
    credentials_path = tmp_path / "service-account.json"
    credentials_path.write_text(
        json.dumps(
            {
                "client_email": "slides@example.iam.gserviceaccount.com",
                "private_key": "private-key",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.delenv("GOOGLE_DRIVE_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr("imagegen.google_slides.jwt.encode", lambda *args, **kwargs: "assertion")

    def fake_post(url: str, *, data: dict, timeout: int) -> FakeResponse:
        assert url == "https://oauth2.googleapis.com/token"
        assert data["assertion"] == "assertion"
        assert timeout == 30
        return FakeResponse({"access_token": "service-account-token"})

    monkeypatch.setattr("imagegen.google_slides.requests.post", fake_post)

    assert (
        resolve_google_access_token(credentials_file=str(credentials_path))
        == "service-account-token"
    )


def test_generate_google_slides_copies_template_and_replaces_text(
    tmp_path: Path, monkeypatch
) -> None:
    event = find_event(load_events("_data/sample-events.yml"), 32)
    requests: list[tuple[str, dict]] = []

    def fake_post(url: str, *, headers: dict, json: dict, timeout: int) -> FakeResponse:
        assert headers["Authorization"] == "Bearer token"
        assert timeout == 45
        requests.append((url, json))
        if "/copy?" in url:
            return FakeResponse({"id": "generated-presentation"})
        return FakeResponse({"replies": []})

    def fake_get(url: str, *, headers: dict, timeout: int) -> FakeResponse:
        assert url.endswith("/presentations/generated-presentation")
        return FakeResponse({"slides": [{"objectId": "titleSlide"}]})

    monkeypatch.setattr("imagegen.google_slides.requests.post", fake_post)
    monkeypatch.setattr("imagegen.google_slides.requests.get", fake_get)

    deck = generate_google_slides(
        event,
        template="source-presentation",
        access_token="token",
        output_dir=str(tmp_path),
        folder_id="destination-folder",
    )

    assert deck.presentation_id == "generated-presentation"
    assert deck.url.endswith("/generated-presentation/edit")
    assert requests[0][1]["parents"] == ["destination-folder"]
    replacement_requests = requests[1][1]["requests"]
    assert any(
        request["replaceAllText"]["containsText"]["text"] == "{{ event.title }}"
        and request["replaceAllText"]["replaceText"] == "Test Event"
        for request in replacement_requests
    )
    assert any(
        request.get("createSlide", {}).get("objectId") == "imagegenAgenda32"
        for request in replacement_requests
    )
    metadata = json.loads((tmp_path / "32" / "google-slides.json").read_text())
    assert metadata["url"] == deck.url


def test_generate_google_slides_explains_service_account_quota_failure(
    tmp_path: Path, monkeypatch
) -> None:
    event = find_event(load_events("_data/sample-events.yml"), 32)

    def fake_post(url: str, *, headers: dict, json: dict, timeout: int) -> FakeResponse:
        return FakeResponse(
            {"error": {"errors": [{"reason": "storageQuotaExceeded"}]}},
            status_code=403,
        )

    monkeypatch.setattr("imagegen.google_slides.requests.post", fake_post)

    with pytest.raises(GoogleSlidesError, match="Shared Drive destination"):
        generate_google_slides(
            event,
            template="source-presentation",
            access_token="token",
            output_dir=str(tmp_path),
        )


def test_generate_google_slides_reuses_event_presentation_after_quota_failure(
    tmp_path: Path, monkeypatch
) -> None:
    event = find_event(load_events("_data/sample-events.yml"), 32)
    posted_urls: list[str] = []

    def fake_post(url: str, *, headers: dict, json: dict, timeout: int) -> FakeResponse:
        posted_urls.append(url)
        if "/copy?" in url:
            return FakeResponse(
                {"error": {"errors": [{"reason": "storageQuotaExceeded"}]}},
                status_code=403,
            )
        return FakeResponse({"replies": []})

    def fake_get(
        url: str, *, headers: dict, timeout: int, params: dict | None = None
    ) -> FakeResponse:
        if url.endswith("/drive/v3/files"):
            assert params is not None
            assert "name = '32'" in params["q"]
            assert "'destination-folder' in parents" in params["q"]
            return FakeResponse({"files": [{"id": "existing-presentation", "name": "32"}]})
        assert url.endswith("/presentations/existing-presentation")
        return FakeResponse({"slides": [{"objectId": "imagegenAgenda32"}]})

    monkeypatch.setattr("imagegen.google_slides.requests.post", fake_post)
    monkeypatch.setattr("imagegen.google_slides.requests.get", fake_get)

    deck = generate_google_slides(
        event,
        template="source-presentation",
        access_token="token",
        output_dir=str(tmp_path),
        folder_id="destination-folder",
    )

    assert deck.presentation_id == "existing-presentation"
    assert deck.name == "32"
    assert posted_urls[-1].endswith("/presentations/existing-presentation:batchUpdate")
