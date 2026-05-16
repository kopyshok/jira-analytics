.PHONY: install dev run test lint migrate clean release

# Install dependencies
install:
	pip install -r requirements.txt

# Development setup
dev: install
	cp -n .env.example .env || true
	mkdir -p data exports

# Run the application
run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
test:
	pytest tests/ -v

# Run linter
lint:
	ruff check app/ tests/
	mypy app/

# Format code
format:
	ruff format app/ tests/

# Create new migration
migration:
	alembic revision --autogenerate -m "$(msg)"

# Apply migrations
migrate:
	alembic upgrade head

# Downgrade one migration
downgrade:
	alembic downgrade -1

# Show migration history
history:
	alembic history

# Clean up
clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	rm -rf data/*.db

# Full reset (clean + migrate)
reset: clean migrate

# Cut a release: bump versions, commit, tag, push.
# Usage:  make release VERSION=v1.2.3
release:
	@if [ -z "$(VERSION)" ]; then echo "Usage: make release VERSION=v1.2.3"; exit 1; fi
	@echo "$(VERSION)" | grep -Eq '^v[0-9]+\.[0-9]+\.[0-9]+$$' || { echo "VERSION must match vMAJOR.MINOR.PATCH"; exit 1; }
	@if ! git diff --quiet || ! git diff --cached --quiet; then echo "Working tree dirty — commit or stash first."; exit 1; fi
	@PLAIN=$$(echo "$(VERSION)" | sed 's/^v//'); \
	python -c "import re,pathlib; p=pathlib.Path('app/config.py'); s=p.read_text(); s=re.sub(r'app_version: str = \"[^\"]*\"', f'app_version: str = \"$$PLAIN\"', s); p.write_text(s)"; \
	python -c "import json,pathlib; p=pathlib.Path('frontend/package.json'); d=json.loads(p.read_text()); d['version']='$$PLAIN'; p.write_text(json.dumps(d, indent=2)+'\n')"
	git add app/config.py frontend/package.json
	git commit -m "chore(release): $(VERSION)"
	git tag -a $(VERSION) -m "Release $(VERSION)"
	@echo ""
	@echo "Local commit + tag ready. To trigger CI release pipeline, run:"
	@echo "  git push origin main && git push origin $(VERSION)"

# Help
help:
	@echo "Available commands:"
	@echo "  make install    - Install dependencies"
	@echo "  make dev        - Development setup"
	@echo "  make run        - Run the application"
	@echo "  make test       - Run tests"
	@echo "  make lint       - Run linter"
	@echo "  make format     - Format code"
	@echo "  make migrate    - Apply migrations"
	@echo "  make migration msg='description' - Create new migration"
	@echo "  make clean      - Clean up cache files"
	@echo "  make reset      - Clean and migrate"
	@echo "  make release VERSION=v1.2.3 - Bump versions, commit and tag"
