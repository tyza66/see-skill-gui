import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "see" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import parse_media


class ProviderOrderTests(unittest.TestCase):
    def test_image_and_video_defaults_stay_distinct(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                parse_media.provider_order("auto", {}),
                list(parse_media.DEFAULT_PROVIDER_ORDER),
            )
            self.assertEqual(
                parse_media.video_provider_order("auto", {}),
                list(parse_media.DEFAULT_VIDEO_PROVIDER_ORDER),
            )


class LocalBackendTests(unittest.TestCase):
    def test_macos_uses_system_vision_without_swift(self) -> None:
        image = Path("/tmp/test.png")

        def find_command(name: str) -> str | None:
            return "/usr/bin/osascript" if name == "osascript" else None

        with (
            patch.object(parse_media.sys, "platform", "darwin"),
            patch.object(parse_media.shutil, "which", side_effect=find_command),
            patch.object(
                parse_media,
                "run_json",
                return_value={"backend": "macos-vision", "items": []},
            ) as run_json,
        ):
            result = parse_media.macos_ocr(image)

        self.assertEqual(result["backend"], "macos-vision")
        command = run_json.call_args.args[0]
        self.assertEqual(command[:3], ["/usr/bin/osascript", "-l", "JavaScript"])
        self.assertEqual(Path(command[3]), parse_media.MACOS_OCR_JXA_SCRIPT)

    def test_setup_hints_are_actionable(self) -> None:
        cases = {
            "darwin": "macOS 10.15",
            "win32": "语言选项",
            "linux": "sudo apt install tesseract-ocr",
        }
        for platform, expected in cases.items():
            with self.subTest(platform=platform), patch.object(
                parse_media.sys,
                "platform",
                platform,
            ):
                self.assertIn(expected, parse_media.local_setup_hint())


class LongCatAdapterTests(unittest.TestCase):
    def test_spec_uses_local_cc_switch_proxy_without_key(self) -> None:
        spec = parse_media.PROVIDER_SPECS["longcat"]
        self.assertEqual(spec["base_url"], "http://127.0.0.1:15721/v1")
        self.assertEqual(spec["model"], "deepseek-v4-flash-vision-exp")
        self.assertEqual(spec["key_names"], ())
        self.assertFalse(spec.get("requires_key", True))

    def test_preferred_longcat_comes_first_without_changing_public_defaults(self) -> None:
        with patch.dict(os.environ, {"SEE_PROVIDER": "longcat"}, clear=True):
            order = parse_media.provider_order("auto", {})
        self.assertEqual(order[0], "longcat")
        self.assertNotIn("longcat", parse_media.DEFAULT_PROVIDER_ORDER)

    def test_resolved_provider_is_callable_without_api_key(self) -> None:
        provider = parse_media.resolve_provider("longcat", {}, allow_common=False)
        self.assertEqual(provider.api_key, "")
        self.assertFalse(provider.requires_key)
        self.assertTrue(parse_media.provider_ready(provider))

    def test_route_image_uses_no_key_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "image.png"
            image.write_bytes(b"fake")
            with patch.object(
                parse_media,
                "call_provider",
                return_value="图片内容",
            ) as call:
                result = parse_media.route_image(
                    image,
                    1,
                    {},
                    ["longcat"],
                    "",
                    Path(tmp),
                    "auto",
                    "",
                    "",
                    "",
                )
        call.assert_called_once()
        self.assertEqual(result.backend, "longcat")
        self.assertEqual(result.text, "图片内容")


class CustomProviderTests(unittest.TestCase):
    def test_spec_requires_user_configuration(self) -> None:
        spec = parse_media.PROVIDER_SPECS["custom"]
        self.assertTrue(spec.get("requires_config"))
        self.assertEqual(spec["base_env"], "CUSTOM_BASE_URL")
        self.assertEqual(spec["model_env"], "CUSTOM_MODEL")
        self.assertIn("CUSTOM_API_KEY", spec["key_names"])

    def test_ensure_custom_configured_requires_base_and_model(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "CUSTOM_BASE_URL"):
            parse_media.ensure_custom_configured(["custom"], [], {})
        with self.assertRaisesRegex(RuntimeError, "CUSTOM_MODEL"):
            parse_media.ensure_custom_configured(
                ["custom"],
                [],
                {"CUSTOM_BASE_URL": "https://api.example.com/v1"},
            )
        parse_media.ensure_custom_configured(
            ["custom"],
            [],
            {
                "CUSTOM_BASE_URL": "https://api.example.com/v1",
                "CUSTOM_MODEL": "vision-model",
            },
        )

    def test_ensure_custom_accepts_cli_overrides(self) -> None:
        parse_media.ensure_custom_configured(
            ["custom"],
            [],
            {},
            "https://cli.example.com/v1",
            "cli-model",
        )

    def test_ensure_custom_video_can_reuse_image_model(self) -> None:
        parse_media.ensure_custom_configured(
            [],
            ["custom"],
            {
                "CUSTOM_BASE_URL": "https://api.example.com/v1",
                "CUSTOM_MODEL": "vision-model",
            },
        )

    def test_resolved_custom_uses_user_values_and_video_fallback(self) -> None:
        values = {
            "CUSTOM_BASE_URL": "https://api.example.com/v1",
            "CUSTOM_MODEL": "vision-model",
            "CUSTOM_API_KEY": "custom-key",
        }
        provider = parse_media.resolve_provider("custom", values, allow_common=False)
        self.assertEqual(provider.base_url, "https://api.example.com/v1")
        self.assertEqual(provider.model, "vision-model")
        self.assertEqual(provider.api_key, "custom-key")
        self.assertTrue(parse_media.provider_ready(provider))

        video = parse_media.resolve_provider(
            "custom",
            values,
            allow_common=False,
            video=True,
        )
        self.assertEqual(video.model, "vision-model")

        with patch.dict(values, {"CUSTOM_VIDEO_MODEL": "video-vision"}):
            separate = parse_media.resolve_provider(
                "custom",
                values,
                allow_common=False,
                video=True,
            )
        self.assertEqual(separate.model, "video-vision")


if __name__ == "__main__":
    unittest.main()
