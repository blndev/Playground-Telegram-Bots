#!/bin/bash

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install/upgrade dependencies
echo "Installing/upgrading dependencies..."
pip install -r requirements.txt --upgrade

echo "Setup complete! Virtual environment is activated."
echo "To deactivate the virtual environment, run: deactivate"
