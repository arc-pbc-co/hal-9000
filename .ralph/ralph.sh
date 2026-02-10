#!/bin/bash
# HAL-9000 Refactor Agent Runner
# Adapted from https://github.com/snarktank/ralph

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
MAX_ITERATIONS=50
TOOL="claude"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --tool)
            TOOL="$2"
            shift 2
            ;;
        --max)
            MAX_ITERATIONS="$2"
            shift 2
            ;;
        *)
            if [[ "$1" =~ ^[0-9]+$ ]]; then
                MAX_ITERATIONS="$1"
            fi
            shift
            ;;
    esac
done

# Get the phase directory (current directory)
PHASE_DIR=$(pwd)
PHASE_NAME=$(basename "$PHASE_DIR")

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  HAL-9000 Refactor Agent: ${YELLOW}${PHASE_NAME}${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Verify required files exist
if [ ! -f "prd.json" ]; then
    echo -e "${RED}Error: prd.json not found in ${PHASE_DIR}${NC}"
    exit 1
fi

if [ ! -f "CLAUDE.md" ]; then
    echo -e "${RED}Error: CLAUDE.md not found in ${PHASE_DIR}${NC}"
    exit 1
fi

# Initialize progress.txt if it doesn't exist
if [ ! -f "progress.txt" ]; then
    echo "# ${PHASE_NAME} Progress Log" > progress.txt
    echo "" >> progress.txt
    echo "## Codebase Patterns" >> progress.txt
    echo "" >> progress.txt
    echo "---" >> progress.txt
    echo "" >> progress.txt
fi

# Check if all stories are complete
check_complete() {
    python3 -c "
import json
with open('prd.json') as f:
    prd = json.load(f)
incomplete = [s for s in prd['userStories'] if not s['passes']]
if not incomplete:
    print('COMPLETE')
else:
    print(f'{len(incomplete)} stories remaining')
"
}

# Get next story to work on
get_next_story() {
    python3 -c "
import json
with open('prd.json') as f:
    prd = json.load(f)
incomplete = [s for s in prd['userStories'] if not s['passes']]
incomplete.sort(key=lambda x: x['priority'])
if incomplete:
    print(f\"{incomplete[0]['id']}: {incomplete[0]['title']}\")
"
}

# Main loop
ITERATION=1
while [ $ITERATION -le $MAX_ITERATIONS ]; do
    echo ""
    echo -e "${GREEN}━━━ Iteration ${ITERATION}/${MAX_ITERATIONS} ━━━${NC}"

    # Check completion status
    STATUS=$(check_complete)
    if [ "$STATUS" = "COMPLETE" ]; then
        echo -e "${GREEN}✓ All stories complete!${NC}"
        echo ""
        echo -e "${BLUE}Phase ${PHASE_NAME} finished successfully.${NC}"
        exit 0
    fi

    NEXT=$(get_next_story)
    echo -e "Next story: ${YELLOW}${NEXT}${NC}"
    echo ""

    # Change to project root for Claude Code
    PROJECT_ROOT=$(cd ../.. && pwd)

    # Run the appropriate tool
    if [ "$TOOL" = "claude" ]; then
        echo -e "${BLUE}Spawning Claude Code agent...${NC}"
        cd "$PROJECT_ROOT"

        # Run Claude Code with the phase's CLAUDE.md
        claude --print "Read ${PHASE_DIR}/CLAUDE.md and follow the instructions. The prd.json is at ${PHASE_DIR}/prd.json and progress.txt is at ${PHASE_DIR}/progress.txt"

        cd "$PHASE_DIR"
    else
        echo -e "${RED}Unknown tool: ${TOOL}${NC}"
        exit 1
    fi

    # Check if agent signaled completion
    if [ -f ".agent_complete" ]; then
        rm .agent_complete
        echo -e "${GREEN}Agent signaled completion for this iteration${NC}"
    fi

    ITERATION=$((ITERATION + 1))

    # Brief pause between iterations
    sleep 2
done

echo -e "${YELLOW}Max iterations (${MAX_ITERATIONS}) reached${NC}"
echo "Check progress.txt for status"
