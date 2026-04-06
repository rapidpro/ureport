#!/bin/sh

# auto check for pep8 so we don't check in bad code
FILES=$(git diff --cached --name-only --diff-filter=ACM | grep -e '\.py$')

if [ -n "$FILES" ]; then
    ruff check --select I --fix -q $FILES
fi

if [ -n "$FILES" ]; then
    ruff format -q $FILES
fi

if [ -n "$FILES" ]; then
    ruff check -q $FILES
fi
