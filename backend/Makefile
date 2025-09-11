ifeq ($(OS),Windows_NT)
VENV_BIN=.venv/Scripts
PY=python
else
VENV_BIN=.venv/bin
PY=python3
endif

PIP=$(VENV_BIN)/pip
PYTHON=$(VENV_BIN)/python
MANAGE=$(PYTHON) manage.py

.PHONY: venv install migrate seed run test dev superuser inspect-fees

venv:
	$(PY) -m venv .venv

install: venv
	$(PIP) install -r requirements.txt

migrate:
	$(MANAGE) migrate

seed:
	$(MANAGE) create_test_users

run:
	$(MANAGE) runserver

test:
	$(MANAGE) test

dev: install migrate run

superuser:
	$(MANAGE) createsuperuser

# Inspect fees for a given ratecard. Optionally pass RATECARD_NAME
#   make inspect-fees
#   RATECARD_NAME="Your Ratecard" make inspect-fees
inspect-fees:
	$(PYTHON) ../scripts/inspect_fees.py
