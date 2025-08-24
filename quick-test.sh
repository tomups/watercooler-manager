#!/bin/bash

# Quick test to verify system dependencies and Python packages
echo "🔍 Quick GitHub Actions compatibility check..."
echo "============================================="

# Check Python version
echo "🐍 Python version:"
python3 --version

# Check if system dependencies are available
echo ""
echo "📦 Checking system dependencies..."

# Detect package manager
if command -v pacman &> /dev/null; then
    # Arch Linux
    deps=("python-gobject" "python-cairo" "gtk3" "libappindicator-gtk3")
    missing_deps=()

    for dep in "${deps[@]}"; do
        if pacman -Q "$dep" &> /dev/null; then
            echo "✅ $dep - installed"
        else
            echo "❌ $dep - missing"
            missing_deps+=("$dep")
        fi
    done

    if [ ${#missing_deps[@]} -gt 0 ]; then
        echo ""
        echo "⚠️  Missing system dependencies. Install with:"
        echo "sudo pacman -S ${missing_deps[*]}"
        echo ""
    fi
elif command -v dpkg &> /dev/null; then
    # Debian/Ubuntu
    deps=("python3-gi" "python3-gi-cairo" "gir1.2-gtk-3.0" "gir1.2-appindicator3-0.1")
    missing_deps=()

    for dep in "${deps[@]}"; do
        if dpkg -l | grep -q "^ii.*$dep"; then
            echo "✅ $dep - installed"
        else
            echo "❌ $dep - missing"
            missing_deps+=("$dep")
        fi
    done

    if [ ${#missing_deps[@]} -gt 0 ]; then
        echo ""
        echo "⚠️  Missing system dependencies. Install with:"
        echo "sudo apt install ${missing_deps[*]}"
        echo ""
    fi
else
    echo "⚠️  Unknown package manager - manual dependency check needed"
fi

# Check if required files exist
echo ""
echo "📁 Checking required files..."
files=("src/main.py" "src/icons/connected.png" "requirements.txt" "requirements-linux.txt")

for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        echo "✅ $file - exists"
    else
        echo "❌ $file - missing"
    fi
done

# Test PyInstaller installation
echo ""
echo "🔧 Testing PyInstaller..."
if python3 -c "import PyInstaller" 2>/dev/null; then
    echo "✅ PyInstaller - available"
else
    echo "❌ PyInstaller - not installed (pip install pyinstaller)"
fi

echo ""
echo "💡 To run full build test: ./test-build-local.sh"
