#!/usr/bin/env sh
# Build NotFlix's server images and push them to the registry, for deploy/docker-compose.yml.
#
#   docker login registry.mfhost.de      (once)
#   scripts/publish.sh                   all three: backend, frontend, aniscraper
#   scripts/publish.sh backend           only some of them
#
# Pushes registry.mfhost.de/notflix-<name>:publish. Override with REGISTRY=..., TAG=... and the
# target platform with PLATFORM=... (default linux/amd64, also when building on an ARM Mac).
set -eu

REGISTRY="${REGISTRY:-registry.mfhost.de}"
TAG="${TAG:-publish}"
PLATFORM="${PLATFORM:-linux/amd64}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

[ $# -gt 0 ] || set -- backend frontend aniscraper
for name in "$@"; do
    case "$name" in
        backend | aniscraper) target="" ;;
        frontend) target="--target prod" ;;  # the optimized build, not the development server
        *) echo "Unknown image '$name' (backend, frontend or aniscraper)" >&2; exit 2 ;;
    esac
    image="$REGISTRY/notflix-$name:$TAG"
    echo "==> Building $image ($PLATFORM)"
    # shellcheck disable=SC2086 # $target is empty or two words
    docker build --platform "$PLATFORM" --pull $target -t "$image" "$ROOT/$name"
    echo "==> Pushing $image"
    docker push "$image"
done
echo "Published: $* ($REGISTRY, tag $TAG)"
