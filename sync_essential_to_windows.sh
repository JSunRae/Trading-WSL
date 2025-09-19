#!/bin/bash
# Sync essential files from WSL to Windows repository
# Usage: ./sync_essential_to_windows.sh

WSL_SOURCE="/home/jrae/wsl projects/Trading-WSL"
WIN_TARGET="/mnt/c/Users/Pilot/Documents/Vs Code Projects/Trading-Win"

echo "🔄 Syncing essential files from WSL to Windows..."
echo "Source: $WSL_SOURCE"
echo "Target: $WIN_TARGET"
echo ""

# Create target directory if it doesn't exist
if [ ! -d "$WIN_TARGET" ]; then
    echo "❌ Target directory does not exist: $WIN_TARGET"
    echo "Please ensure the Windows path is mounted and accessible."
    exit 1
fi

# 1. Copy .env file (MOST CRITICAL)
echo "📋 Copying .env file..."
if [ -f "$WSL_SOURCE/.env" ]; then
    cp "$WSL_SOURCE/.env" "$WIN_TARGET/"
    echo "  ✅ .env copied successfully"
else
    echo "  ❌ .env file not found!"
fi

# 2. Copy VS Code settings
echo ""
echo "🔧 Copying VS Code settings..."
mkdir -p "$WIN_TARGET/.vscode"
if [ -d "$WSL_SOURCE/.vscode" ]; then
    cp "$WSL_SOURCE/.vscode/"* "$WIN_TARGET/.vscode/" 2>/dev/null
    echo "  ✅ VS Code settings copied"
    echo "     - settings.json, tasks.json, launch.json, etc."
else
    echo "  ⚠️  .vscode directory not found"
fi

# 3. Copy data files
echo ""
echo "📊 Copying data files..."
mkdir -p "$WIN_TARGET/data"
if [ -d "$WSL_SOURCE/data" ]; then
    cp -r "$WSL_SOURCE/data/"* "$WIN_TARGET/data/" 2>/dev/null
    echo "  ✅ Data files copied:"
    ls "$WSL_SOURCE/data/" | sed 's/^/     - /'
else
    echo "  ⚠️  data directory not found"
fi

# 4. Copy logs
echo ""
echo "📝 Copying logs..."
mkdir -p "$WIN_TARGET/logs"
if [ -d "$WSL_SOURCE/logs" ]; then
    cp -r "$WSL_SOURCE/logs/"* "$WIN_TARGET/logs/" 2>/dev/null
    echo "  ✅ Log files copied:"
    ls "$WSL_SOURCE/logs/" | sed 's/^/     - /'
else
    echo "  ⚠️  logs directory not found"
fi

echo ""
echo "✅ Essential file sync complete!"
echo ""
echo "🚨 IMPORTANT NEXT STEPS for Windows:"
echo ""
echo "1. 🐍 Recreate Python virtual environment:"
echo "   cd 'C:\\Users\\Pilot\\Documents\\Vs Code Projects\\Trading-Win'"
echo "   python -m venv .venv"
echo "   .venv\\Scripts\\activate"
echo "   pip install -e .[dev]"
echo ""
echo "2. 📝 Update .env file for Windows:"
echo "   - Change ML_BASE_PATH from ~/Machine Learning to C:\\Users\\Pilot\\Machine Learning"
echo "   - Update IB_HOST if needed (probably keep 127.0.0.1)"
echo "   - Convert any other Linux paths to Windows format"
echo ""
echo "3. 🔧 Verify VS Code settings work on Windows"
echo "   - Tasks might need path adjustments"
echo "   - Python interpreter paths will be different"
echo ""
echo "🔒 SECURITY REMINDER:"
echo "   The .env file contains passwords and API keys!"
echo "   Ensure your Windows repository is secure and private."