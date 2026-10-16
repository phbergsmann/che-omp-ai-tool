#!/bin/sh
set -eu
root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
engine=${CONTAINER_ENGINE:-podman}
version=$(cat "$root/OMP_VERSION")
image=${IMAGE:-ghcr.io/phbergsmann/che-omp-ai-tool:$version}
case "$version" in v[0-9]*.[0-9]*.[0-9]*) ;; *) echo 'OMP_VERSION must contain an upstream v-prefixed release tag' >&2; exit 1 ;; esac
exec "$engine" build --file "$root/Containerfile" --tag "$image" \
    --build-arg "OMP_VERSION=$version" \
    --build-arg "VCS_REF=${VCS_REF:-unknown}" "$@" "$root"
