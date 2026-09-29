.PHONY: install dev-backend dev-frontend format lint typecheck test check hooks pages package

install:
	cd backend && uv sync
	cd frontend && npm install

dev-backend:
	uv run --project backend dartscore

dev-frontend:
	cd frontend && npm run dev

format:
	cd backend && uv run ruff format . && uv run ruff check --fix .

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && npm run lint

typecheck:
	cd backend && uv run mypy src tests
	cd frontend && npm run typecheck

test:
	cd backend && uv run pytest

# Local "CI": everything that must pass before a commit
check: lint typecheck test
	cd frontend && npm run build

hooks:
	cd backend && uv run pre-commit install

# Publish the project page (docs/site) to the gh-pages branch served by GitHub Pages
pages:
	git push origin `git subtree split --prefix docs/site HEAD`:refs/heads/gh-pages

# Release package for this system (PyInstaller bundle + installer) into release/, see docs/releasing.md
package:
	uv run --project backend --group package python packaging/build.py
