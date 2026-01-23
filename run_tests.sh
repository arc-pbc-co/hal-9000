#!/bin/bash
# HAL 9000 Test Runner Script

set -e

echo "========================================="
echo "HAL 9000 Test Suite"
echo "========================================="
echo ""

# Check Python version
echo "Checking Python version..."
PYTHON_CMD=""
for cmd in python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
    if command -v $cmd &> /dev/null; then
        VERSION=$($cmd --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
        MAJOR=$(echo $VERSION | cut -d. -f1)
        MINOR=$(echo $VERSION | cut -d. -f2)
        if [ "$MAJOR" -eq 3 ] && [ "$MINOR" -ge 9 ]; then
            PYTHON_CMD=$cmd
            echo "✓ Found Python $VERSION at $(which $cmd)"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "✗ Error: Python 3.9+ is required but not found"
    echo "Please install Python 3.9 or newer"
    exit 1
fi

echo ""

# Check if project is installed
echo "Checking project installation..."
if ! $PYTHON_CMD -c "import hal9000" 2>/dev/null; then
    echo "⚠ Project not installed. Installing..."
    $PYTHON_CMD -m pip install -e ".[dev]"
else
    echo "✓ Project already installed"
fi

echo ""

# Check for test PDFs
echo "Checking test data..."
PDF_COUNT=$(find research/01-superalloys-nickel-materials -name "*.pdf" 2>/dev/null | wc -l | tr -d ' ')
if [ "$PDF_COUNT" -gt 0 ]; then
    echo "✓ Found $PDF_COUNT test PDFs"
else
    echo "⚠ Warning: No test PDFs found in research/01-superalloys-nickel-materials/"
    echo "Some integration tests may be skipped"
fi

echo ""
echo "========================================="
echo "Running Tests"
echo "========================================="
echo ""

# Parse command line arguments
TEST_ARGS="$@"

if [ -z "$TEST_ARGS" ]; then
    # Default: run all tests with coverage
    echo "Running all tests with coverage..."
    $PYTHON_CMD -m pytest tests/ \
        --verbose \
        --cov=hal9000 \
        --cov-report=term-missing \
        --cov-report=html

    echo ""
    echo "========================================="
    echo "Coverage report generated: htmlcov/index.html"
    echo "========================================="
else
    # Run with custom arguments
    echo "Running tests with custom arguments: $TEST_ARGS"
    $PYTHON_CMD -m pytest $TEST_ARGS
fi

echo ""
echo "========================================="
echo "Test run complete!"
echo "========================================="
