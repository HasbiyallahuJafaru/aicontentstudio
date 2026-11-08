"""Plain-language errors: download failures and unplanned exceptions read as something a person can act on."""
import errno
import unittest

import httpx

from app.clipper.acquire import friendly
from app.errors import UserError, explain


class DownloadErrors(unittest.TestCase):
    def test_known_failures_get_their_own_words(self):
        cases = {
            "ERROR: [youtube] abc: HTTP Error 429: Too Many Requests": "limiting downloads",
            "ERROR: unable to download video data: HTTP Error 403: Forbidden": "blocked this download",
            "ERROR: [youtube] abc: Sign in to confirm you're not a bot": "not a bot",
            "ERROR: [youtube] abc: Sign in to confirm your age": "age-restricted",
            "ERROR: [youtube] abc: Private video. Sign in if you've been granted access": "private",
            "ERROR: [youtube] abc: Video unavailable": "isn't available",
            "ERROR: Unsupported URL: https://example.com/page": "isn't a video page",
            "ERROR: [youtube] abc: This live event will begin in 3 hours": "live stream",
            "ERROR: Unable to download webpage: <urlopen error [Errno 11001] getaddrinfo failed>": "internet connection",
        }
        for raw, words in cases.items():
            err = friendly(Exception(raw))
            self.assertIn(words, str(err), raw)
            self.assertEqual(err.detail, raw)  # the raw error stays under technical details

    def test_unknown_failure_is_calm_and_cookie_trouble_is_named(self):
        self.assertIn("Couldn't download that video", str(friendly(Exception("ERROR: something new"))))
        self.assertIn("cookies", str(friendly(Exception("could not decrypt cookie"), cookies="chrome")))


class UnplannedErrors(unittest.TestCase):
    def test_common_causes_in_plain_words(self):
        self.assertIn("internet", explain(httpx.ConnectError("boom"))[0])
        self.assertIn("disk is full", explain(OSError(errno.ENOSPC, "No space left"))[0])
        self.assertIn("Close any program", explain(PermissionError("locked"))[0])
        message, detail = explain(KeyError("x"))
        self.assertIn("Something went wrong", message)
        self.assertIn("KeyError", detail)
        self.assertEqual(explain(UserError("Say this.", "why")), ("Say this.", "why"))


if __name__ == "__main__":
    unittest.main()
