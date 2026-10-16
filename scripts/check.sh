#!/bin/sh
# Same inexpensive checks locally and in CI; no image build or cluster access.
set -eu
engine=${CONTAINER_ENGINE:-docker}
python3 -m unittest discover -s test -p 'test_*.py'
python3 scripts/registry.py validate
python3 -c 'import json,pathlib; [json.loads(p.read_text()) for pattern in ("*.json", "registry/**/*.json") for p in pathlib.Path(".").glob(pattern)]'
python3 -c 'import json,pathlib; p=pathlib.Path("registry/registry.json"); assert p.read_text() == json.dumps(json.loads(p.read_text()), indent=2, ensure_ascii=False) + "\n", "registry.json must use two-space JSON formatting"'
"$engine" run --rm -v "$PWD:/work:ro" -w /work koalaman/shellcheck:v0.10.0 scripts/*.sh
"$engine" run --rm -i hadolint/hadolint:v2.12.0 < Containerfile
python3 -m yamllint -c .yamllint .yamllint .github/workflows registry
npx --yes markdownlint-cli2@0.17.2 '*.md' 'docs/**/*.md'
