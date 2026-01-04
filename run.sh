#!/bin/bash

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Set PYTHONPATH to current directory
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Determine working directory
WORK_DIR="playground"
if [ "$1" ]; then
    WORK_DIR="$1"
fi

if [ ! -d "$WORK_DIR" ]; then
    echo "Error: Directory '$WORK_DIR' does not exist."
    exit 1
fi

# Get absolute path of src/main.py before changing directory
SCRIPT_PATH=$(pwd)/src/main.py

cd "$WORK_DIR"
python3 "$SCRIPT_PATH"
