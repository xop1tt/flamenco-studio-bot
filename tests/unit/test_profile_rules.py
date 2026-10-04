import unittest

from flamenco_bot.services import (
    MAX_USER_NAME_LENGTH,
    InvalidUserNameError,
    normalize_user_name,
)


class NormalizeUserNameTests(unittest.TestCase):
    def test_strips_and_accepts_valid_names(self):
        self.assertEqual(normalize_user_name("  Анна  "), "Анна")
        self.assertEqual(
            normalize_user_name("я" * MAX_USER_NAME_LENGTH),
            "я" * MAX_USER_NAME_LENGTH,
        )

    def test_rejects_blank_and_too_long_names(self):
        for value in ("", "   ", "\n\t", "я" * (MAX_USER_NAME_LENGTH + 1)):
            with self.subTest(value=value):
                with self.assertRaises(InvalidUserNameError):
                    normalize_user_name(value)


if __name__ == "__main__":
    unittest.main()
