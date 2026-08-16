import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "integrations/xray_bash_onekey/repository_files"
SYSTEMD = INTEGRATION / "systemd"
SCRIPTS = INTEGRATION / "scripts"


class Tests(unittest.TestCase):
    def test_observer_default_is_real_host_root(self):
        source = (SCRIPTS / "rill_xray_agent_observe.py").read_text()
        self.assertIn('ROOT = Path(os.environ.get("RILL_XRAY_HOST_ROOT", "/etc/' + "i" + "d" + "l" + "e" + "l" + "e" + "o" + '"))', source)
        self.assertNotIn("/etc/rill-xray-agent/host", source)

    def test_observe_service_env_maps_to_real_root(self):
        unit = (SYSTEMD / "rill-xray-agent-xray-observe.service").read_text()
        self.assertIn("Environment=RILL_XRAY_HOST_ROOT=/etc/" + "i" + "d" + "l" + "e" + "l" + "e" + "o", unit)
        self.assertNotIn("/etc/rill-xray-agent/host", unit)

    def test_observe_path_watches_real_xray_config(self):
        unit = (SYSTEMD / "rill-xray-agent-xray-observe.path").read_text()
        self.assertIn("PathChanged=/etc/" + "i" + "d" + "l" + "e" + "l" + "e" + "o" + "/conf/xray/config.json", unit)

    def test_observer_produces_valid_observation_for_real_layout(self):
        with tempfile.TemporaryDirectory(prefix="rxa-observe-") as tmp:
            tmp = Path(tmp)
            root = tmp / "root"
            (root / "conf/xray").mkdir(parents=True)
            (root / "conf/xray/config.json").write_text('{"inbounds":[]}')
            data, _ = self._observe(tmp, root)
            self.assertEqual(data["schemaVersion"], 1)
            self.assertTrue(data["xrayConfig"]["present"])
            self.assertIn("services", data)

    def _observe(self, tmp, root, with_generation=None):
        status = tmp / "status.json"
        topology = tmp / "route-topology.json"
        history = tmp / "history"
        env = dict(os.environ)
        env["RILL_XRAY_HOST_ROOT"] = str(root)
        env["RILL_XRAY_AGENT_OUTPUT"] = str(status)
        env["RILL_XRAY_AGENT_HISTORY"] = str(history)
        env["RILL_XRAY_AGENT_LOCK"] = str(tmp / ".observer.lock")
        env["RILL_XRAY_AGENT_PYTHON"] = str(ROOT / "python")
        env["RILL_XRAY_AGENT_TOPOLOGY"] = str(topology)
        env["RILL_XRAY_AGENT_GENERATION"] = str(tmp / "generation")
        if with_generation is not None:
            (tmp / "generation").write_text(f"{with_generation}\n")
        proc = subprocess.run(
            ["python3", str(SCRIPTS / "rill_xray_agent_observe.py")],
            env=env, capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(status.read_text()), json.loads(topology.read_text())

    def test_nested_file_symlink_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="rxa-nest-") as tmp:
            tmp = Path(tmp)
            root = tmp / "root"
            nginx = root / "conf/nginx"
            nginx.mkdir(parents=True)
            (nginx / "real.conf").write_text("server {}")
            (nginx / "leak.conf").symlink_to("/etc/shadow")
            data, _ = self._observe(tmp, root)
            self.assertEqual(data["nginxConfig"], {"present": True, "safe": False})

    def test_nested_directory_symlink_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="rxa-nest-") as tmp:
            tmp = Path(tmp)
            root = tmp / "root"
            nginx = root / "conf/nginx"
            nginx.mkdir(parents=True)
            (nginx / "sites").mkdir()
            (nginx / "sites-enabled").symlink_to(nginx / "sites", target_is_directory=True)
            data, _ = self._observe(tmp, root)
            self.assertEqual(data["nginxConfig"], {"present": True, "safe": False})

    def test_dangling_symlink_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="rxa-nest-") as tmp:
            tmp = Path(tmp)
            root = tmp / "root"
            nginx = root / "conf/nginx"
            nginx.mkdir(parents=True)
            (nginx / "gone.conf").symlink_to("/nonexistent/missing.conf")
            data, _ = self._observe(tmp, root)
            self.assertEqual(data["nginxConfig"], {"present": True, "safe": False})

    def test_special_file_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="rxa-nest-") as tmp:
            tmp = Path(tmp)
            root = tmp / "root"
            nginx = root / "conf/nginx"
            nginx.mkdir(parents=True)
            os.mkfifo(nginx / "pipe.conf")
            data, _ = self._observe(tmp, root)
            self.assertEqual(data["nginxConfig"], {"present": True, "safe": False})

    def test_clean_tree_still_safe(self):
        with tempfile.TemporaryDirectory(prefix="rxa-nest-") as tmp:
            tmp = Path(tmp)
            root = tmp / "root"
            nginx = root / "conf/nginx"
            nginx.mkdir(parents=True)
            (nginx / "a.conf").write_text("server {}")
            (nginx / "b.conf").write_text("server {}")
            data, _ = self._observe(tmp, root)
            self.assertTrue(data["nginxConfig"]["safe"])
            self.assertEqual(data["nginxConfig"]["files"], 2)

    def test_observer_writes_secret_free_route_topology_projection(self):
        # §P0-4: the ROOT observer must emit the safe route-topology projection
        # (secret-free) carrying the root-owned generation + whole config digest.
        with tempfile.TemporaryDirectory(prefix="rxa-topo-") as tmp:
            tmp = Path(tmp)
            root = tmp / "root"
            (root / "conf/xray").mkdir(parents=True)
            (root / "conf/xray/config.json").write_text(json.dumps({
                "routing": {"rules": [
                    {"type": "field", "domain": ["user.example.com"],
                     "outboundTag": "direct"},
                    {"tag": "rill-managed-a1b2c3", "type": "field",
                     "domain": ["managed.example.com"], "outboundTag": "proxy"},
                    {"id": "a92f8c9f-0f4f-4b7c-9d3a-7f8a9b0c1d2e",
                     "privateKey": "6KzhM9OBsZ0T9c7Vhx4N2mFpR1QvJ5tW8yXbL3eDcG",
                     "shortId": "abcdef0123456789", "protocol": "reality"},
                ]},
            }))
            _, topo = self._observe(tmp, root, with_generation=7)
            self.assertEqual(topo["schemaVersion"], 2)
            # Generation comes from the ROOT-owned generation file (§P0-7).
            self.assertEqual(topo["configurationGeneration"], 7)
            self.assertNotIn("configGeneration", topo)
            self.assertEqual(topo["routingRulesCount"], 3)
            self.assertEqual(len(topo["rules"]), 3)
            self.assertEqual(len(topo["wholeConfigSha256"]), 64)
            blob = repr(topo)
            for secret in ("a92f8c9f", "privateKey", "shortId", "6KzhM9OB",
                           "abcdef0123456789", "user.example.com",
                           "managed.example.com"):
                self.assertNotIn(secret, blob, f"projection leaked {secret}")
            # Managed ownership is preserved through the projection.
            managed = [r["ruleIndex"] for r in topo["rules"] if r["isManaged"]]
            self.assertEqual(managed, [1])

    def test_observer_projection_fails_closed_on_missing_config(self):
        # Missing / unparseable Xray config -> EMPTY projection (fail closed),
        # never a partial leak, and the observer still exits 0.
        with tempfile.TemporaryDirectory(prefix="rxa-topo-") as tmp:
            tmp = Path(tmp)
            root = tmp / "root"
            (root / "conf/xray").mkdir(parents=True)
            _, topo = self._observe(tmp, root)
            self.assertEqual(topo["routingRulesCount"], 0)
            self.assertEqual(topo["rules"], [])
            self.assertEqual(topo["configurationGeneration"], 0)
            self.assertEqual(topo["wholeConfigSha256"], "")

    def test_observer_projection_fails_closed_on_unparseable_config(self):
        with tempfile.TemporaryDirectory(prefix="rxa-topo-") as tmp:
            tmp = Path(tmp)
            root = tmp / "root"
            (root / "conf/xray").mkdir(parents=True)
            (root / "conf/xray/config.json").write_text("{not-json")
            _, topo = self._observe(tmp, root)
            self.assertEqual(topo["routingRulesCount"], 0)
            self.assertEqual(topo["rules"], [])

    def test_observe_unit_grants_runtime_readonly_topology(self):
        # §P0-4: the Runtime service mounts the observer's status tree
        # (containing the route-topology projection) READ-ONLY via
        # ReadOnlyPaths, so the Runtime can never write the projection the
        # root observer produced.
        runtime = (SYSTEMD / "rill-xray-agent-runtime.service").read_text()
        ro_line = next(line for line in runtime.splitlines()
                       if line.startswith("ReadOnlyPaths="))
        self.assertIn("/var/lib/rill-xray-agent-xray", ro_line)

    def test_core_never_mentions_host_identity(self):
        token = "i" + "d" + "l" + "e" + "l" + "e" + "o"
        for path in (ROOT / "python/rill_xray_agent").glob("*.py"):
            self.assertNotIn(token, path.read_text(errors="ignore").lower(), str(path))

    def test_manager_has_transaction_helpers(self):
        manager = (SCRIPTS / "rill_xray_agent_manager.sh").read_text()
        for marker in (
            "rxa_observe_fresh",
            "rxa_verify_runtime_mode",
            'rxa_runtime mode "$old"',
            "rxa_set mode \"$mode\"",
            "rxa_mode_state_matches_target()",
            "rxa_observe_valid()",
        ):
            self.assertIn(marker, manager)


if __name__ == "__main__":
    unittest.main()
