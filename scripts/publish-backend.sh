#!/usr/bin/env sh
# Build the backend's Docker image and push it to the registry.
#
#   docker login registry.mfhost.de      (once)
#   scripts/publish-backend.sh
#
# Pushes registry.mfhost.de/notflix-backend:publish. Override with IMAGE=... and TAG=...,
# and the target platform with PLATFORM=... (default linux/amd64, also when building on an ARM
# Mac). The image runs the database migrations when it starts.
set -eu

IMAGE="${IMAGE:-registry.mfhost.de/notflix-backend}"
TAG="${TAG:-publish}"
PLATFORM="${PLATFORM:-linux/amd64}"
BACKEND="$(cd "$(dirname "$0")/../backend" && pwd)"

echo "Building $IMAGE:$TAG ($PLATFORM) from $BACKEND"
docker build --platform "$PLATFORM" --pull -t "$IMAGE:$TAG" "$BACKEND"
echo "Pushing $IMAGE:$TAG"
docker push "$IMAGE:$TAG"
echo "Published $IMAGE:$TAG"
