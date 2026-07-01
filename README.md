# agent-smith

## Стек

- Python 3.14
- [uv](https://docs.astral.sh/uv/) - менеджмент зависимостей
- [aiogram](https://aiogram.dev/) - фреймворк для тг-ботов
- Docker + Docker Compose - контейнеризация и запуск

## Нужно установить

- Docker и Docker Compose (на Windows - Docker Desktop с включённой интеграцией WSL2)
- Для локального запуска без Docker - [uv](https://docs.astral.sh/uv/)
- Для быстрых команд - `make` (обычно уже есть в Ubuntu/WSL; если нет: `sudo apt install make`)

## Настройка окружения

Скопировать пример (из .env.example в .env) и заполнить своими значениями:
```bash
cp .env.example .env
```
Файл `.env` не коммитится (`.gitignore`) - только `.env.example` хранится в репозитории как образец

## Быстрый старт (через Docker)

1. Склонировать репозиторий и перейти в папку:
```bash
   git clone git@github.com:bmstu-dspl/agent-smith.git
   cd agent-smith
```
2. Настроить `.env` (см. пункт «Настройка окружения» ранее).
3. Собрать и запустить:
```bash
   docker compose up --build
```
   Или через Makefile (см. ниже):
```bash
   make up
```
4. Остановить:
```bash
   docker compose down
```
   Или:
```bash
   make down
```

## Быстрые команды (через Makefile)

make up — Собрать и запустить бота

make down — Остановить бота

make build — Пересобрать образ без запуска

make restart — Перезапустить бота

make logs — Смотреть логи запущенного бота

make shell — Зайти в контейнер бота

make ps — Список запущенных контейнеров

make clean — Остановить и удалить образы и тома (volumes)

## Локальный запуск (без Docker, для разработки)

1. Установить зависимости (uv сам подтянет нужный Python, если его нет):
```bash
   uv sync
```
2. Настроить `.env` (см. раздел «Настройка окружения» выше).
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
- `Makefile` - шорткаты для команд
- `.env.example` - образец переменных окружения (без секретов)
- `.dockerignore` / `.gitignore` - не попадает в образ/репозиторий

## Доп инфа

Новые сервисы добавляются как сервисы в `compose.yaml` рядом с `bot`.