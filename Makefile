.PHONY: install pipeline pipeline-small run test lint docker-up

install:
	uv sync

pipeline:
	uv run python -m src.run_pipeline

pipeline-small:
	uv run python -m src.run_pipeline --small

run:
	PYTHONPATH=. uv run streamlit run app/Home.py

test:
	uv run pytest

lint:
	uv run ruff check .

docker-up:
	docker compose up --build
