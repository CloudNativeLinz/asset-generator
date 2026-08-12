FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir .

COPY _data ./_data
COPY assets ./assets

RUN useradd --create-home --uid 10001 imagegen \
    && mkdir -p /app/artifacts /app/.cache/images /app/assets/speaker-images \
    && chown -R imagegen:imagegen \
        /app/artifacts \
        /app/.cache \
        /app/assets/speaker-images

USER imagegen

EXPOSE 8000

CMD ["imagegen", "preview", "--template", "assets/templates/save-the-date.yaml", "--file", "_data/events.yml", "--host", "0.0.0.0", "--port", "8000"]