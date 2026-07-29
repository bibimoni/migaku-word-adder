#!/bin/bash

set -xe
PYTHON_APP_PATH=".venv/bin/python"
${PYTHON_APP_PATH} migaku_queue.py "$@"

