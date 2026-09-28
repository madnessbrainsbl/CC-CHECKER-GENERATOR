import unittest
from http.server import HTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from server import DemoHandler


class DemoServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), DemoHandler)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_only_public_assets_are_served(self):
        for path in ("/", "/index.html", "/assets/main.css", "/assets/index.js"):
            with self.subTest(path=path), urlopen(self.base_url + path) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(
                    "default-src 'self'", response.headers["Content-Security-Policy"]
                )

        for path in ("/.env", "/.git/config", "/server.py", "/config.json"):
            with self.subTest(path=path), self.assertRaises(HTTPError) as error:
                urlopen(self.base_url + path)
            self.assertEqual(error.exception.code, 404)

    def test_payment_post_is_rejected(self):
        request = Request(self.base_url + "/check_card", data=b"sample", method="POST")
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
