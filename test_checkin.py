"""签到协议的离线回归测试；不会访问 GLaDOS。"""

import hashlib
import unittest
from unittest.mock import MagicMock, patch

import checkin


class CheckinProtocolTests(unittest.TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.session.__enter__.return_value = self.session
        self.session.get.return_value.json.return_value = {
            "code": 0,
            "nonce": "test-nonce",
            "ttl": 300000,
        }
        self.session.post.return_value.json.return_value = {
            "code": 0,
            "points": 7,
        }

    @patch("checkin.time.sleep")
    @patch("checkin.time.monotonic", side_effect=[100.0, 102.7])
    @patch("checkin.requests.Session")
    def test_challenge_proof_precedes_checkin(self, session_factory, _clock, _sleep):
        session_factory.return_value = self.session

        result = checkin.api_checkin("fake-cookie", "glados.one")

        self.assertEqual(result["points"], 7)
        self.session.get.assert_called_once()
        self.assertEqual(
            self.session.get.call_args.args[0],
            "https://glados.one/api/user/checkin/challenge",
        )
        self.session.post.assert_called_once()
        self.assertEqual(
            self.session.post.call_args.kwargs["json"],
            {
                "token": "glados.one",
                "nonce": "test-nonce",
                "proof": hashlib.sha256(b"test-nonce.glados-observe-v1").hexdigest(),
                "tsState": "off",
            },
        )

    @patch("checkin.requests.Session")
    def test_missing_challenge_does_not_submit_old_request(self, session_factory):
        session_factory.return_value = self.session
        self.session.get.return_value.json.return_value = {"code": 4}

        with self.assertRaisesRegex(RuntimeError, "未提供有效签到验证"):
            checkin.api_checkin("fake-cookie", "glados.one")

        self.session.post.assert_not_called()

    @patch("checkin.requests.Session")
    def test_turnstile_requires_manual_checkin(self, session_factory):
        session_factory.return_value = self.session
        self.session.get.return_value.json.return_value["turnstile"] = {"sitekey": "fake"}

        with self.assertRaises(checkin.ManualVerificationRequired):
            checkin.api_checkin("fake-cookie", "glados.one")

        self.session.post.assert_not_called()

    @patch("checkin.api_checkin", side_effect=checkin.ManualVerificationRequired("请手动签到"))
    def test_turnstile_does_not_fall_back_to_another_domain(self, api_checkin):
        ok, summary = checkin.checkin_one(1, "fake-cookie", ["glados.one", "glados.cloud"])

        self.assertFalse(ok)
        self.assertIn("请手动签到", summary)
        api_checkin.assert_called_once_with("fake-cookie", "glados.one")


if __name__ == "__main__":
    unittest.main()
