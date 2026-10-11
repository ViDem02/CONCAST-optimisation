#!/bin/bash

# CONCAST Simulator Frontend - Installation Script
# This script sets up the React frontend for the simulator

echo "=========================================="
echo "CONCAST Simulator Frontend Setup"
echo "=========================================="
echo ""

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed!"
    echo "Please install Node.js 18+ from https://nodejs.org/"
    exit 1
fi

echo "✅ Node.js version: $(node --version)"

# Check if npm is installed
if ! command -v npm &> /dev/null; then
    echo "❌ npm is not installed!"
    exit 1
fi

echo "✅ npm version: $(npm --version)"
echo ""

# Navigate to frontend directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "📦 Installing frontend dependencies..."
echo "This may take a few minutes..."
echo ""

npm install

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "✅ Installation Complete!"
    echo "=========================================="
    echo ""
    echo "Next steps:"
    echo ""
    echo "1. Ensure Django backend is running:"
    echo "   cd ../simulator_project"
    echo "   python manage.py runserver"
    echo ""
    echo "2. Start the frontend development server:"
    echo "   npm run dev"
    echo ""
    echo "3. Open your browser at:"
    echo "   http://localhost:3000"
    echo ""
    echo "📚 Documentation:"
    echo "   - README.md - Full documentation"
    echo "   - SETUP.md - Quick start guide"
    echo "   - OVERVIEW.md - Technical overview"
    echo ""
else
    echo ""
    echo "❌ Installation failed!"
    echo "Please check the error messages above."
    exit 1
fi
