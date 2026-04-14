.PHONY: help dev-api dev-web dev-cli test-core test-api test-cli test-web test-all docker-up docker-down install

help:
	@echo "Hwarang AI System - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install          Install all dependencies"
	@echo "  make setup-storage    Initialize disk directories (multi-disk)"
	@echo "  make check-storage    Check storage paths (dry-run)"
	@echo ""
	@echo "Development:"
	@echo "  make dev-api          Start API server with hot reload"
	@echo "  make dev-web          Start web UI dev server"
	@echo "  make dev-cli          Launch CLI agent"
	@echo ""
	@echo "Testing:"
	@echo "  make test-core        Run LLM core tests"
	@echo "  make test-api         Run API server tests"
	@echo "  make test-cli         Run CLI tool tests"
	@echo "  make test-web         Run web UI tests"
	@echo "  make test-all         Run all tests"
	@echo ""
	@echo "Data:"
	@echo "  make download-data    Download all training data"
	@echo "  make download-code    Download code data (20 languages)"
	@echo "  make download-design  Download UI/UX design data"
	@echo "  make download-ko      Download Korean data only"
	@echo "  make download-test    Download small test set"
	@echo ""
	@echo "Training:"
	@echo "  make train-tokenizer  Train BPE tokenizer"
	@echo "  make pretrain         Run pretraining"
	@echo "  make finetune         Run supervised fine-tuning"
	@echo "  make align            Run DPO alignment"
	@echo "  make export           Export model for serving"
	@echo "  make benchmark        Run inference benchmark"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-up        Start all services (single server)"
	@echo "  make docker-down      Stop all services"
	@echo "  make cluster-up       Start distributed cluster (multi-server)"
	@echo "  make cluster-scale    Scale workers (N=3)"
	@echo "  make cluster-status   Check cluster status"
	@echo "  make cluster-down     Stop cluster"

# Setup
install:
	cd packages/hwarang-shared && poetry install
	cd modules/hwarang-core && poetry install
	cd modules/hwarang-api && poetry install
	cd modules/hwarang-cli && poetry install
	cd modules/hwarang-web && pnpm install
	pip install datasets tqdm
	@echo ""
	@echo "All dependencies installed!"

setup-storage:
	python scripts/setup_storage.py

check-storage:
	python scripts/setup_storage.py --dry-run

# Development
dev-api:
	cd modules/hwarang-api && poetry run uvicorn hwarang_api.main:create_app --factory --reload --port 8000

dev-api-distributed:
	cd modules/hwarang-api && HWARANG_DISTRIBUTED=true poetry run uvicorn hwarang_api.main:create_app --factory --reload --port 8000

dev-worker:
	cd modules/hwarang-api && poetry run python -m hwarang_api.distributed.worker \
		--model-path ../hwarang-core/exported/hwarang-small \
		--model-id hwarang-small \
		--redis-url redis://localhost:6379

dev-web:
	cd modules/hwarang-web && pnpm dev

dev-cli:
	cd modules/hwarang-cli && poetry run hwarang

# Testing
test-core:
	cd modules/hwarang-core && poetry run pytest -v

test-api:
	cd modules/hwarang-api && poetry run pytest -v

test-cli:
	cd modules/hwarang-cli && poetry run pytest -v

test-web:
	cd modules/hwarang-web && pnpm test

test-all: test-core test-api test-cli test-web

# Docker
docker-up:
	docker compose -f docker/docker-compose.yml up --build

docker-down:
	docker compose -f docker/docker-compose.yml down

# Distributed Cluster
cluster-up:
	docker compose -f docker/docker-compose.distributed.yml up --build

cluster-scale:
	docker compose -f docker/docker-compose.distributed.yml up --scale worker=$(N) --no-recreate -d

cluster-status:
	@curl -s http://localhost:8000/admin/cluster/status | python -m json.tool 2>/dev/null || echo "API server not running"

cluster-down:
	docker compose -f docker/docker-compose.distributed.yml down

# Data
download-data:
	python scripts/download_data.py --task all --output data/

download-code:
	python scripts/download_data.py --task code --output data/

download-design:
	python scripts/download_data.py --task design --output data/

download-ko:
	python scripts/download_data.py --task all --lang ko --output data/

download-test:
	python scripts/download_data.py --task all --lang ko --max-samples 1000 --output data/

# Training
train-tokenizer:
	cd modules/hwarang-core && poetry run python scripts/train_tokenizer.py \
		--data ../../data/pretrain/corpus.txt --output ./tokenizer_output --vocab-size 32000

pretrain:
	cd modules/hwarang-core && poetry run torchrun --nproc_per_node=auto scripts/pretrain.py \
		--data ../../data/train.bin --model-config configs/model/small.yaml

finetune:
	cd modules/hwarang-core && poetry run python scripts/finetune.py \
		--checkpoint ./checkpoints/pretrain/final --data ../../data/sft/all_sft.jsonl

align:
	cd modules/hwarang-core && poetry run python scripts/align.py \
		--checkpoint ./checkpoints/sft/final --data ../../data/dpo/preferences.jsonl

export:
	cd modules/hwarang-core && poetry run python scripts/export_model.py \
		--checkpoint ./checkpoints/dpo/final --output ./exported/hwarang-small

benchmark:
	cd modules/hwarang-core && poetry run python scripts/benchmark.py --model-size small
