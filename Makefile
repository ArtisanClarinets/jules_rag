# Makefile for Vantus Vector Platform

.PHONY: dev prod down clean install-prereqs backup restore

dev:
	docker compose --profile cpu up -d --build

prod:
	docker compose --profile cpu up -d --build

down:
	docker compose --profile cpu down

clean:
	docker compose --profile cpu down -v
	rm -rf data/*

install-prereqs:
	bash scripts/install_prereqs_ubuntu.sh

backup:
	bash scripts/backup.sh

restore:
	bash scripts/restore.sh

test:
	docker compose run --rm api pytest
	# Add more test commands

lint:
	# Add lint commands
	echo "Linting..."
