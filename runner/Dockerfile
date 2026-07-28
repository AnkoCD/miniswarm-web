FROM node:24-bookworm-slim AS node-runtime

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_INDEX_URL=https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
RUN sed -i \
      -e 's|deb.debian.org/debian|mirrors.tuna.tsinghua.edu.cn/debian|g' \
      -e 's|security.debian.org/debian-security|mirrors.tuna.tsinghua.edu.cn/debian-security|g' \
      /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
      fontconfig \
      fonts-liberation \
      fonts-noto-cjk \
      fonts-wqy-zenhei \
      libreoffice-calc \
      libreoffice-impress \
      libreoffice-writer \
      poppler-utils \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*
RUN addgroup --system runner && adduser --system --ingroup runner runner
COPY pyproject.toml ./
COPY runner_app ./runner_app
RUN python -m pip install --no-cache-dir .
USER runner
EXPOSE 8100
CMD ["uvicorn", "runner_app.main:app", "--host", "0.0.0.0", "--port", "8100"]
