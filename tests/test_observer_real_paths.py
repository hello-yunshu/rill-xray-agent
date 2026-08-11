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
            data = self._observe(tmp, root)
            self.assertEqual(data["schemaVersion"], 1)
            self.assertTrue(data["xrayConfig"]["present"])
            self.assertIn("services", data)

    def _observe(self, tmp, root):
        status = tmp / "status.json"
        history = tmp / "history"
        env = dict(os.environ)
        env["RILL_XRAY_HOST_ROOT"] = str(root)
        env["RILL_XRAY_AGENT_OUTPUT"] = str(status)
        env["RILL_XRAY_AGENT_HISTORY"] = str(history)
        env["RILL_XRAY_AGENT_LOCK"] = str(tmp / ".observer.lock")
        env["RILL_XRAY_AGENT_PYTHON"] = str(ROOT / "python")
        proc = subprocess.run(
            ["python3", str(SCRIPTS / "rill_xray_agent_observe.py")],
            env=env, capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(status.read_text())

    def test_nested_file_symlink_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="rxa-nest-") as tmp:
            tmp = Path(tmp)
            root = tmp / "root"
            nginx = root / "conf/nginx"
            nginx.mkdir(parents=True)
            (nginx / "real.conf").write_text("server {}")
            (nginx / "leak.conf").symlink_to("/etc/shadow")
            data = self._observe(tmp, root)
            self.assertEqual(data["nginxConfig"], {"present": True, "safe": False})

    def test_nested_directory_symlink_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="rxa-nest-") as tmp:
            tmp = Path(tmp)
            root = tmp / "root"
            nginx = root / "conf/nginx"
            nginx.mkdir(parents=True)
            (nginx / "sites").mkdir()
            (nginx / "sites-enabled").symlink_to(nginx / "sites", target_is_directory=True)
            data = self._observe(tmp, root)
            self.assertEqual(data["nginxConfig"], {"present": True, "safe": False})

    def test_dangling_symlink_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="rxa-nest-") as tmp:
            tmp = Path(tmp)
            root = tmp / "root"
            nginx = root / "conf/nginx"
            nginx.mkdir(parents=True)
            (nginx / "gone.conf").symlink_to("/nonexistent/missing.conf")
            data = self._observe(tmp, root)
            self.assertEqual(data["nginxConfig"], {"present": True, "safe": False})

    def test_special_file_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="rxa-nest-") as tmp:
            tmp = Path(tmp)
            root = tmp / "root"
            nginx = root / "conf/nginx"
            nginx.mkdir(parents=True)
            os.mkfifo(nginx / "pipe.conf")
            data = self._observe(tmp, root)
            self.assertEqual(data["nginxConfig"], {"present": True, "safe": False})

    def test_clean_tree_still_safe(self):
        with tempfile.TemporaryDirectory(prefix="rxa-nest-") as tmp:
            tmp = Path(tmp)
            root = tmp / "root"
            nginx = root / "conf/nginx"
            nginx.mkdir(parents=True)
            (nginx / "a.conf").write_text("server {}")
            (nginx / "b.conf").write_text("server {}")
            data = self._observe(tmp, root)
            self.assertTrue(data["nginxConfig"]["safe"])
            self.assertEqual(data["nginxConfig"]["files"], 2)

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
