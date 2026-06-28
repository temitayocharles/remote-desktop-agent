.PHONY: install test lint run-control run-bot run-runner up down bootstrap-mac sync-mac
install:
	python3 -m pip install -e .
test:
	pytest -q
lint:
	python3 -m compileall -q apps tests
run-control:
	PYTHONPATH=apps/control-plane uvicorn app.main:app --host 127.0.0.1 --port 8080
run-bot:
	PYTHONPATH=apps/telegram-bot python3 apps/telegram-bot/bot.py
run-runner:
	PYTHONPATH=apps/runner python3 -m agent_runner.main
up:
	bash ./scripts/compose.sh up -d --build
down:
	bash ./scripts/compose.sh down
bootstrap-mac:
	bash ./scripts/bootstrap_mac.sh
sync-mac:
	bash ./scripts/sync_mac.sh
