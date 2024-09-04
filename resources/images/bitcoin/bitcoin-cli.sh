#!/bin/bash

bitcoin-cli() {
    if [[ "$*" == *"generate"* ]]; then
        echo "Error: 'generate' are prohibited." >&2
        return 1
    else
        command bitcoin-cli "$@"
    fi
}
