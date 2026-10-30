test:
	uv run pytest tests/unit -v

test-integration:
	uv run pytest tests/integration -v

test-all:
	uv run pytest -v

check-connection:
	uv run python -m scripts.check_connection