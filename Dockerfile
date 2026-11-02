ARG BASE_IMAGE=python:3.12-alpine

FROM ${BASE_IMAGE} AS builder

# зависимости сборки
RUN set -eu; \
    if command -v apk >/dev/null 2>&1; then \
        apk add --no-cache ca-certificates build-base; \
    elif command -v apt-get >/dev/null 2>&1; then \
        apt-get update; \
        apt-get install -y --no-install-recommends \
            ca-certificates build-essential; \
        rm -rf /var/lib/apt/lists/*; \
    else \
        echo "Supported package managers: apk, apt-get" >&2; \
        exit 1; \
    fi

COPY requirements.txt /requirements.txt

# venv
RUN python -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install --no-cache-dir \
        -r /requirements.txt \
    && /opt/venv/bin/python -m pip check

FROM ${BASE_IMAGE} AS runtime

ARG APP_UID=10001
ARG APP_GID=10001

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY src ./src

# пользователь и права доступа
RUN set -eu; \
    if command -v apk >/dev/null 2>&1; then \
        addgroup -g "$APP_GID" app; \
        adduser -D -u "$APP_UID" -G app \
            -h /home/app -s /bin/false app; \
    else \
        groupadd --gid "$APP_GID" app; \
        useradd --uid "$APP_UID" --gid "$APP_GID" \
            --create-home --shell /bin/false app; \
    fi; \
    mkdir -p /app/data /app/logs; \
    chmod -R u=rwX,go=rX /app/src /opt/venv; \
    chown -R app:app /app/data /app/logs /home/app; \
    chmod 0750 /app/data /app/logs

USER ${APP_UID}:${APP_GID}

STOPSIGNAL SIGTERM
ENTRYPOINT ["/opt/venv/bin/python", "-m", "src.main"]
CMD []
