import unittest

from flamenco_bot.config import parse_admins, parse_database_pool_sizes


class ConfigTests(unittest.TestCase):
    def test_admin_ids_are_deduplicated_and_empty_values_are_ignored(self):
        self.assertEqual(parse_admins("123, 456,123,, "), [123, 456])

    def test_invalid_admin_id_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "числовые Telegram ID"):
            parse_admins("123,not-an-id")

    def test_non_positive_admin_id_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "положительными"):
            parse_admins("0")

    def test_database_pool_sizes_accept_valid_bounds(self):
        self.assertEqual(parse_database_pool_sizes("2", "8"), (2, 8))

    def test_database_pool_sizes_reject_invalid_values(self):
        for minimum, maximum in (("x", "8"), ("0", "2"), ("3", "2")):
            with self.subTest(minimum=minimum, maximum=maximum):
                with self.assertRaises(ValueError):
                    parse_database_pool_sizes(minimum, maximum)
