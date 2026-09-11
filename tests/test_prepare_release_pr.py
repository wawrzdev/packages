from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.error

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import prepare_release_pr as prepare
from publish_release import PublishError, release_record
from test_publish_release import release_fixture


class ReconcileTests(unittest.TestCase):
    def test_empty_repositories_are_bootstrap_not_a_failure(self):
        gh = Mock()
        missing = urllib.error.HTTPError("url", 404, "Not Found", {}, None)
        forbidden = urllib.error.HTTPError("url", 403, "Forbidden", {}, None)
        try:
            gh.json.side_effect = missing
            self.assertIsNone(prepare.latest_payload(gh, "wawrzdev/secret"))
            gh.json.side_effect = forbidden
            with self.assertRaises(urllib.error.HTTPError):
                prepare.latest_payload(gh, "wawrzdev/secret")
        finally:
            missing.close()
            forbidden.close()

    def test_latest_payload_uses_api_asset_identity_and_resolved_tag(self):
        gh = Mock()
        gh.json.return_value = {"id": 23, "tag_name": "v1.2.3", "immutable": True,
                                "assets": [{"id": 42, "name": "checksums.txt"}]}
        with patch.object(prepare, "peel_tag", return_value=("a" * 40, "b" * 40)):
            payload = prepare.latest_payload(gh, "wawrzdev/secret")
        self.assertEqual(payload["source_commit"], "a" * 40)
        self.assertEqual(payload["checksums_asset_id"], "42")
        gh.json.return_value["immutable"] = False
        with self.assertRaises(PublishError):
            prepare.latest_payload(gh, "wawrzdev/secret")

    def test_one_reconciliation_includes_all_changed_sources_and_preserves_input(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            releases = {}
            for app in ("secret", "snip", "wtf"):
                (root / app).mkdir()
                releases[app] = release_fixture(root / app, app)
            original = {"schema": 1, "apps": {}}
            with patch.object(prepare, "latest_payload", return_value={"tag_name": "v1.2.3"}), \
                 patch.object(prepare, "verify_release", side_effect=lambda gh, app, *args: releases[app]):
                manifest, newest = prepare.reconcile(Mock(), original, root / "stage")
            self.assertEqual(set(manifest["apps"]), set(releases))
            self.assertEqual(set(newest), set(releases))
            self.assertEqual(original, {"schema": 1, "apps": {}})

    def test_replay_is_noop_and_downgrade_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            release = release_fixture(root)
            original = {"schema": 1, "apps": {"secret": [release_record(release)]}}
            def payload(gh, repo):
                return {"tag_name": "v1.2.3"} if repo.endswith("/secret") else None
            with patch.object(prepare, "latest_payload", side_effect=payload), \
                 patch.object(prepare, "verify_release", return_value=release):
                manifest, newest = prepare.reconcile(Mock(), original, root / "stage")
            self.assertEqual(manifest, original)
            self.assertEqual(newest, {})
            with patch.object(prepare, "latest_payload", return_value={"tag_name": "v1.0.0"}):
                with self.assertRaises(PublishError):
                    prepare.reconcile(Mock(), original, root / "stage")


if __name__ == "__main__":
    unittest.main()
