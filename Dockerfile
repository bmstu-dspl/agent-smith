FROM python:3.14-slim

# копируем из официального образа uv
COPY --from=ghcr.io/astral-sh/uv:0.11.25 /uv /uvx /bin/

# рабочая папка внутри контейнера
WORKDIR /app

# настройки окружения
ENV PYTHONUNBUFFERED=1
ENV UV_NO_DEV=1
ENV UV_PYTHON_DOWNLOADS=0

# файлы зависимостей
COPY pyproject.toml uv.lock ./
# зависимости только по lock-файлу
RUN uv sync --frozen --no-install-project
COPY . .

# запускать при старте контейнера
CMD ["uv", "run", "--no-sync", "python", "main.py"]