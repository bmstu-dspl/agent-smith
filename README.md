# agent-smith

## Стек

- Python 3.14
- [uv](https://docs.astral.sh/uv/) - менеджмент зависимостей
- [aiogram](https://aiogram.dev/) - фреймворк для тг-ботов
- Docker + Docker Compose - контейнеризация и запуск

## Нужно установить

- Docker и Docker Compose (на Windows - Docker Desktop с включённой интеграцией WSL2)
- Для локального запуска без Docker - [uv](https://docs.astral.sh/uv/)

## Быстрый старт (через Docker)

1. Склонировать репозиторий и перейти в папку:
```bash
   git clone git@github.com:bmstu-dspl/agent-smith.git
   cd agent-smith
```
2. Создать файл `.env` в корне проекта и вписать токен бота в формате:
```
   BOT_TOKEN=ваш_токен
```
3. Собрать и запустить:
```bash
   docker compose up --build
```
4. Остановить:
```bash
   docker compose down
```

## Локальный запуск (без Docker, для разработки)

1. Установить зависимости:
```bash
   uv sync
```
2. Создать `.env` с `BOT_TOKEN` (см. выше).
3. Запустить:
```bash
   uv run python main.py
```

## Структура:

- `main.py` - точка входа, код бота (тестового)
- `pyproject.toml` - зависимости и настройки проекта (uv)
- `uv.lock` - версии зависимостей
- `Dockerfile` - рецепт сборки образа
- `compose.yaml` - описание запуска сервисов
- `.dockerignore` / `.gitignore` - не попадает в образ/репозиторий

## Доп инфа

Новые сервисы добавляются как сервисы в `compose.yaml` рядом с `bot`.