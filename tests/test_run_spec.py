import unittest

from run_spec import validate_and_normalize_spec, expand_variation_manifests


class TestRunSpec(unittest.TestCase):
    def setUp(self):
        self.config = {
            "theme": "neon_rain",
            "seed": 42,
            "audio": {"fallback_prompt": "fallback ambient"},
            "video": {
                "fps": 30,
                "duration_minutes": 120,
                "resolution_x": 2560,
                "resolution_y": 1440,
            },
            "render": {
                "engine": "BLENDER_EEVEE_NEXT",
                "samples": 64,
                "bloom": True,
                "volumetrics": True,
            },
        }

    def test_validation_defaults(self):
        spec = validate_and_normalize_spec({}, self.config)
        self.assertEqual(spec["theme"], "neon_rain")
        self.assertEqual(spec["variations"], 1)
        self.assertTrue(spec["music_prompt"])

    def test_deterministic_manifest_expansion(self):
        spec = validate_and_normalize_spec(
            {
                "run_id": "run-x",
                "theme": "neon_rain",
                "mood": "dark",
                "music_prompt": "rain",
                "seed": 101,
                "variations": 3,
            },
            self.config,
        )
        a = expand_variation_manifests(spec)
        b = expand_variation_manifests(spec)
        self.assertEqual(a, b)
        self.assertEqual(len(a), 3)
        self.assertEqual(a[0]["seed"], 101)
        self.assertEqual(a[2]["seed"], 103)


if __name__ == "__main__":
    unittest.main()
