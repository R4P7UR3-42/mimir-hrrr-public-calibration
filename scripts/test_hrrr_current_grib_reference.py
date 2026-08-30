import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("capture_hrrr_current_grib_reference.py")
SPEC = importlib.util.spec_from_file_location("reference", MODULE_PATH)
reference = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reference)


class CurrentHrrrReferenceTests(unittest.TestCase):
    def test_frozen_identity_and_request_budget(self):
        self.assertEqual(reference.RUN_DATE, "2026-08-29")
        self.assertEqual(reference.RUN_HOUR, 12)
        self.assertEqual(reference.STEPS, (18, 21, 24, 27, 30, 33, 36, 39, 42))
        self.assertEqual(reference.MAX_REQUESTS, 18)
        self.assertEqual(len(reference.STATIONS), 20)
        self.assertEqual(len({station[0] for station in reference.STATIONS}), 20)

    def test_index_requires_one_exact_temperature_message_and_next_boundary(self):
        compact = reference.RUN_DATE.replace("-", "")
        payload = "\n".join((
            f"1:0:d={compact}12:VIS:surface:30 hour fcst:",
            f"2:100:d={compact}12:TMP:2 m above ground:30 hour fcst:",
            f"3:250:d={compact}12:DPT:2 m above ground:30 hour fcst:",
        ))
        self.assertEqual(reference.parse_index(payload, 30), (100, 249, payload.splitlines()[1]))

    def test_index_rejects_duplicate_adjacent_and_unbounded_rows(self):
        compact = reference.RUN_DATE.replace("-", "")
        exact = f"1:100:d={compact}12:TMP:2 m above ground:30 hour fcst:"
        with self.assertRaisesRegex(ValueError, "found 2"):
            reference.parse_index(f"{exact}\n2:200:{exact.split(':', 2)[2]}\n3:300:x:x:x:x", 30)
        with self.assertRaisesRegex(ValueError, "does not bound"):
            reference.parse_index(exact, 30)

    def test_only_frozen_steps_construct_urls(self):
        object_url, index_url = reference.urls(42)
        self.assertTrue(object_url.endswith("hrrr.t12z.wrfsfcf42.grib2"))
        self.assertEqual(index_url, f"{object_url}.idx")
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            reference.urls(17)


if __name__ == "__main__":
    unittest.main()
