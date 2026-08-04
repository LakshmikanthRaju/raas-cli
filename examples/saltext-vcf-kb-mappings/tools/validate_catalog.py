#!/usr/bin/env python3
from pathlib import Path
import sys, yaml
root=Path(__file__).resolve().parents[1]
cat=yaml.safe_load((root/'solutions/catalog.yaml').read_text())
errors=[]; ids=set(); kbids=set()
for e in cat.get('entries',[]):
    if e['id'] in ids: errors.append('duplicate id '+e['id'])
    if e['kb_id'] in kbids: errors.append('duplicate kb '+e['kb_id'])
    ids.add(e['id']); kbids.add(e['kb_id'])
    p=root/e['solution_path']
    if not p.is_file(): errors.append('missing '+str(p)); continue
    s=yaml.safe_load(p.read_text())
    if s['metadata']['id']!=e['id']: errors.append(str(p)+': metadata.id mismatch')
    if s['kb']['id']!=e['kb_id']: errors.append(str(p)+': kb.id mismatch')
    if s['execution']['enabled']!=e['automation']['execution_enabled']: errors.append(str(p)+': enabled mismatch')
    if s['execution']['state']!=e['automation']['state']: errors.append(str(p)+': state mismatch')
    if s['execution']['enabled'] and not s['execution']['state']: errors.append(str(p)+': enabled without state')
if errors:
    print('Validation failed:'); [print(' - '+x) for x in errors]; sys.exit(1)
print(f'Validated {len(ids)} KB entries successfully.')
