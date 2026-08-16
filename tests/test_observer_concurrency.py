"""Observer WHOLE-transaction concurrency mutual exclusion (P1-1).

Guards the crash-safe exactly-once observer commit against two independent
observers (a systemd timer/path observer and a direct manager/install call)
running the (recover -> derive -> journal append -> observation replace ->
checkpoint clear) transaction concurrently. A cross-process mutex
(`ObserverLock`) serializes them, so the SAME real transition is recorded
exactly once: no duplicate sequence, no duplicate transitionId, the second
observer converges without corrupting state, journal integrity stays valid
and the checkpoint never lingers.

The competition window is forced with a threading.Barrier (not sleeps), then
verified both at the canonical transaction level (threads contending on the
same lock+journal) and end-to-end (two concurrent observe.py subprocesses).
"""
import json
import os
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from rill_xray_agent.canonical import atomic_write_json
from rill_xray_agent.event_journal import EventJournal
from rill_xray_agent.locking import ObserverLock
from rill_xray_agent.observer_transition import (CHECKPOINT_NAME, commit_transition,
                                                 recover_pending_transition)

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "integrations" / "xray_bash_onekey" / "repository_files" / "scripts"


def _obs(xray_sha="A", xray_ok=True, xray_svc=True,
         nginx_sha="A", nginx_ok=True, nginx_svc=True):
    return {
        "schemaVersion": 1,
        "capturedAtEpochSeconds": 1000,
        "xrayConfig": {"present": True, "safe": True, "sha256": xray_sha},
        "nginxConfig": {"present": True, "safe": True, "sha256": nginx_sha},
        "installConfig": {"present": False, "safe": True, "sha256": None},
        "xrayValidation": {"ok": xray_ok},
        "nginxValidation": {"ok": nginx_ok},
        "services": {"xray": {"ok": xray_svc}, "nginx": {"ok": nginx_svc}},
    }


def _read_prev(out):
    if out.is_file() and not out.is_symlink():
        try:
            return json.loads(out.read_text())
        except Exception:
            return None
    return None


class ObserverConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory(prefix="rxa-conc-")
        self.root = Path(self._td.name)
        self.history = self.root / "history"
        self.out = self.root / "status" / "xray-observation.json"
        self.out.parent.mkdir(parents=True, exist_ok=True)
        self.checkpoint = self.out.parent / CHECKPOINT_NAME
        self.lock = self.out.parent / ".observer.lock"

    def tearDown(self):
        self._td.cleanup()

    def _run_one_observer(self, current, barrier):
        """One full observer transaction under the cross-process mutex."""
        barrier.wait()
        with ObserverLock(self.lock):
            journal = EventJournal(self.history)
            journal.recover()
            recovered = recover_pending_transition(journal, self.out, self.checkpoint)
            previous = recovered if recovered is not None else _read_prev(self.out)
            commit_transition(journal, self.out, self.checkpoint, previous, current)

    def test_two_observers_same_transition_exactly_once(self):
        current = _obs()
        barrier = threading.Barrier(2)
        threads = [threading.Thread(target=self._run_one_observer, args=(current, barrier))
                   for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        self.assertFalse(any(t.is_alive() for t in threads), "observer thread hung")

        journal = EventJournal(self.history)
        events = journal.read()
        # Same real transition recorded exactly once.
        self.assertEqual(len(events), 1, events)
        self.assertEqual(events[0]["eventType"], "baseline_observed")
        tids = [e.get("transitionId") for e in events]
        self.assertEqual(len(tids), len(set(tids)), "duplicate transitionId")
        # No duplicate sequence (EventJournal.read fails closed otherwise).
        journal.verify()
        # Observation is present and correct; checkpoint cleared.
        self.assertTrue(self.out.is_file())
        self.assertEqual(json.loads(self.out.read_text())["xrayConfig"]["sha256"], "A")
        self.assertFalse(self.checkpoint.exists(), "checkpoint must not linger")

    def test_second_observer_converges_not_corrupts(self):
        # Baseline committed by a first observer, then a second contention run.
        first = _obs()
        commit_transition(EventJournal(self.history), self.out, self.checkpoint,
                          None, first)
        self.checkpoint.unlink(missing_ok=True)
        barrier = threading.Barrier(2)
        threads = [threading.Thread(target=self._run_one_observer, args=(first, barrier))
                   for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        self.assertFalse(any(t.is_alive() for t in threads), "observer thread hung")
        # No meaningful change -> no new events, state intact.
        journal = EventJournal(self.history)
        events = journal.read()
        self.assertEqual(len(events), 1, events)
        journal.verify()
        self.assertFalse(self.checkpoint.exists())

    def test_observe_py_concurrent_subprocesses_exactly_once(self):
        root = self.root / "host"
        (root / "conf/xray").mkdir(parents=True)
        (root / "conf/xray/config.json").write_text('{"inbounds":[]}')
        env = dict(os.environ)
        env["RILL_XRAY_HOST_ROOT"] = str(root)
        env["RILL_XRAY_AGENT_OUTPUT"] = str(self.out)
        env["RILL_XRAY_AGENT_HISTORY"] = str(self.history)
        env["RILL_XRAY_AGENT_LOCK"] = str(self.lock)
        env["RILL_XRAY_AGENT_TOPOLOGY"] = str(self.out.parent / "route-topology.json")
        env["RILL_XRAY_AGENT_GENERATION"] = str(self.root / "generation")
        env["RILL_XRAY_AGENT_PYTHON"] = str(ROOT / "python")
        procs = [
            subprocess.Popen(["python3", str(SCRIPTS / "rill_xray_agent_observe.py")],
                             env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for _ in range(2)
        ]
        for p in procs:
            _, err = p.communicate(timeout=30)
            self.assertEqual(p.returncode, 0, err)
        journal = EventJournal(self.history)
        events = journal.read()
        self.assertEqual(len(events), 1, events)
        self.assertEqual(events[0]["eventType"], "baseline_observed")
        journal.verify()
        self.assertFalse(self.checkpoint.exists(), "checkpoint must not linger")

    def test_observer_lock_is_root_owned_regular_file(self):
        with ObserverLock(self.lock):
            pass
        self.assertTrue(self.lock.is_file())
        self.assertFalse(self.lock.is_symlink())
        # Re-acquirable (held only for the duration of the critical section).
        with ObserverLock(self.lock):
            pass

    def test_observer_lock_rejects_symlink(self):
        target = self.root / "target"
        target.write_text("x")
        self.lock.symlink_to(target)
        with self.assertRaises(OSError):
            with ObserverLock(self.lock):
                pass


if __name__ == "__main__":
    unittest.main()