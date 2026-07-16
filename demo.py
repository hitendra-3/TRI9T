import sys
import os
import json
import requests

sys.stdout.reconfigure(encoding='utf-8')

BASE = 'http://127.0.0.1:8000'

print('[1] Health Check')
h = requests.get(f'{BASE}/health').json()
print('   ', h)
assert h['status'] == 'healthy'
assert h['mongodb'] == 'connected', 'MongoDB not connected!'

print('[2] Clearing DB for clean run...')
r = requests.delete(f'{BASE}/api/documents/admin/clear-db')
print('   ', r.json().get('message'))

print('[3] Ingesting CT-200 Manual v1...')
with open('data/ct200_manual.md', encoding='utf-8') as f:
    md_v1 = f.read()
r = requests.post(f'{BASE}/api/documents/ingest', json={
    'document_name': 'CardioTrack CT-200',
    'version_label': 'v1',
    'markdown_content': md_v1,
    'is_new_document': True
})
res = r.json()
doc_id = res['version']['document_id']
v1_id = res['version']['id']
print('    Stats:', res['stats'])

print('[4] FTS5 Search: "4.2 Error Codes"')
r = requests.get(f'{BASE}/api/nodes/search?document_id={doc_id}&version_id={v1_id}&query="4.2 Error Codes"')
results = r.json()
assert len(results) > 0, 'No search results!'
node = results[0]
node_id = node['id']
title = node['title']
print(f'    Found: {title} (node_id={node_id})')

print('[5] Creating named selection pinned to v1...')
r = requests.post(f'{BASE}/api/selections', json={
    'name': 'Safety Deflation Tests',
    'node_ids': [node_id]
})
sel = r.json()
sel_id = sel['id']
ver_id = sel['version_id']
print(f'    Selection ID: {sel_id}, pinned to version_id: {ver_id}')

print('[6] Generating QA test cases via Gemini (may take ~20s)...')
r = requests.post(f'{BASE}/api/selections/{sel_id}/generate', timeout=120)
assert r.status_code == 200, f'Generate failed: {r.text}'
gen = r.json()
tcs = gen['test_cases']
print(f'    Generated {len(tcs)} test cases - stored in MongoDB Atlas')
for i, tc in enumerate(tcs, 1):
    print(f'    TC{i}: [{tc["priority"]}] {tc["title"]}')

print('[7] Staleness check BEFORE v2 ingestion...')
r = requests.get(f'{BASE}/api/selections/{sel_id}/test-cases')
s = r.json()
print(f'    is_stale = {s["is_stale"]}')
assert s['is_stale'] is False

print('[8] Ingesting CT-200 Manual v2 (with changes)...')
with open('data/ct200_manual_v2.md', encoding='utf-8') as f:
    md_v2 = f.read()
r = requests.post(f'{BASE}/api/documents/ingest', json={
    'document_name': 'CardioTrack CT-200',
    'version_label': 'v2',
    'markdown_content': md_v2,
    'is_new_document': False,
    'document_id': doc_id
})
print('    Stats:', r.json()['stats'])

print('[9] Staleness check AFTER v2 ingestion...')
r = requests.get(f'{BASE}/api/selections/{sel_id}/test-cases')
s = r.json()
print(f'    is_stale = {s["is_stale"]}')
print(f'    staleness_reason: {s["staleness_reason"]}')
print(f'    impacted_nodes: {len(s["impacted_nodes"])} section(s)')
for nd in s['impacted_nodes']:
    path = nd.get('path', nd.get('logical_id', ''))
    print(f'      [{nd["status"]}] {path}')
assert s['is_stale'] is True

print()
print('=' * 60)
print('DEMO COMPLETE - All 9 steps passed!')
print('MongoDB Atlas: LLM test cases stored at cloud.mongodb.com')
print('Collection: ct200_qa / generated_test_cases')
print('=' * 60)
