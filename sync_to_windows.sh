#!/bin/bash
# Sync important non-git files from WSL to Windows repository
# Usage: ./sync_to_windows.sh

WSL_SOURCE="/home/jrae/wsl projects/Trading-WSL"
WIN_TARGET="/mnt/c/Users/Pilot/Documents/Vs Code Projects/Trading-Win"

echo "Syncing important non-git files from WSL to Windows..."

# Create target directory if it doesn't exist
mkdir -p "$WIN_TARGET"

# 1. Copy environment file (MOST IMPORTANT)
echo "📋 Copying .env file..."
cp "$WSL_SOURCE/.env" "$WIN_TARGET/"

# 2. Copy VS Code configuration
echo "🔧 Copying VS Code settings..."
mkdir -p "$WIN_TARGET/.vscode"
cp -r "$WSL_SOURCE/.vscode/"* "$WIN_TARGET/.vscode/" 2>/dev/null

# 3. Copy config files
echo "⚙️  Copying configuration files..."
mkdir -p "$WIN_TARGET/config"
cp -r "$WSL_SOURCE/config/"* "$WIN_TARGET/config/"

# 4. Copy data files (if any exist)
echo "📊 Copying data files..."
mkdir -p "$WIN_TARGET/data"
cp -r "$WSL_SOURCE/data/"* "$WIN_TARGET/data/" 2>/dev/null

# 5. Copy logs (optional - you might want recent logs)
echo "📝 Copying recent logs..."
mkdir -p "$WIN_TARGET/logs"
cp -r "$WSL_SOURCE/logs/"* "$WIN_TARGET/logs/" 2>/dev/null

# 6. Copy artifacts
echo "🗄️  Copying artifacts..."
mkdir -p "$WIN_TARGET/artifacts"
cp -r "$WSL_SOURCE/artifacts/"* "$WIN_TARGET/artifacts/" 2>/dev/null

# 7. Copy any other important files
echo "📁 Copying other important files..."
files_to_copy=(
    "nohup.out"
    "preferred_connection.txt"
    "warrior_discovery_debug.json"
    "warrior_task_debug.json"
    "warrior_task_summary.json"
    "coverage_analysis.json"
)

for file in "${files_to_copy[@]}"; do
    if [ -f "$WSL_SOURCE/$file" ]; then
        cp "$WSL_SOURCE/$file" "$WIN_TARGET/"
        echo "  ✓ Copied $file"
    fi
done

echo ""
echo "✅ Sync complete!"
echo ""
echo "🚨 IMPORTANT NEXT STEPS for Windows:"
echo "1. You'll need to recreate the Python virtual environment:"
echo "   cd 'C:\\Users\\Pilot\\Documents\\Vs Code Projects\\Trading-Win'"
echo "   python -m venv .venv"
echo "   .venv\\Scripts\\activate"
echo "   pip install -e .[dev]"
echo ""
echo "2. Update .env file paths for Windows:"
echo "   - Change WSL paths (/) to Windows paths (\\)"
echo "   - Update IB_HOST to point to Windows localhost"
echo "   - Update file paths in ML_BASE_PATH"
echo ""
echo "3. Verify VS Code settings work on Windows"
echo ""
echo "🔒 SECURITY NOTE: The .env file contains sensitive credentials!"
echo "   Make sure your Windows repository is also private/secure."