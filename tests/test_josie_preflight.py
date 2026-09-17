import unittest
from unittest.mock import patch
from io import StringIO
import json
import sys
import os

# Add tools directory to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tools.josie_preflight import inspect_preflight

class TestJosiePreflight(unittest.TestCase):
    def test_inspection_keys(self):
        result = inspect_preflight()
        self.assertEqual(len(result), 9)
        self.assertIn('josie_root_exists', result)
        self.assertIn('mission_manager_importable', result)
        self.assertIn('python_executable', result)
        self.assertIn('ollama_reachable', result)
        self.assertIn('configured_local_model', result)
        self.assertIn('opencode_executable_exists', result)
        self.assertIn('goose_executable_exists', result)
        self.assertIn('conversation_control_8790_listening', result)
        self.assertIn('overall_ready', result)

    def test_missing_components(self):
        # Mock os.path.exists to return False for key files
        with patch('os.path.exists', return_value=False):
            result = inspect_preflight()
            self.assertFalse(result['josie_root_exists'])
            self.assertFalse(result['opencode_executable_exists'])
            self.assertFalse(result['goose_executable_exists'])

        # Mock the inspection function's dependency. The tools module imports
        # `urlopen` directly into its namespace (from urllib.request import urlopen),
        # so patch tools.josie_preflight.urlopen for the mock to take effect.
        with patch('tools.josie_preflight.urlopen', side_effect=Exception("Connection failed")):
            result = inspect_preflight()
            self.assertFalse(result['ollama_reachable'])

        # Mock socket.create_connection to raise exception
        with patch('socket.create_connection', side_effect=Exception("Connection failed")):
            result = inspect_preflight()
            self.assertFalse(result['conversation_control_8790_listening'])

    def test_script_output(self):
        # Test script output when run directly
        with patch('sys.stdout', new=StringIO()) as fake_output:
            with patch('sys.argv', ['tools/josie_preflight.py']):
                inspect_preflight()
                output = fake_output.getvalue()
                # Check if output is valid JSON
                try:
                    json.loads(output)
                except json.JSONDecodeError:
                    self.fail("Output is not valid JSON")
                # Check if all required keys are present
                parsed = json.loads(output)
                self.assertEqual(len(parsed), 9)
                self.assertIn('josie_root_exists', parsed)
                self.assertIn('mission_manager_importable', parsed)
                self.assertIn('python_executable', parsed)
                self.assertIn('ollama_reachable', parsed)
                self.assertIn('configured_local_model', parsed)
                self.assertIn('opencode_executable_exists', parsed)
                self.assertIn('goose_executable_exists', parsed)
                self.assertIn('conversation_control_8790_listening', parsed)
                self.assertIn('overall_ready', parsed)

if __name__ == '__main__':
    unittest.main()
