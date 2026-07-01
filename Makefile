.PHONY: up down build restart logs shell ps clean

up:
	docker compose up --build

down:
	docker compose down

build:
	docker compose build

restart: down up

logs:
	docker compose logs -f

shell:
	docker compose exec bot sh

ps:
	docker compose ps

clean:
	docker compose down --rmi all --volumes