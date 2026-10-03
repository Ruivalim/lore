# lore: biblioteca pessoal curada e consultável
# `make` lista comandos, receitas delegam para as ferramentas do projeto.
SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
MAKEFLAGS += --warn-undefined-variables --no-builtin-rules --no-print-directory
.DEFAULT_GOAL := help
.DELETE_ON_ERROR:

APP ?= lore
VENV ?= .venv
PYTHON := $(VENV)/bin/python
PIPX ?= pipx
GO ?= go
TUI_BIN ?= tui/lore-tui
BIN_DIR ?= $(HOME)/.local/bin

BOLD :=
CYAN :=
GREEN :=
RESET :=
ifneq ($(shell [ -t 1 ] && echo tty),)
BOLD := $(shell tput bold 2>/dev/null)
CYAN := $(shell tput setaf 6 2>/dev/null)
GREEN := $(shell tput setaf 2 2>/dev/null)
RESET := $(shell tput sgr0 2>/dev/null)
endif

##@ Geral
.PHONY: help
help: ## Lista os alvos disponíveis
	@awk 'BEGIN {FS = ":.*##"; printf "\n$(BOLD)$(APP)$(RESET)\n\nUso: make $(CYAN)<alvo>$(RESET)\n"} /^##@/ {printf "\n$(BOLD)%s$(RESET)\n", substr($$0, 5)} /^[a-zA-Z0-9_.\/-]+:.*##/ {printf " $(CYAN)%-18s$(RESET) %s\n", $$1, $$2} END {printf "\n"}' $(MAKEFILE_LIST)

##@ Desenvolvimento
.PHONY: setup
setup: ## Instala dependências no ambiente virtual
	@echo "$(GREEN)▸ setup$(RESET)"
	test -x $(PYTHON) || python3 -m venv $(VENV)
	$(PYTHON) -m pip install -e '.[dev]'

.PHONY: test
test: setup ## Executa testes
	@echo "$(GREEN)▸ test$(RESET)"
	$(PYTHON) -m pytest -q
	cd tui && $(GO) test -race ./...

.PHONY: lint
lint: setup ## Verifica estilo e erros comuns
	@echo "$(GREEN)▸ lint$(RESET)"
	$(VENV)/bin/ruff check src tests
	cd tui && $(GO) vet ./... && test -z "$$(gofmt -l .)"

.PHONY: fmt
fmt: setup ## Formata Python e Go
	@echo "$(GREEN)▸ fmt$(RESET)"
	$(VENV)/bin/ruff format src tests
	cd tui && gofmt -w .

.PHONY: check
check: lint test build ## Executa lint, testes e build

##@ Distribuição
.PHONY: build
build: setup tui ## Empacota wheel em dist/ e compila o TUI
	@echo "$(GREEN)▸ build$(RESET)"
	mkdir -p dist
	$(PYTHON) -m pip wheel . --no-deps -w dist

.PHONY: tui
tui: ## Compila o TUI (lore ask sem pergunta) em tui/lore-tui
	@echo "$(GREEN)▸ tui$(RESET)"
	cd tui && $(GO) build -trimpath -o lore-tui .

.PHONY: tui-install
tui-install: tui ## Instala lore-tui em ~/.local/bin
	@echo "$(GREEN)▸ tui-install$(RESET)"
	install -Dm755 $(TUI_BIN) $(BIN_DIR)/lore-tui

.PHONY: install
install: ## Instala Lore editável para o usuário via pipx
	@echo "$(GREEN)▸ install$(RESET)"
	@if $(PIPX) list --short 2>/dev/null | grep -qx 'lore 0.0.1'; then \
		$(PIPX) reinstall lore; \
	else \
		$(PIPX) install --editable .; \
	fi

.PHONY: uninstall
uninstall: ## Remove instalação pipx do Lore
	@echo "$(GREEN)▸ uninstall$(RESET)"
	$(PIPX) uninstall lore

.PHONY: clean
clean: ## Remove artefatos gerados
	@echo "$(GREEN)▸ clean$(RESET)"
	rm -rf build dist .pytest_cache .ruff_cache src/lore.egg-info $(TUI_BIN)
