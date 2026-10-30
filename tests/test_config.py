import unittest

from eudic2maimemo.config import Config
from eudic2maimemo.http import SyncError


class FromEnvTest(unittest.TestCase):
    def test_prefixes_nis_when_missing(self):
        config = Config.from_env({"EUDIC_API_KEY": "abc123"})
        self.assertEqual(config.eudic_api_key, "NIS abc123")

    def test_keeps_existing_nis_prefix(self):
        config = Config.from_env({"EUDIC_API_KEY": "NIS abc123"})
        self.assertEqual(config.eudic_api_key, "NIS abc123")

    def test_defaults_to_first_wordbook(self):
        config = Config.from_env({})
        self.assertEqual(config.eudic_category_ids, ["0"])

    def test_parses_multiple_wordbooks(self):
        config = Config.from_env({"EUDIC_CATEGORY_ID": "0, 133716565810649835 ,9"})
        self.assertEqual(config.eudic_category_ids, ["0", "133716565810649835", "9"])

    def test_ignore_patterns_split_by_semicolon_and_newline(self):
        config = Config.from_env({"IGNORE_PATTERNS": r"^\S*\s\S*$;[一-龥]" + "\n^#.*"})
        self.assertEqual(config.ignore_patterns, [r"^\S*\s\S*$", "[一-龥]", "^#.*"])

    def test_invalid_regex_fails_fast(self):
        with self.assertRaises(SyncError):
            Config.from_env({"IGNORE_PATTERNS": "[unclosed"})

    def test_min_star_parsed(self):
        self.assertEqual(Config.from_env({"MIN_STAR": "4"}).min_star, 4)
        self.assertEqual(Config.from_env({"MIN_STAR": " 2 "}).min_star, 2)
        self.assertEqual(Config.from_env({}).min_star, 0)

    def test_min_star_invalid_falls_back_to_zero(self):
        self.assertEqual(Config.from_env({"MIN_STAR": "abc"}).min_star, 0)
        self.assertEqual(Config.from_env({"MIN_STAR": "-3"}).min_star, 0)

    def test_routes_parsed(self):
        config = Config.from_env(
            {"EUDIC_ROUTES": "0=np-aaa;133716565810649835=np-bbb"}
        )
        self.assertEqual(
            config.routes,
            {"0": "np-aaa", "133716565810649835": "np-bbb"},
        )

    def test_routes_split_by_newline(self):
        config = Config.from_env({"EUDIC_ROUTES": "0=np-aaa\n1=np-bbb"})
        self.assertEqual(config.routes, {"0": "np-aaa", "1": "np-bbb"})

    def test_route_without_np_prefix_is_rejected(self):
        with self.assertRaises(SyncError):
            Config.from_env({"EUDIC_ROUTES": "0=1234567"})

    def test_routes_ignore_malformed_entries(self):
        config = Config.from_env({"EUDIC_ROUTES": "0=np-aaa;;坏的;=np-x"})
        self.assertEqual(config.routes, {"0": "np-aaa"})

    def test_accepts_legacy_names(self):
        config = Config.from_env(
            {
                "EUDIC_AUTHORIZATION": "NIS x",
                "MAIMEMO_TOKEN": "tok",
                "MAIMEMO_NOTEPAD_ID": "np-1",
            }
        )
        self.assertEqual(config.maimemo_token, "tok")
        self.assertEqual(config.maimemo_notepad_id, "np-1")


class RequireMaimemoTest(unittest.TestCase):
    def test_raises_when_missing(self):
        config = Config(eudic_api_key="NIS x")
        with self.assertRaises(SyncError) as ctx:
            config.require_maimemo()
        self.assertIn("MOMO_API_KEY", str(ctx.exception))

    def test_passes_when_present(self):
        Config(
            eudic_api_key="NIS x", maimemo_token="t", maimemo_notepad_id="np"
        ).require_maimemo()


class IgnoreTest(unittest.TestCase):
    def test_matches_case_insensitively(self):
        config = Config(eudic_api_key="NIS x", ignore_patterns=[r"^CNC$"])
        self.assertTrue(config.ignored("cnc"))
        self.assertFalse(config.ignored("cnc machine"))

    def test_no_patterns_means_nothing_ignored(self):
        self.assertFalse(Config(eudic_api_key="NIS x").ignored("anything"))


if __name__ == "__main__":
    unittest.main()
