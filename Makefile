# ─────────────────────────────────────────────────────────────
# Atlas — Watch Flip Tracker
# ─────────────────────────────────────────────────────────────
#
#   make install      Install Python dependencies
#   make test         Run unit + integration tests
#   make test-all     Run full suite including property tests
#   make dev          Start frontend + backend locally
#   make frontend     Start only the frontend
#   make backend      Build SAM and start the local API
#   make build        Build the SAM application
#   make deploy       Build and deploy to AWS
#   make deploy-first First-time guided deploy to AWS
#   make upload       Upload frontend to S3 + invalidate cache
#   make release      Deploy backend + upload frontend
#   make secrets      Provision auth secret in Secrets Manager
#   make clean        Remove build artifacts
#   make help         Show this help
#
# ─────────────────────────────────────────────────────────────

SHELL := /bin/bash
.DEFAULT_GOAL := help

STACK_NAME   ?= atlas
STAGE        ?= prod
FRONTEND_DIR := frontend
FRONTEND_PORT ?= 8080
API_PORT     ?= 3000

# ── Helpers ──────────────────────────────────────────────────

.PHONY: help
help: ## Show available commands
	@echo ""
	@echo "  Atlas — available commands"
	@echo "  ─────────────────────────────────────────"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'
	@echo ""

# ── Setup ────────────────────────────────────────────────────

.PHONY: install
install: ## Install all Python dependencies
	pip install -r requirements.txt -r requirements-dev.txt

# ── Testing ──────────────────────────────────────────────────

.PHONY: test
test: ## Run unit + integration tests (fast)
	pytest tests/unit/ tests/integration/ -v --tb=short

.PHONY: test-all
test-all: ## Run full test suite including property tests
	pytest -v --tb=short

.PHONY: coverage
coverage: ## Run tests with coverage report
	pytest --cov=src --cov-report=html --cov-report=term
	@echo ""
	@echo "  HTML report: open htmlcov/index.html"

# ── Local Development ────────────────────────────────────────

.PHONY: dev
dev: ## Start frontend (port 8080) + backend (port 3000)
	@echo ""
	@echo "  Starting Atlas locally..."
	@echo "  Frontend: http://localhost:$(FRONTEND_PORT)"
	@echo "  Backend:  http://127.0.0.1:$(API_PORT)"
	@echo ""
	@echo "  Press Ctrl+C to stop both servers."
	@echo ""
	@sam build --quiet
	@trap 'kill 0' EXIT; \
		python -m http.server $(FRONTEND_PORT) --directory $(FRONTEND_DIR) & \
		sam local start-api --port $(API_PORT) & \
		wait

.PHONY: frontend
frontend: ## Start only the frontend (port 8080)
	@echo "  Frontend: http://localhost:$(FRONTEND_PORT)"
	python -m http.server $(FRONTEND_PORT) --directory $(FRONTEND_DIR)

.PHONY: backend
backend: build ## Build SAM and start the local API (port 3000)
	@echo "  Backend: http://127.0.0.1:$(API_PORT)"
	sam local start-api --port $(API_PORT)

# ── Build & Deploy ───────────────────────────────────────────

.PHONY: build
build: ## Build the SAM application
	sam build

.PHONY: deploy-first
deploy-first: build ## First-time guided deploy (interactive)
	sam deploy --guided

.PHONY: deploy
deploy: build ## Build and deploy to AWS
	sam deploy

.PHONY: upload
upload: ## Upload frontend to S3 and invalidate CloudFront cache
	@WEB_BUCKET=$$(aws cloudformation describe-stacks \
		--stack-name $(STACK_NAME) \
		--query 'Stacks[0].Outputs[?OutputKey==`WebAssetsBucketName`].OutputValue' \
		--output text) && \
	DIST_ID=$$(aws cloudformation describe-stacks \
		--stack-name $(STACK_NAME) \
		--query 'Stacks[0].Outputs[?OutputKey==`WebDistributionId`].OutputValue' \
		--output text) && \
	echo "  Uploading frontend to s3://$$WEB_BUCKET ..." && \
	aws s3 sync $(FRONTEND_DIR)/ s3://$$WEB_BUCKET/ --delete && \
	echo "  Invalidating CloudFront cache ($$DIST_ID) ..." && \
	aws cloudfront create-invalidation --distribution-id $$DIST_ID --paths "/*" > /dev/null && \
	echo "  Done."

.PHONY: release
release: deploy upload ## Deploy backend and upload frontend

.PHONY: secrets
secrets: ## Provision auth secret in Secrets Manager
	chmod +x scripts/setup-secrets.sh
	./scripts/setup-secrets.sh

.PHONY: outputs
outputs: ## Show deployed stack outputs (API URL, bucket names, etc.)
	@aws cloudformation describe-stacks \
		--stack-name $(STACK_NAME) \
		--query 'Stacks[0].Outputs' \
		--output table

# ── Cleanup ──────────────────────────────────────────────────

.PHONY: clean
clean: ## Remove build artifacts
	rm -rf .aws-sam/build
	rm -rf htmlcov .coverage
	find . -type d -name __pycache__ -not -path './.venv/*' -exec rm -rf {} + 2>/dev/null || true
	@echo "  Cleaned."
