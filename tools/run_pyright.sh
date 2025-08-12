#!/usr/bin/env bash
# Type checking script for IB Trading System
# Uses per-folder strictness configured in pyrightconfig.json

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🔍 Running Type Checking (Pyright)${NC}"

# Check if pyright is available
if ! command -v pyright &> /dev/null; then
    echo -e "${YELLOW}⚠️  Installing pyright...${NC}"
    npx --yes pyright --version > /dev/null
fi

# Run pyright with configured settings
echo -e "\n${GREEN}� Type checking with per-folder strictness...${NC}"
if npx --yes pyright; then
    echo -e "\n${GREEN}✅ Type checking passed${NC}"
    exit 0
else
    exit_code=$?
    echo -e "\n${RED}❌ Type checking failed${NC}"
    echo -e "${YELLOW}💡 See docs/typing_ignores.md for ignore guidelines${NC}"
    exit $exit_code
fi
    echo -e "${RED}❌ src/ has type errors${NC}"
    # Show errors but continue
    pyright src/ 2>&1 | head -20
fi

echo -e "\n${GREEN}📁 Checking scripts/ and tests/ (basic mode)${NC}"
if pyright scripts/ tests/ --outputjson > pyright_basic.json 2>/dev/null; then
    echo -e "${GREEN}✅ scripts/ and tests/ type checking passed${NC}"
else
    BASIC_ERRORS=$?
    echo -e "${YELLOW}⚠️  scripts/tests/ have warnings (allowed)${NC}"
fi

echo -e "\n${GREEN}🚫 Checking for undocumented type ignores${NC}"
UNDOCUMENTED_IGNORES=$(grep -rn "# type: ignore$" src/ scripts/ tests/ 2>/dev/null | wc -l || echo "0")
if [ "$UNDOCUMENTED_IGNORES" -gt 0 ]; then
    IGNORE_VIOLATIONS=1
    echo -e "${RED}❌ Found $UNDOCUMENTED_IGNORES undocumented type ignores:${NC}"
    grep -rn "# type: ignore$" src/ scripts/ tests/ 2>/dev/null || true
    echo -e "${YELLOW}💡 Add specific error codes: # type: ignore[attr-defined]${NC}"
else
    echo -e "${GREEN}✅ All type ignores are documented${NC}"
fi

# Summary
echo -e "\n${GREEN}📊 Type Checking Summary${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ $STRICT_ERRORS -eq 0 ]; then
    echo -e "src/ (strict):     ${GREEN}✅ PASS${NC}"
else
    echo -e "src/ (strict):     ${RED}❌ FAIL${NC}"
fi

if [ $BASIC_ERRORS -eq 0 ]; then
    echo -e "scripts/tests/:    ${GREEN}✅ PASS${NC}"
else
    echo -e "scripts/tests/:    ${YELLOW}⚠️  WARNINGS${NC}"
fi

if [ $IGNORE_VIOLATIONS -eq 0 ]; then
    echo -e "ignore policy:     ${GREEN}✅ COMPLIANT${NC}"
else
    echo -e "ignore policy:     ${RED}❌ VIOLATIONS${NC}"
fi

# Cleanup temp files
rm -f pyright_src.json pyright_basic.json

# Exit codes
if [ $STRICT_ERRORS -ne 0 ] || [ $IGNORE_VIOLATIONS -ne 0 ]; then
    echo -e "\n${RED}💥 Type checking failed${NC}"
    echo -e "📖 See docs/typing_ignores.md for guidelines"
    exit 1
else
    echo -e "\n${GREEN}🎉 Type checking passed${NC}"
    exit 0
fi
