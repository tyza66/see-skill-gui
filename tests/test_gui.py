import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "see" / "scripts"))

import gui


class SavePlanTests(unittest.TestCase):
    def test_custom_writes_user_endpoint_model_and_credential_reference(self) -> None:
        values: dict[str, str] = {}
        plan = gui.build_save_plan(
            "custom",
            "sk-custom",
            "https://api.example.com/v1",
            "vision-pro",
            "",
            True,
            values,
        )

        self.assertEqual(plan.provider, "custom")
        self.assertEqual(plan.api_key, "sk-custom")
        self.assertTrue(plan.save_secret)
        self.assertNotIn("CUSTOM_API_KEY", plan.values)
        self.assertEqual(
            plan.values["CUSTOM_BASE_URL"],
            "https://api.example.com/v1",
        )
        self.assertEqual(plan.values["CUSTOM_MODEL"], "vision-pro")
        self.assertEqual(plan.values["CUSTOM_VIDEO_MODEL"], "vision-pro")
        self.assertEqual(plan.values["SEE_CREDENTIAL_REF_CUSTOM"], "see/custom/default")

    def test_custom_keeps_existing_reference_when_key_is_blank(self) -> None:
        values = {"SEE_CREDENTIAL_REF_CUSTOM": "see/custom/default"}
        plan = gui.build_save_plan(
            "custom",
            "",
            "https://api.example.com/v1",
            "vision-pro",
            "video-pro",
            False,
            values,
        )

        self.assertFalse(plan.save_secret)
        self.assertEqual(plan.values["SEE_CREDENTIAL_REF_CUSTOM"], "see/custom/default")
        self.assertEqual(plan.values["CUSTOM_VIDEO_MODEL"], "video-pro")

    def test_longcat_is_no_key_and_keeps_public_defaults(self) -> None:
        values: dict[str, str] = {}
        plan = gui.build_save_plan(
            "longcat",
            "",
            "",
            "",
            "",
            True,
            values,
        )

        self.assertFalse(plan.save_secret)
        self.assertFalse(plan.verify.requires_key)
        self.assertEqual(plan.values["LONGCAT_BASE_URL"], "http://127.0.0.1:15721/v1")
        self.assertEqual(plan.values["LONGCAT_MODEL"], "deepseek-v4-flash-vision-exp")
        self.assertNotIn("SEE_CREDENTIAL_REF_LONGCAT", plan.values)

    def test_local_requires_no_key_and_only_touches_default_flag(self) -> None:
        values = {"SEE_PROVIDER": "zenmux"}
        plan = gui.build_save_plan("local", "", "", "", "", True, values)

        self.assertIsNone(plan.verify)
        self.assertFalse(plan.save_secret)
        self.assertEqual(plan.values["SEE_PROVIDER"], "local")

    def test_custom_requires_base_and_model(self) -> None:
        with self.assertRaisesRegex(ValueError, "API 地址"):
            gui.build_save_plan("custom", "key", "", "model", "", False, {})
        with self.assertRaisesRegex(ValueError, "图片模型"):
            gui.build_save_plan("custom", "key", "https://api.example.com/v1", "", "", False, {})


if __name__ == "__main__":
    unittest.main()
