import io
import json
import os
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from core import updater


class TestNo2FA(unittest.TestCase):
    def test_auth_manager_removed(self):
        auth_path = os.path.join(updater.BASE_DIR, "core", "auth_manager.py")
        self.assertFalse(os.path.exists(auth_path), "core/auth_manager.py should be deleted")

    def test_ui_api_key_no_auth_import(self):
        ui_path = os.path.join(updater.BASE_DIR, "ui_modules", "ui_api_key.py")
        with open(ui_path, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("auth_manager", src)
        self.assertNotIn("_render_login", src)
        self.assertNotIn("_render_first_run", src)


class TestUpdater(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_token_roundtrip(self):
        self.assertEqual(updater.load_github_token(base_dir=self.root), "")
        updater.save_github_token("ghp_test123", base_dir=self.root)
        self.assertEqual(updater.load_github_token(base_dir=self.root), "ghp_test123")
        updater.clear_github_token(base_dir=self.root)
        self.assertEqual(updater.load_github_token(base_dir=self.root), "")

    def test_smart_merge_dict_json_preserves_old_adds_new(self):
        local_p = os.path.join(self.root, "criteria_master.json")
        inc_p = os.path.join(self.root, "incoming_criteria.json")
        with open(local_p, "w", encoding="utf-8") as f:
            json.dump({"existing": {"val": "local_custom"}, "only_local": {"val": 1}}, f)
        with open(inc_p, "w", encoding="utf-8") as f:
            json.dump({"existing": {"val": "github_default"}, "new_item": {"val": 2}}, f)

        changed, added = updater.smart_merge_dict_json(local_p, inc_p)
        self.assertTrue(changed)
        self.assertEqual(added, 1)

        with open(local_p, "r", encoding="utf-8") as f:
            merged = json.load(f)
        self.assertEqual(merged["existing"]["val"], "local_custom")
        self.assertEqual(merged["only_local"]["val"], 1)
        self.assertEqual(merged["new_item"]["val"], 2)

    def test_smart_merge_model_config(self):
        local_p = os.path.join(self.root, "model_config.json")
        inc_p = os.path.join(self.root, "incoming_models.json")
        with open(local_p, "w", encoding="utf-8") as f:
            json.dump({"Google API": ["gemini-2.5-flash", "custom-model"]}, f)
        with open(inc_p, "w", encoding="utf-8") as f:
            json.dump({"Google API": ["gemini-2.5-flash", "gemini-3.7-flash"], "OpenAI": ["gpt-4o"]}, f)

        changed, added = updater.smart_merge_model_config(local_p, inc_p)
        self.assertTrue(changed)
        self.assertEqual(added, 2)

        with open(local_p, "r", encoding="utf-8") as f:
            merged = json.load(f)
        self.assertEqual(merged["Google API"], ["gemini-2.5-flash", "custom-model", "gemini-3.7-flash"])
        self.assertEqual(merged["OpenAI"], ["gpt-4o"])

    def test_apply_update_from_archive_protects_secrets_and_merges_libs(self):
        # Seed local machine files
        with open(os.path.join(self.root, "api_key.json"), "w", encoding="utf-8") as f:
            json.dump({"keys": [{"id": "local-secret"}]}, f)
        with open(os.path.join(self.root, "drive_token.json"), "w", encoding="utf-8") as f:
            json.dump({"token": "local-drive-token"}, f)
        with open(os.path.join(self.root, "criteria_master.json"), "w", encoding="utf-8") as f:
            json.dump({"old_key": {"name": "Local"}}, f)
        with open(os.path.join(self.root, "main.py"), "w", encoding="utf-8") as f:
            f.write("# old main")

        # Build mock GitHub zipball
        buf = io.BytesIO()
        prefix = "hoangdanh293-QC-AI-abc1234"
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"{prefix}/main.py", "# new main v2")
            zf.writestr(f"{prefix}/core/new_mod.py", "X = 1\n")
            zf.writestr(f"{prefix}/api_key.json", '{"keys": []}')
            zf.writestr(f"{prefix}/drive_token.json", '{"token": "should-not-overwrite"}')
            zf.writestr(f"{prefix}/criteria_master.json", '{"old_key": {"name": "GH"}, "new_key": {"name": "New"}}')
            zf.writestr(f"{prefix}/.git/HEAD", "ref: refs/heads/main")

        res = updater.apply_update_from_archive_bytes(
            zip_bytes=buf.getvalue(),
            remote_info={
                "remote_sha": "abc1234567890",
                "commit_message": "Test release",
                "commit_date": "2026-11-16T09:00:00Z",
            },
            base_dir=self.root,
            install_deps=False,
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["updated_files"], 2)  # main.py + core/new_mod.py
        self.assertEqual(res["merged_new_keys"], 1)
        self.assertEqual(res["skipped_protected"], 2)  # api_key.json + drive_token.json

        # Verify protected files untouched
        with open(os.path.join(self.root, "api_key.json"), "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["keys"][0]["id"], "local-secret")
        with open(os.path.join(self.root, "drive_token.json"), "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["token"], "local-drive-token")

        # Verify source updated & .git ignored
        with open(os.path.join(self.root, "main.py"), "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "# new main v2")
        self.assertTrue(os.path.exists(os.path.join(self.root, "core", "new_mod.py")))
        self.assertFalse(os.path.exists(os.path.join(self.root, ".git", "HEAD")))

        # Verify version file saved
        ver = updater.get_local_version(base_dir=self.root)
        self.assertEqual(ver["commit_sha"], "abc1234567890")

    def test_check_for_updates_private_repo_without_token(self):
        class MockResp:
            status_code = 404

        with patch("core.updater.requests.get", return_value=MockResp()):
            info = updater.check_for_updates(base_dir=self.root)
        self.assertFalse(info["ok"])
        self.assertTrue(info["needs_token"])


if __name__ == "__main__":
    unittest.main()
