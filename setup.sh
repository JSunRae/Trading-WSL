#!/bin/bash
"""
Trading Project Setup Script

This script automates the initial setup of the trading project.
Run this after cloning the repository or moving to a new machine.
"""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Main setup function
setup_project() {
    echo "============================================================"
    echo "🚀 TRADING PROJECT SETUP"
    echo "============================================================"
    
    # Check Python version
    print_status "Checking Python installation..."
    if command_exists python3; then
        PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
        print_success "Python $PYTHON_VERSION found"
    else
        print_error "Python3 not found. Please install Python 3.8 or higher."
        exit 1
    fi
    
    # Check if virtual environment exists
    if [ -d ".venv" ]; then
        print_warning "Virtual environment already exists. Skipping creation."
    else
        print_status "Creating virtual environment..."
        python3 -m venv .venv
        if [ $? -eq 0 ]; then
            print_success "Virtual environment created"
        else
            print_error "Failed to create virtual environment"
            exit 1
        fi
    fi
    
    # Activate virtual environment
    print_status "Activating virtual environment..."
    source .venv/bin/activate
    
    # Upgrade pip
    print_status "Upgrading pip..."
    pip install --upgrade pip
    
    # Install dependencies
    print_status "Installing dependencies..."
    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt
        if [ $? -eq 0 ]; then
            print_success "Dependencies installed"
        else
            print_error "Failed to install dependencies"
            exit 1
        fi
    else
        print_error "requirements.txt not found"
        exit 1
    fi
    
    # Create config file if it doesn't exist
    if [ ! -f "config/config.json" ]; then
        print_status "Creating configuration file..."
        cp config/config.example.json config/config.json
        print_success "Configuration file created"
        print_warning "Please update config/config.json with your settings"
    else
        print_warning "Configuration file already exists"
    fi
    
    # Create necessary directories
    print_status "Creating project directories..."
    mkdir -p data logs
    print_success "Directories created"
    
    # Run verification
    print_status "Running setup verification..."
    python verify_setup.py
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "============================================================"
        print_success "🎉 SETUP COMPLETE!"
        echo "============================================================"
        echo ""
        echo "Next steps:"
        echo "1. Update config/config.json with your IB settings"
        echo "2. Start Interactive Brokers TWS or Gateway"
        echo "3. Run: python src/ib_Main.py"
        echo ""
        echo "For help, run: python quick_start.py"
    else
        print_error "Setup verification failed. Please check the errors above."
        exit 1
    fi
}

# Run setup
setup_project
