#!/usr/bin/env python3
"""Validate and safely merge the reserved oh-my-pi/omp Che registry identity."""
import argparse
import copy
import json
from pathlib import Path
import re
import subprocess
import sys

PROVIDER_ID = "oh-my-pi/omp"
REGISTRY_PATH = Path(__file__).resolve().parents[1] / "registry" / "registry.json"
LABELS = {"app.kubernetes.io/component": "ai-tool-registry",
          "app.kubernetes.io/part-of": "che.eclipse.org"}
SELECTOR = ",".join(f"{key}={value}" for key, value in LABELS.items())


def text(value, description):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{description} must be a nonempty string")


def image_reference(value):
    text(value, "injectorImage")
    if re.search(r"\s", value) or "://" in value:
        raise ValueError("injectorImage must be a container image reference")
    if "@" in value:
        if not re.fullmatch(r"[^@]+@sha256:[0-9a-fA-F]{64}", value):
            raise ValueError("injectorImage digest must be sha256 with 64 hex digits")
    elif not re.fullmatch(r"[^\s@]+:[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", value) or ":" not in value.rsplit("/", 1)[-1]:
        raise ValueError("injectorImage must have an explicit tag or sha256 digest")


def validate(registry, require_omp=False):
    if not isinstance(registry, dict):
        raise ValueError("registry.json must be an object")
    for key in ("providers", "tools", "defaultAiProviders"):
        if not isinstance(registry.get(key), list):
            raise ValueError(f"registry.json {key} must be an array")
    providers = set()
    for provider in registry["providers"]:
        if not isinstance(provider, dict):
            raise ValueError("provider must be an object")
        identity = provider.get("id")
        text(identity, "provider id")
        if not re.fullmatch(r"[^/\s]+/[^/\s]+", identity):
            raise ValueError("provider id must use vendor/product format")
        if identity in providers:
            raise ValueError(f"duplicate provider id: {identity}")
        providers.add(identity)
        if identity == PROVIDER_ID:
            for field in ("name", "publisher", "description", "docsUrl"):
                text(provider.get(field), f"OMP provider {field}")
    tags = set()
    omp_count = 0
    for tool in registry["tools"]:
        if not isinstance(tool, dict):
            raise ValueError("tool must be an object")
        identity = tool.get("providerId")
        text(identity, "tool providerId")
        if identity not in providers:
            raise ValueError(f"tool references unknown provider: {identity}")
        if identity != PROVIDER_ID:
            continue  # Do not impose OMP's injection contract on other tools.
        omp_count += 1
        for field in ("tag", "name", "url", "binary", "pattern", "injectorImage"):
            text(tool.get(field), f"OMP tool {field}")
        if tool["tag"] in tags:
            raise ValueError("duplicate OMP tool tag")
        tags.add(tool["tag"])
        if tool["binary"] != "omp" or tool["pattern"] != "init":
            raise ValueError("OMP requires binary omp and pattern init")
        if tool.get("arch") != ["x86_64", "arm64"]:
            raise ValueError("OMP arch must be [x86_64, arm64]")
        if "envVarName" in tool:
            raise ValueError("OMP must not require a global model-provider API key")
        image_reference(tool["injectorImage"])
    for identity in registry["defaultAiProviders"]:
        text(identity, "defaultAiProviders entry")
    if require_omp and (PROVIDER_ID not in providers or not omp_count):
        raise ValueError("registry must contain the OMP provider and at least one OMP tool")
    return registry


def load_json(value):
    def unique(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = item
        return result
    def invalid_constant(constant):
        raise ValueError(f"invalid JSON constant: {constant}")
    return json.loads(value, object_pairs_hook=unique, parse_constant=invalid_constant)


def dumps(value):
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def render(image=None, tag=None):
    registry = load_json(REGISTRY_PATH.read_text())
    for tool in registry["tools"]:
        if image is not None:
            tool["injectorImage"] = image
        if tag is not None:
            tool["tag"] = tag
    return validate(registry, require_omp=True)


def discover(items):
    if not isinstance(items, list):
        raise ValueError("kubectl did not return a ConfigMap list")
    if len(items) > 1:
        raise ValueError("multiple AI registry ConfigMaps match both labels; resolve ambiguity first")
    return items[0] if items else None


def merge(configmap, namespace, desired=None):
    if configmap is None:
        if desired is None:
            return None
        result = {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {
            "name": "ai-tool-registry", "namespace": namespace, "labels": dict(LABELS)}, "data": {}}
        registry = {"providers": [], "tools": [], "defaultAiProviders": []}
    else:
        result = copy.deepcopy(configmap)
        data = result.get("data", {})
        if not isinstance(data, dict):
            raise ValueError("ConfigMap data must be an object")
        if "registry.json" in result.get("binaryData", {}):
            raise ValueError("registry.json must be text data, not binaryData")
        raw = data.get("registry.json")
        if raw is None:
            registry = {"providers": [], "tools": [], "defaultAiProviders": []}
        elif not isinstance(raw, str):
            raise ValueError("ConfigMap registry.json must be a JSON string")
        else:
            registry = validate(load_json(raw))
    registry["providers"] = [p for p in registry["providers"] if p["id"] != PROVIDER_ID]
    registry["tools"] = [t for t in registry["tools"] if t["providerId"] != PROVIDER_ID]
    if desired is not None:
        validate(desired, require_omp=True)
        registry["providers"].extend(copy.deepcopy([p for p in desired["providers"] if p["id"] == PROVIDER_ID]))
        registry["tools"].extend(copy.deepcopy([t for t in desired["tools"] if t["providerId"] == PROVIDER_ID]))
    validate(registry)
    result.setdefault("data", {})["registry.json"] = dumps(registry)
    return result


def kubectl(executable, namespace, arguments, document=None):
    command = [executable, "--namespace", namespace, *arguments]
    result = subprocess.run(command, input=None if document is None else dumps(document),
                            text=True, capture_output=True, check=False)
    if result.returncode:
        raise ValueError(f"kubectl failed (no retry or blind overwrite): {result.stderr.strip()}")
    return result.stdout


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("validate")
    check.add_argument("path", nargs="?", type=Path, default=REGISTRY_PATH)
    rendered = commands.add_parser("render")
    rendered.add_argument("--image", required=True)
    rendered.add_argument("--tag")
    for action in ("install", "uninstall"):
        command = commands.add_parser(action)
        command.add_argument("--namespace", required=True)
        command.add_argument("--kubectl", default="kubectl")
        command.add_argument("--dry-run", action="store_true")
        if action == "install":
            command.add_argument("--image")
            command.add_argument("--tag")
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            validate(load_json(args.path.read_text()), require_omp=True)
            print("Registry is valid")
        elif args.command == "render":
            print(dumps(render(args.image, args.tag)), end="")
        else:
            desired = render(args.image, args.tag) if args.command == "install" else None
            response = load_json(kubectl(args.kubectl, args.namespace,
                ["get", "configmaps", "--selector", SELECTOR, "-o", "json"]))
            current = discover(response.get("items"))
            updated = merge(current, args.namespace, desired)
            if updated is None:
                print("No registry exists; nothing to uninstall", file=sys.stderr)
            elif args.dry_run:
                print(dumps(updated), end="")
            else:
                if current is not None and not current.get("metadata", {}).get("resourceVersion"):
                    raise ValueError("existing ConfigMap lacks resourceVersion; refusing unsafe replacement")
                operation = "create" if current is None else "replace"
                print(kubectl(args.kubectl, args.namespace, [operation, "-f", "-"], updated), end="")
    except (ValueError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
