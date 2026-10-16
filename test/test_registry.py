import copy
import importlib.util
import io
import json
from pathlib import Path
import unittest
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("registry", Path(__file__).resolve().parents[1] / "scripts" / "registry.py")
registry = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(registry)


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.desired = registry.render()
        self.foreign = {"providers": [{"id": "other/agent", "custom": True}],
                        "tools": [{"providerId": "other/agent", "pattern": "bundle", "runtime": "node"}],
                        "defaultAiProviders": ["other/agent"], "extension": {"keep": True}}

    def configmap(self, data=None):
        return {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {
            "name": "custom-registry", "namespace": "eclipse-che", "resourceVersion": "42",
            "labels": dict(registry.LABELS, foreign="yes"), "annotations": {"keep": "yes"}},
            "data": {"registry.json": registry.dumps(self.foreign if data is None else data), "foreign": "value"},
            "binaryData": {"foreign.bin": "YWJj"}}

    def test_canonical_and_overrides(self):
        registry.validate(self.desired, require_omp=True)
        self.assertEqual(self.desired["defaultAiProviders"], [])
        digest = "private.local:5000/team/omp@sha256:" + "a" * 64
        result = registry.render(digest, "development")
        self.assertEqual(result["tools"][0]["injectorImage"], digest)
        self.assertEqual(result["tools"][0]["tag"], "development")
        self.assertEqual(registry.render("private.local:5000/team/omp:dev")["tools"][0]["binary"], "omp")

    def test_version_file_drives_defaults_without_template_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            version = Path(directory) / "OMP_VERSION"
            with patch.object(registry, "OMP_VERSION_PATH", version):
                for value in ("v18.11.1", "v19.2.3", "v19.0.0-rc.1"):
                    version.write_text(value + "\n")
                    tool = registry.render()["tools"][0]
                    self.assertEqual(tool["tag"], value)
                    self.assertEqual(tool["injectorImage"], f"ghcr.io/phbergsmann/che-omp-ai-tool:{value}")

    def test_validate_default_renders_but_explicit_path_does_not(self):
        status, _, err, _ = self.invoke(["validate"], [])
        self.assertEqual(status, 0, err)
        with tempfile.TemporaryDirectory() as directory:
            supplied = Path(directory) / "registry.json"
            supplied.write_text(registry.dumps(self.desired))
            status, _, err, _ = self.invoke(["validate", str(supplied)], [])
            self.assertEqual(status, 0, err)
            supplied.write_text(registry.REGISTRY_PATH.read_text())
            status, _, _, _ = self.invoke(["validate", str(supplied)], [])
            self.assertEqual(status, 1)
            for invalid in ("{", '{"providers":[],"tools":{},"defaultAiProviders":[]}'):
                supplied.write_text(invalid)
                with self.subTest(invalid=invalid), patch.object(registry, "REGISTRY_PATH", supplied):
                    self.assertEqual(self.invoke(["validate"], [])[0], 1)
                    self.assertEqual(self.invoke(["validate", str(supplied)], [])[0], 1)

    def test_render_rejects_invalid_version_and_does_not_expand_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            version = Path(directory) / "OMP_VERSION"
            template = Path(directory) / "registry.json"
            with patch.object(registry, "OMP_VERSION_PATH", version):
                for invalid in ("not-a-version", "v01.2.3", "v1.02.3", "v1.2.03", "v1.2.3-rc.01"):
                    version.write_text(invalid + "\n")
                    with self.subTest(version=invalid), self.assertRaisesRegex(ValueError, "OMP_VERSION"):
                        registry.render()
                version.write_text("v18.11.1\n")
                bad = copy.deepcopy(self.desired)
                bad["tools"][0]["injectorImage"] = "example.com/omp:${SECRET}"
                template.write_text(registry.dumps(bad))
                with patch.object(registry, "REGISTRY_PATH", template), patch.dict("os.environ", {"SECRET": "private"}):
                    with self.assertRaises(ValueError):
                        registry.render()

    def test_missing_registry_and_empty_configmap(self):
        result = registry.merge(None, "openshift-devspaces", self.desired)
        self.assertEqual(result["metadata"]["namespace"], "openshift-devspaces")
        self.assertEqual(result["metadata"]["labels"], registry.LABELS)
        self.assertEqual(json.loads(result["data"]["registry.json"]), self.desired)
        empty = self.configmap()
        empty["data"] = {"foreign": "value"}
        result = registry.merge(empty, "eclipse-che", self.desired)
        self.assertEqual(result["data"]["foreign"], "value")
        self.assertEqual(json.loads(result["data"]["registry.json"]), self.desired)

    def test_merge_preserves_foreign_and_is_idempotent(self):
        original = self.configmap()
        snapshot = copy.deepcopy(original)
        result = registry.merge(original, "eclipse-che", self.desired)
        self.assertEqual(original, snapshot)
        merged = json.loads(result["data"]["registry.json"])
        for key in ("providers", "tools"):
            self.assertEqual(merged[key][0], self.foreign[key][0])
        self.assertEqual(merged["defaultAiProviders"], self.foreign["defaultAiProviders"])
        self.assertEqual(merged["extension"], self.foreign["extension"])
        self.assertEqual(result["metadata"], original["metadata"])
        self.assertEqual(result["binaryData"], original["binaryData"])
        self.assertEqual(result["data"]["foreign"], "value")
        self.assertEqual(registry.merge(result, "eclipse-che", self.desired), result)

    def test_upgrade_replaces_only_owned_tools(self):
        installed = registry.merge(self.configmap(), "eclipse-che", self.desired)
        updated = registry.render("example.com/omp:new", "new")
        result = json.loads(registry.merge(installed, "eclipse-che", updated)["data"]["registry.json"])
        self.assertEqual(result["tools"], self.foreign["tools"] + updated["tools"])
        self.assertEqual(result["providers"], self.foreign["providers"] + updated["providers"])

    def test_uninstall_preserves_shared_registry(self):
        installed = registry.merge(self.configmap(), "eclipse-che", self.desired)
        result = registry.merge(installed, "eclipse-che")
        self.assertEqual(json.loads(result["data"]["registry.json"]), self.foreign)
        self.assertEqual(result["metadata"], installed["metadata"])
        self.assertEqual(registry.merge(result, "eclipse-che"), result)
        self.assertIsNone(registry.merge(None, "eclipse-che"))

    def test_discovery(self):
        self.assertIsNone(registry.discover([]))
        item = self.configmap()
        self.assertIs(registry.discover([item]), item)
        with self.assertRaisesRegex(ValueError, "multiple"):
            registry.discover([item, item])

    def test_malformed_registry(self):
        invalid = [None, [], {}, {"providers": [], "tools": {}, "defaultAiProviders": []}]
        for bad in invalid:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                registry.validate(bad)
        for raw in ("{", '{"providers":[],"providers":[]}'):
            configmap = self.configmap()
            configmap["data"]["registry.json"] = raw
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                registry.merge(configmap, "eclipse-che", self.desired)
        configmap = self.configmap()
        configmap["binaryData"]["registry.json"] = "e30="
        with self.assertRaises(ValueError):
            registry.merge(configmap, "eclipse-che", self.desired)

    def test_strict_omp_contract_and_references(self):
        changes = [("binary", "other"), ("pattern", "bundle"), ("arch", ["x86_64"]),
                   ("injectorImage", "image"), ("injectorImage", "image:tag with spaces"),
                   ("envVarName", "OPENAI_API_KEY"), ("providerId", "missing/provider")]
        for key, value in changes:
            bad = copy.deepcopy(self.desired)
            bad["tools"][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                registry.validate(bad, require_omp=True)
        for key in ("tag", "name", "url", "binary", "pattern", "injectorImage", "arch"):
            bad = copy.deepcopy(self.desired)
            del bad["tools"][0][key]
            with self.subTest(missing=key), self.assertRaises(ValueError):
                registry.validate(bad, require_omp=True)
        bad = copy.deepcopy(self.desired)
        bad["providers"].append(copy.deepcopy(bad["providers"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate provider"):
            registry.validate(bad)
        bad = copy.deepcopy(self.desired)
        bad["tools"].append(copy.deepcopy(bad["tools"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate OMP"):
            registry.validate(bad)
        registry.validate(self.foreign)  # Foreign bundle patterns and extension fields remain legal.

    def invoke(self, args, outputs):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(registry, "kubectl", side_effect=outputs) as command, redirect_stdout(out), redirect_stderr(err):
            status = registry.main(args)
        return status, out.getvalue(), err.getvalue(), command

    def test_install_creates_or_replaces_with_resource_version(self):
        status, _, _, command = self.invoke(["install", "--namespace", "eclipse-che"], ['{"items":[]}', "created\n"])
        self.assertEqual(status, 0)
        self.assertEqual(command.call_args_list[0].args[2][3], registry.SELECTOR)
        self.assertEqual(command.call_args_list[1].args[2], ["create", "-f", "-"])
        current = self.configmap()
        status, _, _, command = self.invoke(["install", "--namespace", "openshift-devspaces"], [json.dumps({"items": [current]}), "replaced\n"])
        self.assertEqual(status, 0)
        self.assertEqual(command.call_args_list[1].args[2], ["replace", "-f", "-"])
        self.assertEqual(command.call_args_list[1].args[3]["metadata"]["resourceVersion"], "42")

    def test_dry_run_and_ambiguous_registry_never_write(self):
        status, out, _, command = self.invoke(["install", "--namespace", "eclipse-che", "--dry-run"], ['{"items":[]}'])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(out)["kind"], "ConfigMap")
        self.assertEqual(command.call_count, 1)
        status, _, err, command = self.invoke(["install", "--namespace", "eclipse-che"], [json.dumps({"items": [self.configmap(), self.configmap()]})])
        self.assertEqual(status, 1)
        self.assertIn("multiple", err)
        self.assertEqual(command.call_count, 1)

    def test_missing_resource_version_refuses_write(self):
        current = self.configmap()
        del current["metadata"]["resourceVersion"]
        status, _, err, command = self.invoke(["install", "--namespace", "eclipse-che"], [json.dumps({"items": [current]})])
        self.assertEqual(status, 1)
        self.assertIn("resourceVersion", err)
        self.assertEqual(command.call_count, 1)

    def test_kubectl_conflict_propagates_without_retry(self):
        completed = type("Result", (), {"returncode": 1, "stderr": "Conflict: object modified", "stdout": ""})()
        with patch.object(registry.subprocess, "run", return_value=completed) as run:
            with self.assertRaisesRegex(ValueError, "Conflict"):
                registry.kubectl("oc", "eclipse-che", ["replace", "-f", "-"], self.configmap())
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][:3], ["oc", "--namespace", "eclipse-che"])


if __name__ == "__main__":
    unittest.main()
