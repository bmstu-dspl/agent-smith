FROM python:3.14-slim

# копируем uv из официального образа
COPY --from=ghcr.io/astral-sh/uv:0.11.25 /uv /uvx /bin/

# рабочая папка внутри контейнера
WORKDIR /app

# настройки окружения
ENV PYTHONUNBUFFERED=1
ENV UV_NO_DEV=1
ENV UV_PYTHON_DOWNLOADS=0

# файлы зависимостей
COPY pyproject.toml uv.lock ./
# устанавливаем зависимости
RUN uv sync --frozen --no-install-project
COPY . .

# устанавливаем проект
RUN uv sync --frozen

# порт для вебхука
EXPOSE 8080

# команда запуска будет переопределена в docker-compose.override.yml
CMD ["uv", "run", "--no-sync", "python", "run.py"]