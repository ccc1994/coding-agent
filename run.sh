#!/bin/bash

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Set PYTHONPATH to current directory
export PYTHONPATH=$PYTHONPATH:$(pwd)

cd playground
python3 ../src/main.py "$@"
