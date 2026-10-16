import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock
import urllib.error

SPEC = importlib.util.spec_from_file_location("release", Path(__file__).parents[1] / "scripts/release.py")
release = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = release
SPEC.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def test_semver_order(self):
        ordered = ["v1.0.0-alpha", "v1.0.0-alpha.1", "v1.0.0-alpha.beta", "v1.0.0-beta", "v1.0.0-beta.2", "v1.0.0-beta.11", "v1.0.0-rc.1", "v1.0.0", "v1.0.1", "v1.10.0", "v2.0.0"]
        versions = list(map(release.Version.parse, ordered))
        self.assertEqual(sorted(reversed(versions)), versions)
        for a, b in zip(versions, versions[1:]):
            self.assertLess(a, b)

    def test_invalid_tags(self):
        for tag in ["1.0.0", "v01.0.0", "v1.0", "v1.0.0-01", "v1.0.0+a", "v1.0.0-", "v1.0.0\n"]:
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                release.Version.parse(tag)

    def test_first_release(self):
        self.assertEqual(release.moving_tags("v1.2.3", []), ["v1.2", "v1", "latest"])

    def test_old_line_advances_independently(self):
        self.assertEqual(release.moving_tags("v1.2.4", ["v1.2.3", "v1.3.0", "v2.0.0"]), ["v1.2"])
        self.assertEqual(release.moving_tags("v1.4.0", ["v1.3.0", "v2.0.0"]), ["v1.4", "v1"])

    def test_old_patch_cannot_rollback(self):
        self.assertEqual(release.moving_tags("v1.2.2", ["v1.2.3"]), [])
        self.assertEqual(release.moving_tags("v1.2.3", ["v1.2.3"]), [])

    def test_prerelease_never_promotes(self):
        self.assertEqual(release.moving_tags("v3.0.0-rc.1", []), [])
        self.assertEqual(release.moving_tags("v1.2.3", ["v9.0.0-beta", "latest", "v1"]), ["v1.2", "v1", "latest"])

    def test_existing_full_tag_rejected(self):
        registry = release.Registry.__new__(release.Registry)
        registry.request = MagicMock()
        with self.assertRaisesRegex(ValueError, "Immutable tag already exists"):
            registry.ensure_absent("v1.2.3")

    def test_only_not_found_allows_new_tag(self):
        registry = release.Registry.__new__(release.Registry)
        registry.request = MagicMock(side_effect=urllib.error.HTTPError("url", 404, "missing", {}, None))
        registry.ensure_absent("v1.2.3")
        for code in (401, 403, 429, 500):
            registry.request = MagicMock(side_effect=urllib.error.HTTPError("url", code, "failure", {}, None))
            with self.subTest(code=code), self.assertRaises(urllib.error.HTTPError):
                registry.ensure_absent("v1.2.3")


if __name__ == "__main__":
    unittest.main()
