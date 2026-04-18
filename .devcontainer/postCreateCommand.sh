#! /usr/bin/env bash

curl -LsSf https://astral.sh/uv/install.sh | sh

uv sync

uv run pre-commit install --install-hooks
