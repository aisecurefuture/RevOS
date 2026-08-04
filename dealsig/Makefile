.PHONY: dev test security check compose-up compose-down

dev:
	uvicorn app.main:app --reload --port 8080

test:
	pytest --cov=app --cov-report=term-missing

security:
	bash scripts/security-check.sh

check: test security

compose-up:
	docker compose up --build -d

compose-down:
	docker compose down

