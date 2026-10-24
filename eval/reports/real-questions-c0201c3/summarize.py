"""Summary numbers + human review sheet (review-th.csv). Outcome classes:
pass / fail (AI preliminary review) ; service_failure = provider error/timeout/runner error (none in this run)."""
import csv, collections, json, statistics
from pathlib import Path
HERE = Path(__file__).resolve().parent
rd = lambda p: json.loads((HERE / p).read_text(encoding='utf8'))
mech = {r['id']: r for r in rd('mechanical.json')}
ver = rd('review-verdicts.json')['verdicts']
cases = {c['id']: c for c in rd('expectations.json')['cases']}
items = {json.loads(l)['id']: json.loads(l) for l in (HERE / 'dataset.jsonl').read_text(encoding='utf8').splitlines()}
core = set(rd('core-subset.json')['core_ids'])
assert set(ver) == set(mech), set(ver) ^ set(mech)

def label(rid):
    return 'service_failure' if mech[rid]['service_failure'] else ver[rid][0]
planned = [r for r in mech if mech[r]['repeat'] == 1 or mech[r]['case_id'] in core]
extra = sorted(set(mech) - set(planned))
cnt = collections.Counter(label(r) for r in planned)
cat = collections.Counter(ver[r][1] for r in planned if label(r) == 'fail')
r1 = [r for r in mech if mech[r]['repeat'] == 1]
cnt_r1 = collections.Counter(label(r) for r in r1)
per_core = {}
for cid in sorted(core):
    labs = [label(f'{cid}-r{k}') for k in (1, 2, 3)]
    per_core[cid] = labs
ok = ('pass', 'pass_by_policy')  # owner policy: a medical refusal is the correct behaviour
all3 = sorted(c for c, l in per_core.items() if all(x in ok for x in l))
none3 = sorted(c for c, l in per_core.items() if not any(x in ok for x in l))
mixed = sorted(set(core) - set(all3) - set(none3))
by_platform = collections.defaultdict(collections.Counter)
for r in r1: by_platform[items[mech[r]['case_id']]['source_platform']][label(r)] += 1

def stats(v):
    v = sorted(v); q = lambda p: v[min(len(v) - 1, int(round(p * (len(v) - 1))))]
    return {'n': len(v), 'median': round(statistics.median(v), 1), 'p90': round(q(0.9), 1), 'max': round(v[-1], 1)}
lat_all = stats([mech[r]['elapsed_excl_pacer'] for r in planned])
answered_model = [r for r in planned if mech[r]['outcome'] == 'answered' and 'answer' in mech[r]['stages']]
lat_model = stats([mech[r]['elapsed_excl_pacer'] for r in answered_model])
fd = [mech[r]['first_delta_excl_pacer'] for r in answered_model if mech[r]['first_delta_excl_pacer'] is not None]
lat_first = stats(fd) if fd else None
calls = stats([len(mech[r]['stages']) for r in planned])
summary = {'planned_results': len(planned), 'extra_results_not_counted': extra, 'counts': dict(cnt),
           'fail_categories': dict(cat), 'repeat1_all61': dict(cnt_r1), 'repeat1_by_platform': {k: dict(v) for k, v in by_platform.items()},
           'core20_all_three_pass': all3, 'core20_no_pass': none3, 'core20_mixed': mixed, 'core20_detail': per_core,
           'latency_seconds_excluding_pacer_all': lat_all, 'latency_seconds_model_answers': lat_model,
           'first_text_seconds_model_answers': lat_first, 'model_calls_per_question': calls,
           'note': 'Latency = wall time of stream_understood_chat minus the harness pacer waits (12.5 s for results 1-15, 6.0 s after the key change); local runner to Gemini, not web latency.'}
(HERE / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf8')
with (HERE / 'review-th.csv').open('w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f)
    w.writerow(['ผลลัพธ์', 'รหัสคำถาม', 'รอบ', 'อยู่ในชุดแกนกลาง', 'นับในสรุป', 'แพลตฟอร์ม', 'URL ต้นทาง', 'คำถามต้นฉบับ',
                'พฤติกรรมที่คาดหวัง (ล็อกก่อนรัน)', 'ห้าม', 'คำตอบจริง', 'การ์ดความรู้ที่อ้าง', 'จำนวนการเรียกโมเดล',
                'เวลา (วินาที ไม่รวมพัก)', 'ผล AI เบื้องต้น', 'ประเภทที่ไม่ผ่าน', 'เหตุผล AI', 'ผลตรวจผู้จัดทำ', 'ผลตรวจผู้เชี่ยวชาญ', 'หมายเหตุ'])
    for rid in sorted(mech, key=lambda x: (mech[x]['case_id'], mech[x]['repeat'])):
        m = mech[rid]; c = cases[m['case_id']]; it = items[m['case_id']]; v = ver[rid]
        ans = m['answer'] or ('[ไม่มีคำตอบ: ' + '; '.join(m['mechanical_findings'])[:300] + ']')
        w.writerow([rid, m['case_id'], m['repeat'], 'ใช่' if m['case_id'] in core else 'ไม่', 'ใช่' if rid in planned else 'ไม่ (ผลเกินแผน)',
                    it['source_platform'], it['source_url'], c['question'], c['expected'], c['must_not'], ans,
                    '; '.join(f"{x['label']}:{x['document_slug']}" for x in m['knowledge_citations']), len(m['stages']),
                    m['elapsed_excl_pacer'], label(rid), v[1] or '', v[2], 'รอตรวจ', 'รอตรวจ', ''])
print(json.dumps(summary, ensure_ascii=False, indent=1))
