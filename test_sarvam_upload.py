"""Regression test: the STT upload must carry a Content-Type.

Sarvam rejects a multipart part with no Content-Type ("Invalid file type:
None"). requests only sets it when the file tuple is a 3-tuple, so this
guards against reintroducing the 2-tuple form.

Runs with SARVAM_STUB unset and a fake key; requests.post is monkeypatched,
so no network call and no credit is used.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ["SARVAM_API_KEY"] = "test-key"
os.environ.pop("SARVAM_STUB", None)

from app import sarvam  # noqa: E402


class _FakeResponse:
    status_code = 200

    def json(self):
        return {"transcript": "hello", "language_code": "en-IN"}


class TestUploadContentType(unittest.TestCase):
    def setUp(self):
        self.captured = {}

        def fake_post(url, **kwargs):
            self.captured["url"] = url
            self.captured["files"] = kwargs.get("files")
            return _FakeResponse()

        self._orig = sarvam.requests.post
        sarvam.requests.post = fake_post

    def tearDown(self):
        sarvam.requests.post = self._orig

    def _content_type_sent(self):
        value = self.captured["files"]["file"]
        self.assertEqual(len(value), 3, "file tuple must be (name, bytes, ctype)")
        return value[2]

    def test_browser_codec_parameter_is_stripped(self):
        sarvam.transcribe(b"abc", "recording.webm", "audio/webm;codecs=opus")
        self.assertEqual(self._content_type_sent(), "audio/webm")

    def test_empty_content_type_falls_back_to_webm(self):
        sarvam.transcribe(b"abc", "recording.webm", "")
        self.assertEqual(self._content_type_sent(), "audio/webm")

    def test_safari_mp4_is_preserved(self):
        sarvam.transcribe(b"abc", "recording.mp4", "audio/mp4")
        self.assertEqual(self._content_type_sent(), "audio/mp4")

    def test_non_audio_type_is_replaced(self):
        sarvam.transcribe(b"abc", "recording.webm", "application/json")
        self.assertEqual(self._content_type_sent(), "audio/webm")

    def test_content_type_is_never_empty(self):
        for ctype in ("", None, "video/webm", "application/octet-stream"):
            with self.subTest(ctype=ctype):
                sarvam.transcribe(b"abc", "recording.webm", ctype or "")
                self.assertTrue(self._content_type_sent())


if __name__ == "__main__":
    unittest.main(verbosity=2)
