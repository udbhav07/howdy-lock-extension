"""Unit tests for pg/store.py. Run: python3 -m unittest test_store"""
import json
import os
import stat
import tempfile
import unittest
from unittest import mock

from pg import store

T0 = 1_800_000_000  # a fixed epoch for the rules


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        env = {"HOME": self.tmp.name, "XDG_DATA_HOME": "", "XDG_CONFIG_HOME": "", "XDG_STATE_HOME": ""}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def make_attempt(self, t, meta=None, photos=0):
        partial = store.new_attempt(t)
        for i in range(1, photos + 1):
            open(os.path.join(partial, f"{i}.jpg"), "wb").close()
        meta = {"failures": 1, "first_failure": t, "last_failure": t, "photos": photos, "error": None, **(meta or {})}
        return store.finish_attempt(partial, meta)

    # paths and permissions

    def test_paths_follow_home_at_call_time(self):
        self.assertTrue(store.data_dir().startswith(self.tmp.name))
        with mock.patch.dict(os.environ, {"XDG_DATA_HOME": "/elsewhere"}):
            self.assertEqual(store.data_dir(), "/elsewhere/presence-guard")

    def test_private_dirs_are_0700(self):
        path = self.make_attempt(T0)
        for d in (store.data_dir(), store.attempts_dir(), path):
            self.assertEqual(stat.S_IMODE(os.stat(d).st_mode), 0o700, d)

    # settings

    def test_settings_default_has_photos_off_until_camera_chosen(self):
        s = store.settings()
        self.assertEqual(s, store.DEFAULTS)
        self.assertFalse(store.photos_enabled(s))
        self.assertTrue(store.photos_enabled({**s, "camera": "/dev/video0"}))
        self.assertFalse(store.photos_enabled({**s, "camera": "/dev/video0", "wrong_password_photos": False}))

    def test_settings_round_trip_and_corrupt_file_gives_defaults(self):
        store.save_settings({"camera": "/dev/video0", "keep_days": 7})
        self.assertEqual(store.settings()["camera"], "/dev/video0")
        self.assertEqual(store.settings()["keep_days"], 7)
        with open(store.settings_file(), "w") as f:
            f.write("{half written")
        self.assertEqual(store.settings(), store.DEFAULTS)

    def test_atomic_write_leaves_no_temp_file(self):
        store.save_settings({"keep_days": 3})
        folder = os.path.dirname(store.settings_file())
        self.assertEqual(os.listdir(folder), ["settings.json"])

    # attempts

    def test_attempt_names_are_utc_and_never_collide(self):
        a = self.make_attempt(T0)
        b = self.make_attempt(T0)
        self.assertEqual(os.path.basename(a), "2027-01-15_08-00-00")
        self.assertEqual(os.path.basename(b), "2027-01-15_08-00-00-2")
        self.assertEqual(store.name_time("2027-01-15_08-00-00-2"), T0)
        self.assertIsNone(store.name_time("unseen"))
        self.assertIsNone(store.name_time("2027-01-15_08-00-00.partial"))

    def test_attempts_lists_newest_first_and_skips_partial_and_junk(self):
        self.make_attempt(T0, photos=2)
        self.make_attempt(T0 + 60)
        store.new_attempt(T0 + 120)  # still being written
        os.mkdir(os.path.join(store.attempts_dir(), "unseen"))
        names = [a["name"] for a in store.attempts()]
        self.assertEqual(names, ["2027-01-15_08-01-00", "2027-01-15_08-00-00"])
        self.assertEqual([os.path.basename(p) for p in store.attempts()[1]["photos"]], ["1.jpg", "2.jpg"])

    def test_photos_are_numbered_in_order(self):
        path = self.make_attempt(T0)
        for n in (10, 2, 1):
            open(os.path.join(path, f"{n}.jpg"), "wb").close()
        self.assertEqual([os.path.basename(p) for p in store.photo_paths(path)], ["1.jpg", "2.jpg", "10.jpg"])

    def test_corrupt_meta_still_lists_the_attempt(self):
        path = self.make_attempt(T0)
        with open(os.path.join(path, "meta.json"), "w") as f:
            f.write("not json")
        [a] = store.attempts()
        self.assertEqual(a["meta"], {})
        self.assertEqual(a["time"], T0)

    def test_delete_attempt(self):
        path = self.make_attempt(T0, photos=1)
        store.delete_attempt(path)
        self.assertEqual(store.attempts(), [])
        store.delete_attempt(path)  # already gone: no error
        self.assertEqual(os.listdir(store.attempts_dir()), [])

    def test_delete_refuses_paths_outside_attempts(self):
        with self.assertRaises(ValueError):
            store.delete_attempt(self.tmp.name)

    # rules

    def test_burst_rules(self):
        burst = {"first": T0, "last": T0}
        self.assertFalse(store.burst_continues(None, T0))
        self.assertTrue(store.burst_continues(burst, T0 + 9))
        self.assertFalse(store.burst_continues(burst, T0 + 10))   # gap too long
        self.assertFalse(store.burst_continues(burst, T0 - 1))    # older than the burst
        long = {"first": T0, "last": T0 + 115}
        self.assertTrue(store.burst_continues(long, T0 + 119))
        self.assertFalse(store.burst_continues(long, T0 + 121))   # burst too old overall

    def test_three_quick_failures_make_one_attempt(self):
        burst, attempts_made = None, 0
        for t in (T0, T0 + 3, T0 + 8):
            if store.burst_continues(burst, t):
                burst["last"] = t
            else:
                burst, attempts_made = {"first": t, "last": t}, attempts_made + 1
        self.assertEqual(attempts_made, 1)

    def test_new_and_last_seen(self):
        self.assertIsNone(store.last_seen())
        self.assertTrue(store.is_new("2027-01-15_08-00-00", None))
        store.mark_seen("2027-01-15_08-00-00")
        seen = store.last_seen()
        self.assertEqual(seen, "2027-01-15_08-00-00")
        self.assertFalse(store.is_new("2027-01-15_08-00-00", seen))
        self.assertTrue(store.is_new("2027-01-15_08-00-00-2", seen))
        self.assertTrue(store.is_new("2027-01-15_08-00-01", seen))

    def test_probably_you(self):
        self.assertTrue(store.probably_you(T0, T0 + 20))
        self.assertFalse(store.probably_you(T0, T0 + 21))
        self.assertFalse(store.probably_you(T0 + 5, T0))  # after the unlock

    def test_prune(self):
        day = 86400
        old = self.make_attempt(T0)
        recent = self.make_attempt(T0 + 9 * day)
        store.new_attempt(T0 - day)  # partial: never pruned
        store.save_settings({"keep_days": 5})
        store.prune(now=T0 + 10 * day)
        self.assertEqual([a["path"] for a in store.attempts()], [recent])
        self.assertTrue(any(n.endswith(".partial") for n in os.listdir(store.attempts_dir())))
        store.save_settings({"keep_days": 0})
        store.prune(now=T0 + 1000 * day)
        self.assertEqual(len(store.attempts()), 1)
        self.assertFalse(os.path.exists(old))

    def test_prune_skips_an_open_burst(self):
        a = {"time": T0, "meta": {"last_failure": T0 + 100 * 86400}}
        self.assertFalse(store.prunable(a, T0 + 100 * 86400 + 30, keep_days=1))
        self.assertTrue(store.prunable(a, T0 + 100 * 86400 + 300, keep_days=1))


if __name__ == "__main__":
    unittest.main()
