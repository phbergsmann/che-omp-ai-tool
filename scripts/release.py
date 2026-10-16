#!/usr/bin/env python3
"""Plan immutable releases and monotonic compatibility tags against authenticated GHCR."""
import argparse
import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from functools import total_ordering


@total_ordering
@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int
    prerelease: tuple = ()

    @classmethod
    def parse(cls, value):
        match = re.fullmatch(r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?", value)
        if not match:
            raise ValueError(f"Invalid release tag: {value}")
        pre = tuple(match[4].split(".")) if match[4] else ()
        if any(p.isdigit() and len(p) > 1 and p.startswith("0") for p in pre):
            raise ValueError("Numeric prerelease identifiers must not have leading zeroes")
        return cls(int(match[1]), int(match[2]), int(match[3]), pre)

    def __lt__(self, other):
        core = (self.major, self.minor, self.patch)
        other_core = (other.major, other.minor, other.patch)
        if core != other_core:
            return core < other_core
        if not self.prerelease or not other.prerelease:
            return bool(self.prerelease) and not other.prerelease
        for left, right in zip(self.prerelease, other.prerelease):
            if left == right:
                continue
            if left.isdigit() and right.isdigit():
                return int(left) < int(right)
            if left.isdigit() != right.isdigit():
                return left.isdigit()
            return left < right
        return len(self.prerelease) < len(other.prerelease)


def moving_tags(version, existing):
    """Compare each compatibility line independently; prereleases never promote."""
    candidate = Version.parse(version)
    if candidate.prerelease:
        return []
    stable = []
    for tag in existing:
        try:
            parsed = Version.parse(tag)
        except ValueError:
            continue
        if not parsed.prerelease:
            stable.append(parsed)
    lines = [
        (f"v{candidate.major}.{candidate.minor}", lambda v: (v.major, v.minor) == (candidate.major, candidate.minor)),
        (f"v{candidate.major}", lambda v: v.major == candidate.major),
        ("latest", lambda v: True),
    ]
    return [tag for tag, belongs in lines if all(candidate > v for v in stable if belongs(v))]


class Registry:
    def __init__(self, image):
        if not re.fullmatch(r"ghcr\.io/[a-z0-9._-]+/[a-z0-9._/-]+", image):
            raise ValueError("Expected a lowercase GHCR image without a tag")
        self.repository = image.removeprefix("ghcr.io/")
        actor = os.environ["GITHUB_ACTOR"]
        credential = os.environ["GHCR_TOKEN"]
        authorization = base64.b64encode(f"{actor}:{credential}".encode()).decode()
        query = urllib.parse.urlencode({"service": "ghcr.io", "scope": f"repository:{self.repository}:pull,push"})
        request = urllib.request.Request(f"https://ghcr.io/token?{query}", headers={"Authorization": f"Basic {authorization}"})
        with urllib.request.urlopen(request, timeout=30) as response:
            self.token = json.load(response)["token"]

    def request(self, path, method="GET"):
        return urllib.request.urlopen(urllib.request.Request(
            f"https://ghcr.io/v2/{self.repository}/{path}", method=method,
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json"}), timeout=30)

    def tags(self):
        result = []
        path = "tags/list?n=100"
        while path:
            try:
                with self.request(path) as response:
                    result.extend(json.load(response).get("tags") or [])
                    link = response.headers.get("Link", "")
            except urllib.error.HTTPError as error:
                if error.code == 404:
                    return result
                raise
            if not link:
                break
            target = link.split("<", 1)[1].split(">", 1)[0]
            prefix = f"/v2/{self.repository}/"
            if target.startswith("https://ghcr.io"):
                target = target.removeprefix("https://ghcr.io")
            if not target.startswith(prefix):
                raise ValueError("Unexpected registry pagination URL")
            path = target[len(prefix):]
        return result

    def ensure_absent(self, tag):
        try:
            with self.request(f"manifests/{tag}", "HEAD"):
                pass
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return
            raise
        raise ValueError(f"Immutable tag already exists: {tag}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--github-output")
    args = parser.parse_args()
    Version.parse(args.version)
    registry = Registry(args.image)
    registry.ensure_absent(args.version)
    result = {"version": args.version, "image": args.image,
              "moving": ",".join(f"{args.image}:{tag}" for tag in moving_tags(args.version, registry.tags()))}
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as stream:
            for key, value in result.items():
                stream.write(f"{key}={value}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
