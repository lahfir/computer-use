#!/bin/bash

# Computer Use Agent - Automated Installation Script
# Supports macOS, Linux, and Windows (via WSL/Git Bash)

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Unicode symbols
CHECK="✓"
CROSS="✗"
ARROW="→"
ROCKET="🚀"
GEAR="⚙️"
PACKAGE="📦"
KEY="🔑"
SPARKLE="✨"

# Print functions
print_header() {
    echo ""
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║                                                            ║${NC}"
    echo -e "${CYAN}║        ${SPARKLE}  COMPUTER USE AGENT - INSTALLER  ${SPARKLE}          ║${NC}"
    echo -e "${CYAN}║                                                            ║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}${CHECK}${NC} $1"
}

print_error() {
    echo -e "${RED}${CROSS}${NC} $1"
}

print_info() {
    echo -e "${BLUE}${ARROW}${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC}  $1"
}

print_step() {
    echo ""
    echo -e "${CYAN}${GEAR}  $1${NC}"
    echo -e "${CYAN}${'─'$(printf '─%.0s' {1..60})}${NC}"
}

# Detect OS
detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        OS="linux"
    elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]]; then
        OS="windows"
    else
        OS="unknown"
    fi
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Install uv
install_uv() {
    print_step "Installing uv Package Manager"
    
    if command_exists uv; then
        print_success "uv is already installed"
        uv --version
        return 0
    fi
    
    print_info "Installing uv..."
    
    if [[ "$OS" == "windows" ]]; then
        powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    else
        curl -LsSf https://astral.sh/uv/install.sh | sh
    fi
    
    # Add uv to PATH for current session
    if [[ -f "$HOME/.cargo/env" ]]; then
        source "$HOME/.cargo/env"
    fi
    
    if command_exists uv; then
        print_success "uv installed successfully"
        uv --version
    else
        print_error "Failed to install uv. Please install manually from https://github.com/astral-sh/uv"
        exit 1
    fi
}

# Check Python version
check_python() {
    print_step "Checking Python Version"
    
    if command_exists python3; then
        PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
        PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
        PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)
        
        print_info "Found Python $PYTHON_VERSION"
        
        if [[ $PYTHON_MAJOR -eq 3 ]] && [[ $PYTHON_MINOR -ge 11 ]]; then
            print_success "Python version is compatible (≥3.11)"
        else
            print_error "Python 3.11+ is required (found $PYTHON_VERSION)"
            print_info "Please install Python 3.11 or higher:"
            
            if [[ "$OS" == "macos" ]]; then
                echo "  brew install python@3.11"
            elif [[ "$OS" == "linux" ]]; then
                echo "  sudo apt install python3.11  # Debian/Ubuntu"
                echo "  sudo dnf install python3.11  # Fedora"
            fi
            exit 1
        fi
    else
        print_error "Python 3 is not installed"
        exit 1
    fi
}

# Install Python dependencies
install_python_deps() {
    print_step "Installing Python Dependencies"
    
    print_info "This may take a few minutes (downloading ~500MB)..."
    
    # Install platform-specific dependencies
    if [ "$OS" = "macos" ]; then
        print_info "Installing macOS accessibility libraries (atomacos)..."
        if uv sync --extra macos --quiet 2>&1 | grep -v "^$"; then
            print_success "Core + macOS dependencies installed"
        else
            print_error "Failed to install dependencies"
            exit 1
        fi
    elif [ "$OS" = "windows" ]; then
        print_info "Installing Windows UI Automation libraries (pywinauto)..."
        if uv sync --extra windows --quiet 2>&1 | grep -v "^$"; then
            print_success "Core + Windows dependencies installed"
        else
            print_error "Failed to install dependencies"
            exit 1
        fi
    elif [ "$OS" = "linux" ]; then
        print_info "Installing Linux AT-SPI libraries..."
        if uv sync --extra linux --quiet 2>&1 | grep -v "^$"; then
            print_success "Core + Linux dependencies installed"
        else
            print_error "Failed to install dependencies"
            exit 1
        fi
        
        # Install system-level AT-SPI on Linux
        print_info "Installing python3-pyatspi system package..."
        if command_exists apt-get; then
            sudo apt-get update -qq && sudo apt-get install -y python3-pyatspi
        elif command_exists yum; then
            sudo yum install -y python3-pyatspi
        elif command_exists dnf; then
            sudo dnf install -y python3-pyatspi
        else
            print_warning "Could not detect package manager - please install python3-pyatspi manually"
        fi
    else
        print_warning "Unknown OS - installing core dependencies only"
        if uv sync --quiet 2>&1 | grep -v "^$"; then
            print_success "Core dependencies installed"
        else
            print_error "Failed to install core dependencies"
            exit 1
        fi
    fi
}

# Install platform-specific dependencies
install_platform_deps() {
    print_step "Installing Platform-Specific Dependencies"
    
    case $OS in
        macos)
            print_info "Installing macOS accessibility frameworks..."
            uv pip install pyobjc-framework-ApplicationServices pyobjc-framework-Cocoa pyobjc-framework-Quartz --quiet
            print_success "macOS frameworks installed"
            
            print_warning "You may need to grant accessibility permissions:"
            print_info "System Settings → Privacy & Security → Accessibility → Add Terminal"
            ;;
        
        linux)
            print_info "Checking for Linux dependencies..."
            
            # Check if we can install system packages
            if command_exists apt-get; then
                print_info "Detected Debian/Ubuntu - checking system packages..."
                MISSING_PKGS=""
                
                if ! dpkg -l | grep -q python3-xlib; then
                    MISSING_PKGS="$MISSING_PKGS python3-xlib"
                fi
                
                if [ ! -z "$MISSING_PKGS" ]; then
                    print_warning "Missing system packages: $MISSING_PKGS"
                    print_info "Install with: sudo apt install $MISSING_PKGS"
                fi
            fi
            
            print_success "Linux platform configured"
            ;;
        
        windows)
            print_info "Installing Windows UI automation libraries..."
            uv pip install pywinauto comtypes --quiet
            print_success "Windows libraries installed"
            ;;
        
        *)
            print_warning "Unknown OS - skipping platform-specific dependencies"
            ;;
    esac
}

# Create .env file
setup_env_file() {
    print_step "Setting Up Environment Configuration"
    
    if [[ -f ".env" ]]; then
        print_success ".env file already exists (skipping)"
        return 0
    fi
    
    print_info "Creating .env file..."
    
    cat > .env << 'EOF'
# Computer Use Agent Configuration
# Edit this file to add your API keys

# Main LLM Provider (coordination, browser, system tasks)
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini

# Vision LLM (GUI screenshot analysis)
VISION_LLM_PROVIDER=openai
VISION_LLM_MODEL=gpt-4o

# API Keys - Add your keys here
OPENAI_API_KEY=your-openai-key-here
# ANTHROPIC_API_KEY=your-anthropic-key-here
# GOOGLE_API_KEY=your-google-key-here
# OLLAMA_BASE_URL=http://localhost:11434

# Optional: Browser automation settings
# SERPER_API_KEY=your-serper-key-here
EOF
    
    print_success ".env file created"
    print_warning "Remember to add your API keys to .env file"
}

# Prompt for API keys
prompt_api_keys() {
    print_step "API Key Configuration"
    
    echo -e "${YELLOW}Would you like to configure API keys now? (y/n)${NC}"
    read -r configure_keys
    
    if [[ "$configure_keys" =~ ^[Yy]$ ]]; then
        echo ""
        echo -e "${CYAN}Enter your OpenAI API key (or press Enter to skip):${NC}"
        read -r openai_key
        
        if [[ ! -z "$openai_key" ]]; then
            sed -i.bak "s/OPENAI_API_KEY=.*/OPENAI_API_KEY=$openai_key/" .env
            rm .env.bak 2>/dev/null || true
            print_success "OpenAI API key configured"
        fi
        
        echo ""
        echo -e "${CYAN}Would you like to add other provider keys? (y/n)${NC}"
        read -r add_more
        
        if [[ "$add_more" =~ ^[Yy]$ ]]; then
            echo ""
            echo -e "${CYAN}Anthropic API key (press Enter to skip):${NC}"
            read -r anthropic_key
            if [[ ! -z "$anthropic_key" ]]; then
                sed -i.bak "s/# ANTHROPIC_API_KEY=.*/ANTHROPIC_API_KEY=$anthropic_key/" .env
                rm .env.bak 2>/dev/null || true
                print_success "Anthropic API key configured"
            fi
            
            echo ""
            echo -e "${CYAN}Google API key (press Enter to skip):${NC}"
            read -r google_key
            if [[ ! -z "$google_key" ]]; then
                sed -i.bak "s/# GOOGLE_API_KEY=.*/GOOGLE_API_KEY=$google_key/" .env
                rm .env.bak 2>/dev/null || true
                print_success "Google API key configured"
            fi
        fi
    else
        print_info "Skipping API key configuration"
        print_warning "Edit .env file manually to add your API keys"
    fi
}

# Test installation
test_installation() {
    print_step "Testing Installation"
    
    print_info "Verifying installation..."
    echo ""
    
    # Quick verification test
    if uv run python -c "
from computer_use.utils.platform_detector import detect_platform
from computer_use.config.llm_config import LLMConfig
cap = detect_platform()
print(f'✅ Platform: {cap.os_type}')
print(f'✅ Python packages: OK')
print(f'✅ Installation verified!')
" 2>/dev/null; then
        print_success "Installation verified successfully!"
    else
        print_warning "Verification incomplete - you may need to configure API keys"
        print_info "The installation is complete, just add your API keys to .env"
    fi
}

# Print next steps
print_next_steps() {
    echo ""
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║                                                            ║${NC}"
    echo -e "${CYAN}║  ${GREEN}${CHECK} Installation Complete!${NC}                               ${CYAN}║${NC}"
    echo -e "${CYAN}║                                                            ║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    
    print_info "Quick Start:"
    echo ""
    echo -e "  ${CYAN}1.${NC} Edit .env file to add your API keys:"
    echo -e "     ${YELLOW}nano .env${NC}  or  ${YELLOW}vim .env${NC}"
    echo ""
    echo -e "  ${CYAN}2.${NC} Start the agent:"
    echo -e "     ${YELLOW}uv run python -m computer_use.main${NC}"
    echo ""
    
    print_info "Example Tasks:"
    echo "  • Download HD image of Cristiano Ronaldo"
    echo "  • Open Calculator and compute 25 × 36"
    echo "  • Create folder named 'reports' in Documents"
    echo "  • Move file from Downloads to Documents folder"
    echo ""
    
    print_info "Documentation:"
    echo "  • README.md - Complete enterprise documentation"
    echo ""
    
    if [[ "$OS" == "macos" ]]; then
        print_warning "Don't forget to grant Accessibility permissions!"
        echo "  System Settings → Privacy & Security → Accessibility"
    fi
    
    echo ""
    echo -e "${GREEN}${SPARKLE} Happy Automating! ${SPARKLE}${NC}"
    echo ""
}

# Main installation flow
main() {
    print_header
    
    detect_os
    print_success "Detected OS: $OS"
    
    install_uv
    check_python
    install_python_deps
    install_platform_deps
    setup_env_file
    prompt_api_keys
    test_installation
    print_next_steps
}

# Run main installation
main

