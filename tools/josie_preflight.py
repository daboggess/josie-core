import json
import os
import socket
import sys
from urllib.request import urlopen
from pathlib import Path


def inspect_preflight():
    josie_root_exists = os.path.exists(r'D:\Josie') and os.path.isdir(r'D:\Josie')

    mission_manager_importable = False
    try:
        import mission_manager
        mission_manager_importable = True
    except ImportError:
        mission_manager_importable = False

    python_executable = sys.executable

    ollama_reachable = False
    try:
        urlopen('http://127.0.0.1:11434', timeout=5)
        ollama_reachable = True
    except:
        pass

    configured_local_model = 'qwen3:14b'

    opencode_executable_exists = os.path.exists(r'I:\Josie-Storage\apps\OpenCode\1.18.23\opencode.exe')
    goose_executable_exists = os.path.exists(r'I:\Josie-Storage\apps\goose-1.50.0\goose-package\goose.exe')

    conversation_control_8790_listening = False
    try:
        with socket.create_connection(('127.0.0.1', 8790), timeout=5):
            conversation_control_8790_listening = True
    except:
        pass

    overall_ready = (
        josie_root_exists and
        mission_manager_importable and
        ollama_reachable and
        opencode_executable_exists and
        goose_executable_exists and
        conversation_control_8790_listening
    )

    result = {
        'josie_root_exists': josie_root_exists,
        'mission_manager_importable': mission_manager_importable,
        'python_executable': python_executable,
        'ollama_reachable': ollama_reachable,
        'configured_local_model': configured_local_model,
        'opencode_executable_exists': opencode_executable_exists,
        'goose_executable_exists': goose_executable_exists,
        'conversation_control_8790_listening': conversation_control_8790_listening,
        'overall_ready': overall_ready
    }
    print(json.dumps(result, indent=4))
    return result


if __name__ == '__main__':
    inspect_preflight()