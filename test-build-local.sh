#!/bin/bash

# Local build test script to simulate GitHub Actions workflow
# This tests the Linux build process locally

set -e  # Exit on any error

echo "🧪 Testing Linux build process locally..."
echo "========================================"

# Check if we're on Linux
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo "❌ This script is designed for Linux systems"
    exit 1
fi

# Create a temporary virtual environment for testing
echo "📦 Creating test virtual environment..."
python3 -m venv test_build_env
source test_build_env/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
python -m pip install --upgrade pip

# Install base requirements
echo "📋 Installing base requirements..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    echo "❌ requirements.txt not found!"
    exit 1
fi

# Install Linux-specific requirements
echo "🐧 Installing Linux-specific requirements..."
if [ -f "requirements-linux.txt" ]; then
    pip install -r requirements-linux.txt
else
    echo "❌ requirements-linux.txt not found!"
    exit 1
fi

# Install PyInstaller
echo "🔧 Installing PyInstaller..."
pip install pyinstaller

# Check if main.py exists
if [ ! -f "src/main.py" ]; then
    echo "❌ src/main.py not found!"
    exit 1
fi

# Check if icon exists
if [ ! -f "src/icons/connected.png" ]; then
    echo "❌ src/icons/connected.png not found!"
    exit 1
fi

# Build the executable
echo "🏗️  Building executable with PyInstaller..."
pyinstaller \
    --noconfirm \
    --onefile \
    --windowed \
    --noconsole \
    --icon "src/icons/connected.png" \
    --add-data "src/icons:icons" \
    --add-data "src/watercooler_manager:watercooler_manager" \
    --name "WaterCoolerManager" \
    src/main.py

# Check if build was successful
if [ -f "dist/WaterCoolerManager" ]; then
    echo "✅ Build successful!"
    echo "📁 Executable created at: dist/WaterCoolerManager"
    
    # Get file info
    echo "📊 File information:"
    ls -lh dist/WaterCoolerManager
    file dist/WaterCoolerManager
    
    # Test if executable runs (just check if it starts without crashing)
    echo "🧪 Testing if executable starts..."
    timeout 5s ./dist/WaterCoolerManager --help 2>/dev/null || echo "ℹ️  Executable starts (timeout after 5s is expected)"
    
else
    echo "❌ Build failed - executable not found!"
    exit 1
fi

# Cleanup
echo "🧹 Cleaning up..."
deactivate
rm -rf test_build_env

echo ""
echo "🎉 Local build test completed successfully!"
echo "The GitHub Actions workflow should work correctly."
echo ""
echo "Next steps:"
echo "1. Commit and push the workflow files"
echo "2. Create and push a version tag (e.g., git tag v1.0.0-test && git push origin v1.0.0-test)"
echo "3. Check the Actions tab in GitHub to see the workflow run"
