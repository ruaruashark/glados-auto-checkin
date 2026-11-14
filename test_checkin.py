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

    @patch("checkin.time.sleep")
    @patch("checkin.time.monotonic", side_effect=[100.0, 102.7])
    @patch("checkin.requests.Session")
    def test_turnstile_configuration_does_not_stop_before_response(self, session_factory, _clock, _sleep):
        session_factory.return_value = self.session
        self.session.get.return_value.json.return_value["turnstile"] = {"sitekey": "fake"}

        result = checkin.api_checkin("fake-cookie", "glados.one")

        self.assertEqual(result["code"], 0)
        self.session.post.assert_called_once()
        self.assertEqual(self.session.post.call_args.kwargs["json"]["tsState"], "error")
        self.assertNotIn("turnstile", self.session.post.call_args.kwargs["json"])

    @patch("checkin.api_checkin")
    def test_server_rejection_can_fall_back_to_another_domain(self, api_checkin):
        api_checkin.side_effect = [
            {"code": 4, "reason": "turnstile", "message": "Cloudflare verification failed"},
            {"code": 0, "points": 7, "message": "Checkin!"},
        ]
        with patch("checkin.api_status", return_value={"data": {"leftDays": 632}}):
            ok, summary = checkin.checkin_one(1, "fake-cookie", ["glados.one", "glados.cloud"])

        self.assertTrue(ok)
        self.assertIn("服务端要求人机验证", summary)
        self.assertIn("签到成功", summary)
        self.assertEqual(api_checkin.call_count, 2)

    @patch("checkin.api_checkin")
    @patch("checkin.api_status", return_value={"data": {"leftDays": 632}})
    def test_all_server_rejections_report_failure(self, _status, api_checkin):
        api_checkin.return_value = {
            "code": 4, "reason": "turnstile", "message": "Cloudflare verification failed"
        }
        ok, summary = checkin.checkin_one(1, "fake-cookie", ["glados.one", "glados.cloud"])

        self.assertFalse(ok)
        self.assertEqual(summary.count("服务端要求人机验证"), 2)
        self.assertEqual(api_checkin.call_count, 2)


if __name__ == "__main__":
    unittest.main()
