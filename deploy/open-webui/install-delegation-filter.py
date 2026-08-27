"""Run inside the existing Open WebUI container; updates only filter source."""
import hashlib
import asyncio
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, '/app/backend')
if not os.environ.get('WEBUI_SECRET_KEY'):
    os.environ['WEBUI_SECRET_KEY'] = Path('/app/backend/.webui_secret_key').read_text().strip()
from open_webui.models.functions import Functions
from open_webui.utils.plugin import load_function_module_by_id

async def main():
    filter_id = 'josie_exact_tool_response'
    current = await Functions.get_function_by_id(filter_id)
    if current is None:
        raise RuntimeError('Existing Josie filter is missing; refusing to create or reconfigure model')
    content = Path('/opt/josie/exact-tool-response-filter.py').read_text(encoding='utf-8')
    module, kind, _ = await load_function_module_by_id(filter_id, content)
    assert kind == 'filter' and callable(module.outlet)
    digest = hashlib.sha256(current.content.encode()).hexdigest()
    backup = Path('/app/backend/data') / ('josie-filter-before-delegate-' + digest + '.json')
    if not backup.exists():
        with backup.open('x', encoding='utf-8') as stream:
            json.dump(current.model_dump(mode='json'), stream, indent=2)
    saved = await Functions.update_function_by_id(filter_id, {'content': content})
    assert saved is not None and saved.content == content
    before = current.model_dump()
    after = saved.model_dump()
    assert all(before[key] == after[key] for key in before if key not in {'content', 'updated_at'})
    print(json.dumps({'filter_updated': True, 'other_fields_preserved': True,
                      'rollback_file': str(backup),
                      'sha256': hashlib.sha256(content.encode()).hexdigest()}))

asyncio.run(main())
