import argparse
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parents[1] / 'see/scripts'))
import onboard

class OnboardTests(unittest.TestCase):
    def args(self):
        return argparse.Namespace(status=False,install_agents=False,provider='zenmux',key_stdin=True,model='',base_url='',skip_check=True,no_default=False)
    def test_entry_writes_reference_without_secret_or_global_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'config.env'
            with patch.object(onboard,'parse_args',return_value=self.args()),patch.object(onboard,'config_file_path',return_value=path),patch.object(onboard.sys,'stdin',io.StringIO('fake-api-credential\n')),patch.object(onboard.secure_credentials,'save') as save,patch.object(onboard,'install_agents_rule') as global_write,redirect_stdout(io.StringIO()):
                self.assertEqual(onboard.main(),0)
            save.assert_called_once_with('see/zenmux/default','fake-api-credential')
            self.assertNotIn('fake-api-credential',path.read_text())
            self.assertIn('SEE_CREDENTIAL_REF_ZENMUX=see/zenmux/default',path.read_text())
            global_write.assert_not_called()
    def test_legacy_secret_blocks_before_mutating_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'config.env';path.write_text('ZENMUX_API_KEY=legacy-fake\n')
            with patch.object(onboard,'parse_args',return_value=self.args()),patch.object(onboard,'config_file_path',return_value=path),patch.object(onboard.secure_credentials,'save') as save,self.assertRaises(SystemExit):
                onboard.main()
            save.assert_not_called();self.assertIn('legacy-fake',path.read_text())

    def test_no_key_provider_saves_route_without_credential_reference(self):
        args = self.args()
        args.provider = 'longcat'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.env'
            with patch.object(onboard,'parse_args',return_value=args),patch.object(onboard,'config_file_path',return_value=path),patch.object(onboard.secure_credentials,'save') as save,redirect_stdout(io.StringIO()):
                self.assertEqual(onboard.main(),0)
            save.assert_not_called()
            text = path.read_text()
            self.assertIn('SEE_PROVIDER=longcat', text)
            self.assertNotIn('SEE_CREDENTIAL_REF_LONGCAT', text)

    def test_custom_provider_saves_address_model_and_credential_reference(self):
        args = self.args()
        args.provider = 'custom'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.env'
            with patch.object(onboard,'parse_args',return_value=args),patch.object(onboard,'config_file_path',return_value=path),patch.object(onboard.sys,'stdin',io.StringIO('custom-secret\n')),patch.object(onboard.secure_credentials,'save') as save,patch('builtins.input',side_effect=['https://api.example.com/v1','vision-model']),redirect_stdout(io.StringIO()):
                self.assertEqual(onboard.main(),0)
            save.assert_called_once_with('see/custom/default','custom-secret')
            text = path.read_text()
            self.assertNotIn('custom-secret', text)
            self.assertIn('CUSTOM_BASE_URL=https://api.example.com/v1', text)
            self.assertIn('CUSTOM_MODEL=vision-model', text)
            self.assertIn('CUSTOM_VIDEO_MODEL=vision-model', text)
            self.assertIn('SEE_CREDENTIAL_REF_CUSTOM=see/custom/default', text)

if __name__ == '__main__':unittest.main()
