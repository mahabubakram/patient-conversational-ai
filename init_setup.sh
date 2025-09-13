#!/usr/bin/env bash
set -euo pipefail

echo "🚀 Setting up Python environment for Conversational AI POC..."

# Create virtual environment if not exists
if [ ! -d ".venv" ]; then
  echo "📦 Creating virtual environment (.venv)..."
  python3 -m venv .venv
fi

# Activate venv
echo "🔑 Activating virtual environment..."
source .venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install requirements
echo "📥 Installing Python dependencies..."
pip install -r requirements.txt

# Download spaCy models
echo "📥 Downloading spaCy models..."
python -m spacy download en_core_web_sm

echo "✅ Setup complete. Activate venv with: source .venv/bin/activate"
echo "👉 Run the API with: uvicorn app.main:app --reload --port 8000"
