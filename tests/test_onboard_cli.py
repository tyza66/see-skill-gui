import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "see" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import onboard


class OnboardCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="see-cli-")
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.codex_home = root / "codex"
        self.bin_home = root / "bin"
        self.config_dir = root / "config"
        self.profile = root / ".profile"
        self.env = patch.dict(
            os.environ,
            {
                "CODEX_HOME": str(self.codex_home),
                "XDG_BIN_HOME": str(self.bin_home),
                "XDG_CONFIG_HOME": str(self.config_dir),
                "SEE_LOG_FILE": str(root / "usage.log"),
                "PATH": "/usr/bin:/bin",
            },
            clear=False,
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.shell_patch = patch.object(
            onboard,
            "_shell_rc_paths",
            return_value=[self.profile],
        )
        self.shell_patch.start()
        self.addCleanup(self.shell_patch.stop)

    def test_install_and_uninstall_skill(self) -> None:
        onboard.install_skill()
        dest = onboard.skill_dest_dir()
        self.assertTrue((dest / "SKILL.md").is_file())
        self.assertTrue((dest / ".see-gui-version").is_file())
        status = onboard.skill_install_status()
        self.assertTrue(status["installed"])
        self.assertEqual(status["path"], str(dest))

        onboard.uninstall_skill()
        self.assertFalse(dest.exists())
        self.assertFalse(onboard.skill_install_status()["installed"])

    def test_install_and_uninstall_cli_updates_rc(self) -> None:
        onboard.install_skill()
        launcher, messages = onboard.install_cli()
        self.assertTrue(launcher.is_file())
        self.assertTrue(launcher.stat().st_mode & 0o111)
        self.assertTrue(messages)
        rc_text = self.profile.read_text(encoding="utf-8")
        self.assertIn(onboard._rc_export_line(), rc_text)
        self.assertTrue(onboard.cli_install_status()["installed"])

        onboard.uninstall_cli()
        self.assertFalse(launcher.exists())
        self.assertNotIn(onboard._rc_export_line(), self.profile.read_text(encoding="utf-8"))

    def test_uninstall_integration_cleans_skill_cli_agents_and_config(self) -> None:
        onboard.install_skill()
        onboard.install_cli()
        agents = Path(self.tmp.name) / "AGENTS.md"
        onboard.install_agents_rule(agents)
        config = onboard.config_file_path()
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text("SEE_PROVIDER=local\n", encoding="utf-8")

        summary = onboard.uninstall_integration(
            skill=True,
            cli=True,
            agents=True,
            agents_path=agents,
            config=True,
            credentials=False,
            logs=True,
        )
        self.assertTrue(summary["skill"])
        self.assertTrue(summary["cli"])
        self.assertTrue(summary["agents_rule"])
        self.assertTrue(summary["config"])
        self.assertTrue(summary["logs_cleared"])
        self.assertFalse(onboard.skill_dest_dir().exists())
        self.assertFalse(onboard.cli_launcher_path().exists())
        self.assertFalse(agents.exists())
        self.assertFalse(config.exists())


if __name__ == "__main__":
    unittest.main()
