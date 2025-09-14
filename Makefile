SHELL := /bin/bash

.PHONY: db-up db-down db-logs test-backend backend-install backend-run frontend-install frontend-dev

db-up:
	docker compose up -d postgres
	@echo "Set DATABASE_URL to: postgres://rateengine:rateengine@127.0.0.1:5432/rateengine"

db-down:
	docker compose down

db-logs:
	docker compose logs -f postgres

backend-install:
	$(MAKE) -C backend install

backend-run:
	$(MAKE) -C backend run

test-backend:
	./scripts/test_backend.sh

frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

