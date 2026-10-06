#!/usr/bin/env sh
# Only the backend's image; see publish.sh.
exec "$(dirname "$0")/publish.sh" backend
