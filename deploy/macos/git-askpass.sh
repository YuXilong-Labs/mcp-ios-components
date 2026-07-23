#!/bin/bash
set -eu

case "${1:-}" in
    *Username*) printf '%s\n' "${GITLAB_USERNAME:-yuxilong}" ;;
    *Password*) printf '%s\n' "${GITLAB_TOKEN:-${GIT_LAB_TOKEN:-}}" ;;
    *) printf '\n' ;;
esac
