#!/usr/bin/env sh
# Build NotFlix's server images and push them to the registry, for deploy/docker-compose.yml.
#
#   docker login registry.uwuenterprises.de      (once)
#   scripts/publish.sh                   the server's image: backend
#   scripts/publish.sh backend frontend  others too (the web app, aniscraper)
#
# Pushes registry.uwuenterprises.de/notflix-<name>:latest. Override with REGISTRY=..., TAG=... and the
# target platform with PLATFORM=... (default linux/amd64, also when building on an ARM Mac).
set -eu

REGISTRY="${REGISTRY:-registry.uwuenterprises.de}"
TAG="${TAG:-latest}"
PLATFORM="${PLATFORM:-linux/amd64}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Printed by the backend when it starts: shows which build a server runs.
VERSION="$(git -C "$ROOT" describe --always --dirty 2>/dev/null || echo unknown) $(date -u +%Y-%m-%dT%H:%MZ)"

[ $# -gt 0 ] || set -- backend
for name in "$@"; do
    case "$name" in
        backend | aniscraper) target="" ;;
        frontend) target="--target prod" ;;  # the optimized build, not the development server
        *) echo "Unknown image '$name' (backend, frontend or aniscraper)" >&2; exit 2 ;;
    esac
    image="$REGISTRY/notflix-$name:$TAG"
    echo "==> Building $image ($PLATFORM)"
    # shellcheck disable=SC2086 # $target is empty or two words
    docker build --platform "$PLATFORM" --pull $target --build-arg NOTFLIX_VERSION="$VERSION" \
        -t "$image" "$ROOT/$name"
    echo "==> Pushing $image"
    docker push "$image"
done
echo "Published: $* ($REGISTRY, tag $TAG)"
