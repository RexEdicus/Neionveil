import unittest

from master_run import parse_args


class TestCliContract(unittest.TestCase):
    def test_variations_min(self):
        with self.assertRaises(SystemExit):
            parse_args(["--variations", "0"])

    def test_prompt_requires_model(self):
        with self.assertRaises(SystemExit):
            parse_args(["--llm-prompt", "rainy cyberpunk"])

    def test_model_requires_prompt(self):
        with self.assertRaises(SystemExit):
            parse_args(["--llm-model", "llama3:8b"])

    def test_valid_contract(self):
        args = parse_args([
            "--llm-prompt", "rainy cyberpunk",
            "--llm-model", "llama3:8b",
            "--variations", "3",
            "--run-id", "run-abc",
            "--dry-run",
        ])
        self.assertEqual(args.variations, 3)
        self.assertEqual(args.run_id, "run-abc")
        self.assertTrue(args.dry_run)


if __name__ == "__main__":
    unittest.main()
