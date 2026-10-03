import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]


class CLITests(unittest.TestCase):
    def invoke(self, *arguments):
        return subprocess.run([sys.executable, str(PROJECT / 'run.py'), *map(str, arguments)], cwd=PROJECT,
                              capture_output=True, text=True, timeout=15)

    def test_fresh_process_import_report_and_packet(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / 'research'
            result = self.invoke('init', '--workspace', workspace)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['companies'], 0)
            result = self.invoke('import', PROJECT/'examples/companies/aster.json', '--workspace', workspace)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = Path(directory) / 'brief.md'
            result = self.invoke('research', 'ASTER', '--workspace', workspace, '--output', report)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('Operating assumptions', report.read_text())
            result = self.invoke('research', 'ASTER', '--workspace', workspace, '--output', report)
            self.assertEqual(result.returncode, 2)
            packet = Path(directory) / 'packet.json'
            result = self.invoke('packet', 'ASTER', '--workspace', workspace, '--output', packet)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(packet.read_text())['synthetic'])
            self.assertNotIn('settings', json.loads(packet.read_text()))

    def test_mockless_delivery_command_is_disabled_without_activation(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.invoke('deliver', '--workspace', directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['attempted'], 0)
            self.assertEqual(json.loads(result.stdout)['state'], 'disabled')

    def test_sample_generation_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.invoke('samples', '--output', directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            path = Path(directory)/'companies/aster.json'
            original = path.read_bytes()
            result = self.invoke('samples', '--output', directory)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(path.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
