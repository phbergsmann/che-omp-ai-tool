#!/bin/sh
set -eu
root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
engine=${CONTAINER_ENGINE:-podman}
image=${IMAGE:-ghcr.io/phbergsmann/che-omp-ai-tool:v0.1.0}
workspace=${WORKSPACE_IMAGE:-registry.access.redhat.com/ubi9/ubi:9.6}
# Keep the default inside rootless Podman's subordinate-ID range.
uid=${SMOKE_UID:-12345}
expected="omp/$(cut -c 2- "$root/OMP_VERSION")"
volume="omp-injection-smoke-$$"
cleanup() { "$engine" volume rm -f "$volume" >/dev/null 2>&1 || :; }
trap cleanup EXIT HUP INT TERM
set --
if [ -n "${SMOKE_PLATFORM:-}" ]; then
    set -- --platform "$SMOKE_PLATFORM"
fi
# Pull before offline execution; no startup command may fetch the tool/runtime.
"$engine" pull "$@" "$workspace"
"$engine" volume create "$volume" >/dev/null
# Container-side expressions must expand in the container, not on the host.
# shellcheck disable=SC2016
"$engine" run "$@" --rm --network none --cap-drop ALL --security-opt no-new-privileges \
    --user "$uid:0" --read-only --tmpfs /home/omp:rw,exec,mode=1777 \
    --tmpfs /tmp:rw,noexec,mode=1777 --entrypoint /bin/sh "$image" -ec '
    test "$(omp --version)" = "$1"
    omp --help
    test -w "$HOME"
' smoke "$expected"
# Emulate the writable shared volume prepared by the workspace controller.
"$engine" run "$@" --rm --network none --cap-drop ALL --security-opt no-new-privileges \
    --read-only --user 0:0 --volume "$volume:/injected-tools" \
    --entrypoint /bin/sh "$image" -ec 'chmod 1777 /injected-tools'
# This is Che init's copy contract: only /usr/local/bin/omp is transferred.
"$engine" run "$@" --rm --network none --cap-drop ALL --security-opt no-new-privileges \
    --read-only --user "$uid:0" --volume "$volume:/injected-tools" \
    --entrypoint /bin/sh "$image" -ec \
    'mkdir -p /injected-tools/bin; cp /usr/local/bin/omp /injected-tools/bin/omp; chmod 0555 /injected-tools/bin/omp'
# An unrelated workspace image has no Bun, node_modules, injector ENV, or wrapper.
# An empty executable HOME forces extraction of the embedded native addon.
# shellcheck disable=SC2016
"$engine" run "$@" --rm --network none --cap-drop ALL --security-opt no-new-privileges \
    --read-only --user "$uid:$uid" \
    --volume "$volume:/injected-tools:ro" \
    --tmpfs /home/workspace:rw,exec,mode=1777 \
    --tmpfs /projects:rw,noexec,mode=1777 --tmpfs /tmp:rw,noexec,mode=1777 \
    --env HOME=/home/workspace --workdir /projects \
    --entrypoint /bin/sh "$workspace" -ec '
    export PATH="/injected-tools/bin:$PATH"
    test "$(command -v omp)" = /injected-tools/bin/omp
    test "$(omp --version)" = "$1"
    omp --help
    omp config --help
    # config help imports the native-backed command graph: require a real cache.
    test -d "$HOME/.omp/natives"
    test -n "$(find "$HOME/.omp/natives" -name "*.node" -print)"
' smoke "$expected"
printf '%s\n' "Passed offline injector and standalone workspace smoke: $expected"
