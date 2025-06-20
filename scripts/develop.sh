#!/bin/bash

set -e  # Exit on any error

# Extract project name from pyproject.toml (first "name" match)
PACKAGE_NAME=$(grep -m1 '^name *= *' pyproject.toml | cut -d '"' -f2)
VENV_DIR=".venv_${PACKAGE_NAME}"

# Create the virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "🔧 Creating virtual environment in $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
else
    echo "ℹ️ Virtual environment already exists in $VENV_DIR"
fi

echo "🔌 Activating virtual environment from $VENV_DIR ..."
source "$VENV_DIR/bin/activate"

echo "📦 Installing main project in editable mode ..."
pip install -e .

if [ -f requirements-dev.txt ]; then
    echo "🧪 Installing development dependencies from requirements-dev.txt ..."
    pip install -r requirements-dev.txt

    # Check for any -e path in requirements-dev.txt and validate the folder exists
    while IFS= read -r req; do
        if [[ "$req" =~ ^-e[[:space:]]+(.+) ]]; then
            REQ_PATH="${BASH_REMATCH[1]}"
            if [ ! -d "$REQ_PATH" ]; then
                echo "⚠️  Warning: editable path '$REQ_PATH' does not exist!" >&2
            fi
        fi
    done < requirements-dev.txt

else
    echo "ℹ️ No requirements-dev.txt found – skipping dev dependencies."
fi

echo "✅ Development environment is ready!"
echo "🔄 To activate, run: source $VENV_DIR/bin/activate"
echo "💡 To deactivate, run: deactivate"
