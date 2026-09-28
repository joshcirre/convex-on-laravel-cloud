"""Exercise the real startup script with fake child processes, without a database."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


class StartupTest(unittest.TestCase):
    def run_start(self, overrides=None, failure=None, child_exit=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copy(ROOT / "start.sh", root)
            (root / "bin").mkdir()
            backend = root / "bin/convex-local-backend"
            backend.write_text("""#!/usr/bin/env python3
import json, os, sys, time
from pathlib import Path
Path(os.environ['CAPTURE']).write_text(json.dumps({
    'args': sys.argv[1:],
    's3': {k: v for k, v in os.environ.items() if k.startswith('S3_')},
}))
if 'CHILD_EXIT' in os.environ:
    sys.exit(int(os.environ['CHILD_EXIT']))
while True:
    time.sleep(1)
""")
            backend.chmod(0o755)
            (root / "proxy.mjs").write_text("setInterval(() => {}, 1000);\n")
            env = {
                "PATH": os.environ["PATH"],
                "INSTANCE_NAME": "test-convex",
                "INSTANCE_SECRET": "0" * 64,
                "CONVEX_CLOUD_ORIGIN": "https://convex.example.com/",
                "DATABASE_URL": "mysql://test:fake@localhost:3306/test_convex",
                "AWS_BUCKET": "test-bucket",
                "AWS_ENDPOINT": "https://storage.example.com",
                "DATA_DIR": str(root / "data"),
                "CAPTURE": str(root / "capture.json"),
            }
            for key, value in (overrides or {}).items():
                if value is None:
                    env.pop(key, None)
                else:
                    env[key] = value
            if child_exit is not None:
                env["CHILD_EXIT"] = str(child_exit)
            process = subprocess.Popen(
                ["bash", str(root / "start.sh")], env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, start_new_session=True,
            )
            try:
                if failure is not None or child_exit is not None:
                    stdout, stderr = process.communicate(timeout=8)
                    self.assertNotEqual(process.returncode, 0, stdout + stderr)
                    if failure:
                        self.assertIn(failure, stderr)
                        self.assertFalse((root / "capture.json").exists())
                    else:
                        self.assertEqual(process.returncode, child_exit or 1)
                    return
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    try:
                        return json.loads((root / "capture.json").read_text())
                    except (FileNotFoundError, json.JSONDecodeError):
                        if process.poll() is not None:
                            self.fail("Startup exited before launching the backend")
                        time.sleep(0.02)
                self.fail("Backend was not launched")
            finally:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                process.communicate(timeout=5)

    def test_mysql_url_and_storage_mapping(self):
        result = self.run_start()
        args = result["args"]
        self.assertEqual(args[args.index("--db") + 1], "mysql-v5")
        self.assertEqual(args[-1], "mysql://test:fake@localhost:3306")
        self.assertEqual(args[args.index("--convex-site") + 1], "https://convex.example.com/http")
        self.assertEqual(args[args.index("--interface") + 1], "127.0.0.1")
        for name in ["EXPORTS", "SNAPSHOT_IMPORTS", "MODULES", "FILES", "SEARCH"]:
            self.assertEqual(result["s3"][f"S3_STORAGE_{name}_BUCKET"], "test-bucket")
        self.assertEqual(result["s3"]["S3_ENDPOINT_URL"], "https://storage.example.com")

    def test_cloud_mysql_fields_encode_credentials(self):
        args = self.run_start({
            "DATABASE_URL": None, "DB_CONNECTION": "mysql", "DB_HOST": "localhost",
            "DB_PORT": "3306", "DB_DATABASE": "test_convex",
            "DB_USERNAME": "test@user", "DB_PASSWORD": "fake:/@?",
        })["args"]
        self.assertEqual(args[-1], "mysql://test%40user:fake%3A%2F%40%3F@localhost:3306")
        self.assertEqual(args[args.index("--db") + 1], "mysql-v5")

    def test_tls_requires_explicit_opt_out(self):
        for value in [None, "", "0", "false", "1", "true"]:
            with self.subTest(value=value):
                args = self.run_start({"DO_NOT_REQUIRE_SSL": value})["args"]
                self.assertEqual("--do-not-require-ssl" in args, value in ["1", "true"])

    def test_boolean_validation(self):
        self.run_start({"DO_NOT_REQUIRE_SSL": "typo"}, failure="DO_NOT_REQUIRE_SSL must be")
        args = self.run_start({"DISABLE_BEACON": "false", "REDACT_LOGS_TO_CLIENT": "true"})["args"]
        self.assertNotIn("--disable-beacon", args)
        self.assertIn("--redact-logs-to-client", args)

    def test_refuses_missing_persistence(self):
        self.run_start({"DATABASE_URL": None}, failure="attach MySQL or Postgres")
        self.run_start({"AWS_BUCKET": None}, failure="attach a private bucket")

    def test_refuses_wrong_database(self):
        self.run_start({"DATABASE_URL": "mysql://test:fake@localhost/production"}, failure="expects 'test_convex'")

    def test_unexpected_clean_child_exit_fails_service(self):
        self.run_start(child_exit=0)

    def test_preserves_child_failure_status(self):
        self.run_start(child_exit=7)


if __name__ == "__main__":
    unittest.main()
