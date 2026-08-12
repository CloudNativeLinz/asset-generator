PYTHON ?= python3
PIP ?= $(PYTHON) -m pip
TEMPLATE ?= assets/templates/save-the-date.yaml
EVENTS_FILE ?= _data/events.yml
OUT_DIR ?= artifacts
EVENT_ID ?=
WIDTH ?=
FORMAT ?= jpg
HOST ?= 0.0.0.0
PORT ?= 8000
PRESET ?= speaker-spotlight
FPS ?= 12
MEETUP_TEMPLATE ?= assets/templates/meetup.yaml
SPEAKER_TEMPLATE ?= assets/templates/speaker.yaml
ANIMATIONS ?=

.DEFAULT_GOAL := help

.PHONY: help install install-dev install-animations lint format test list-events generate generate-all generate-bundle generate-slides generate-animations run preview clean

help:
	@echo "Available targets:"
	@echo "  install       Install runtime dependencies"
	@echo "  install-dev   Install project with dev dependencies"
	@echo "  install-animations Install project with dev and animation dependencies"
	@echo "  lint          Run Ruff linter"
	@echo "  format        Run Black formatter"
	@echo "  test          Run pytest"
	@echo "  list-events   List events from EVENTS_FILE"
	@echo "  generate      Generate one event image (requires EVENT_ID)"
	@echo "  generate-all  Generate images for all events"
	@echo "  generate-bundle     Generate images, social copy, and slides (requires EVENT_ID)"
	@echo "  generate-slides     Generate a slide deck PDF (requires EVENT_ID)"
	@echo "  generate-animations Generate animated clips (requires EVENT_ID)"
	@echo "  run           Start local preview web app"
	@echo "  clean         Remove caches and generated artifacts"
	@echo ""
	@echo "Common overrides:"
	@echo "  make generate EVENT_ID=44 WIDTH=550 FORMAT=jpg"
	@echo "  make generate-all EVENTS_FILE=_data/sample-events.yml"
	@echo "  make generate-bundle EVENT_ID=44 ANIMATIONS='speaker-spotlight event-teaser'"
	@echo "  make run EVENTS_FILE=_data/sample-events.yml EVENT_ID=52 PORT=8000"

install:
	$(PIP) install --break-system-packages -e .

install-dev:
	$(PIP) install --break-system-packages -e .[dev]

install-animations:
	$(PIP) install --break-system-packages -e .[dev,animations]

lint:
	ruff check src tests

format:
	black src tests

test:
	$(PYTHON) -m pytest -q

list-events:
	imagegen list-events --file $(EVENTS_FILE)

generate:
	@if [ -z "$(EVENT_ID)" ]; then \
		echo "EVENT_ID is required. Example: make generate EVENT_ID=44"; \
		exit 1; \
	fi
	imagegen generate --template $(TEMPLATE) --file $(EVENTS_FILE) --out $(OUT_DIR) --id $(EVENT_ID) $(if $(WIDTH),--width $(WIDTH),) --format $(FORMAT)

generate-all:
	imagegen generate --template $(TEMPLATE) --file $(EVENTS_FILE) --out $(OUT_DIR) $(if $(WIDTH),--width $(WIDTH),) --format $(FORMAT)

generate-bundle:
	@if [ -z "$(EVENT_ID)" ]; then \
		echo "EVENT_ID is required. Example: make generate-bundle EVENT_ID=44"; \
		exit 1; \
	fi
	imagegen generate-bundle --template $(MEETUP_TEMPLATE) --speaker-template $(SPEAKER_TEMPLATE) --file $(EVENTS_FILE) --out $(OUT_DIR) --id $(EVENT_ID) $(if $(WIDTH),--width $(WIDTH),) --format $(FORMAT) $(foreach preset,$(ANIMATIONS),--animation $(preset))

generate-slides:
	@if [ -z "$(EVENT_ID)" ]; then \
		echo "EVENT_ID is required. Example: make generate-slides EVENT_ID=44"; \
		exit 1; \
	fi
	imagegen generate-slides --file $(EVENTS_FILE) --out $(OUT_DIR) --id $(EVENT_ID) $(if $(WIDTH),--width $(WIDTH),)

generate-animations:
	@if [ -z "$(EVENT_ID)" ]; then \
		echo "EVENT_ID is required. Example: make generate-animations EVENT_ID=44 PRESET=speaker-spotlight"; \
		exit 1; \
	fi
	imagegen generate-animations --file $(EVENTS_FILE) --out $(OUT_DIR) --id $(EVENT_ID) --preset $(PRESET) --fps $(FPS) $(if $(WIDTH),--width $(WIDTH),)

run:
	imagegen preview --template $(TEMPLATE) --file $(EVENTS_FILE) $(if $(EVENT_ID),--id $(EVENT_ID),) --host $(HOST) --port $(PORT)

preview: run

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache .cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete
