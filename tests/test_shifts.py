import csv
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
import pytest

DAY = '2026-11-18'
LOTS = 'L1,2026-12-01,10,2,稻01;L2,2027-01-15,20,0,稻01'


def order(key, demand, candidates=LOTS, day=DAY, revision=1,
          time='2026-11-18T09:00:00+08:00', cultivar='稻01'):
    return [key, str(revision), time, str(demand), day, candidates, cultivar, '']


def source_csv(rows):
    out = StringIO(newline='')
    pen = csv.writer(out)
    pen.writerow(['调出单', '修订号', '提交时间', '需求袋数', '轮换日', '候选批次', '品种', '原始备注'])
    pen.writerows(rows)
    return out.getvalue()


def book_csv(pairs):
    out = StringIO(newline='')
    pen = csv.writer(out)
    pen.writerow(['调出单', '外部记录值(袋)'])
    pen.writerows(pairs)
    return out.getvalue()


def make_run(client, rows, book, day=DAY):
    report = client.post('/api/runs', json={'data': source_csv(rows), 'book': book_csv(book)}).json()
    return report['manifest']['run_id']


@pytest.fixture
def clean_run(client):
    rows = [order('O1', 6, time='2026-11-18T09:00:00+08:00'),
            order('O2', 6, time='2026-11-18T09:05:00+08:00'),
            order('O3', 6, time='2026-11-18T09:10:00+08:00')]
    return make_run(client, rows, [('O1', 6), ('O2', 6), ('O3', 6)])


def adjudicate(client, run_id, strategy='resequence', picked=(), base_version=0, day=DAY):
    return client.post(f'/api/shifts/{run_id}/{day}/adjudicate',
                       json={'strategy': strategy, 'picked': list(picked), 'base_version': base_version})


def review(client, run_id, version, decision='确认', note='', day=DAY):
    return client.post(f'/api/shifts/{run_id}/{day}/review',
                       json={'version': version, 'decision': decision, 'note': note})


def test_naive_view_exposes_double_occupation(client, clean_run):
    detail = client.get(f'/api/shifts/{clean_run}/{DAY}').json()
    pool = {row['lot']: row for row in detail['pool']}
    assert (pool['L1']['demanded'], pool['L1']['available'], pool['L1']['over']) == (18, 8, 10)
    assert pool['L1']['retained'] == 2 and pool['L2']['over'] == 0
    assert detail['current'] is None and [o['key'] for o in detail['orders']] == ['O1', 'O2', 'O3']


def test_resequence_allocates_oldest_first_without_double_occupy(client, clean_run):
    payload = adjudicate(client, clean_run).json()
    assert payload['version'] == 1 and payload['strategy'] == 'resequence'
    orders = {row['key']: row for row in payload['result']['orders']}
    assert orders['O1']['lines'] == [{'lot': 'L1', 'quantity': '6'}]
    assert orders['O2']['lines'] == [{'lot': 'L1', 'quantity': '2'}, {'lot': 'L2', 'quantity': '4'}]
    assert orders['O3']['lines'] == [{'lot': 'L2', 'quantity': '6'}]
    assert payload['result']['totals'] == {'demand': '18', 'allocated': '18', 'unmet': '0'}
    pool = {row['lot']: row for row in payload['result']['pool']}
    assert all(row['allocated'] <= row['available'] for row in pool.values())
    assert (pool['L1']['left'], pool['L2']['left']) == (0, 10)


def test_freeze_keeps_picked_and_clips_rest(client, clean_run):
    payload = adjudicate(client, clean_run, strategy='freeze', picked=['O1']).json()
    orders = {row['key']: row for row in payload['result']['orders']}
    assert orders['O1']['state'] == '已备货' and orders['O1']['changed'] is False
    assert orders['O1']['lines'] == [{'lot': 'L1', 'quantity': '6'}]
    assert (orders['O2']['lines'], orders['O2']['unmet']) == ([{'lot': 'L1', 'quantity': '2'}], '4')
    assert (orders['O3']['lines'], orders['O3']['unmet']) == ([], '6')
    pool = {row['lot']: row for row in payload['result']['pool']}
    assert pool['L2']['allocated'] == 0
    assert payload['result']['totals']['unmet'] == '10'


def test_freeze_infeasible_keeps_old_version(client, clean_run):
    first = adjudicate(client, clean_run).json()
    failed = adjudicate(client, clean_run, strategy='freeze', picked=['O1', 'O2'], base_version=1)
    assert (failed.status_code, failed.json()['code']) == (422, 'FREEZE_INFEASIBLE')
    detail = client.get(f'/api/shifts/{clean_run}/{DAY}').json()
    assert detail['current']['version'] == first['version'] == 1
    assert detail['current']['strategy'] == 'resequence'


def test_adjudication_idempotent_no_duplicate_occupation(client, clean_run):
    first = adjudicate(client, clean_run).json()
    again = adjudicate(client, clean_run).json()
    assert again == first
    detail = client.get(f'/api/shifts/{clean_run}/{DAY}').json()
    assert [item['version'] for item in detail['versions']] == [1]
    assert detail['current']['id'] == first['id']


def test_concurrent_adjudication_single_version(client, clean_run):
    body = {'strategy': 'resequence', 'picked': [], 'base_version': 0}
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(
            lambda _: client.post(f'/api/shifts/{clean_run}/{DAY}/adjudicate', json=body).json(),
            range(4)))
    assert all(item == results[0] for item in results)
    detail = client.get(f'/api/shifts/{clean_run}/{DAY}').json()
    assert len(detail['versions']) == 1


def test_concurrent_different_adjudications_single_winner(client, clean_run):
    bodies = [{'strategy': 'resequence', 'picked': [], 'base_version': 0},
              {'strategy': 'freeze', 'picked': ['O1'], 'base_version': 0}]
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(
            lambda body: client.post(f'/api/shifts/{clean_run}/{DAY}/adjudicate', json=body),
            bodies * 2))
    won = [response.json() for response in responses if response.status_code == 200]
    stale = [response for response in responses if response.status_code == 409]
    assert won and stale
    assert all(response.json()['code'] == 'STALE' for response in stale)
    assert all(item['id'] == won[0]['id'] and item['version'] == 1 for item in won)
    detail = client.get(f'/api/shifts/{clean_run}/{DAY}').json()
    assert [item['version'] for item in detail['versions']] == [1]


def test_stale_base_version_rejected(client, clean_run):
    stale = adjudicate(client, clean_run, base_version=3)
    assert (stale.status_code, stale.json()['code']) == (409, 'STALE')
    adjudicate(client, clean_run)
    stale = adjudicate(client, clean_run, picked=['O2'], base_version=0)
    assert (stale.status_code, stale.json()['code']) == (409, 'STALE')


def test_picked_must_belong_to_shift(client, clean_run):
    response = adjudicate(client, clean_run, picked=['O9'])
    assert (response.status_code, response.json()['code']) == (422, 'PICKED_UNKNOWN')


def test_late_revision_changes_available_inventory(client):
    rows = [order('O1', 6, candidates='L1,2026-12-01,10,2,稻01', time='2026-11-18T09:00:00+08:00'),
            order('O2', 6, candidates='L1,2026-12-01,4,2,稻01', time='2026-11-18T09:05:00+08:00')]
    run_id = make_run(client, rows, [('O1', 6), ('O2', 2)])
    detail = client.get(f'/api/shifts/{run_id}/{DAY}').json()
    pool, = detail['pool']
    assert (pool['lot'], pool['available']) == ('L1', 2)
    payload = adjudicate(client, run_id).json()
    orders = {row['key']: row for row in payload['result']['orders']}
    assert (orders['O1']['unmet'], orders['O2']['unmet']) == ('4', '6')
    assert payload['result']['totals']['allocated'] == '2'


def test_expiry_day_lot_stops_issuing(client):
    rows = [order('O1', 5, candidates='L0,2026-11-18,50,0,稻01')]
    run_id = make_run(client, rows, [('O1', 0)])
    detail = client.get(f'/api/shifts/{run_id}/{DAY}').json()
    pool, = detail['pool']
    assert pool['blocked'] is True and pool['available'] == 50
    payload = adjudicate(client, run_id).json()
    row, = payload['result']['orders']
    assert row['lines'] == [] and row['unmet'] == '5'
    assert payload['result']['pool'][0]['allocated'] == 0


def test_retained_sample_never_allocated(client):
    rows = [order('O1', 3, candidates='L3,2026-12-01,5,5,稻01')]
    run_id = make_run(client, rows, [('O1', 0)])
    payload = adjudicate(client, run_id).json()
    row, = payload['result']['orders']
    pool, = payload['result']['pool']
    assert row['unmet'] == '3' and pool['retained'] == 5 and pool['allocated'] == 0


def test_publish_requires_clean_reconciliation(client):
    rows = [order('O1', 6, time='2026-11-18T09:00:00+08:00'),
            order('O2', 6, time='2026-11-18T09:05:00+08:00')]
    run_id = make_run(client, rows, [('O1', 6), ('O2', 5)])
    adjudicate(client, run_id)
    blocked = review(client, run_id, 1)
    assert (blocked.status_code, blocked.json()['code']) == (422, 'RECONCILE_DIFF')
    assert review(client, run_id, 1, '退回', '外部账待补').status_code == 200
    assert client.get(f'/api/shifts/{run_id}/{DAY}/export').status_code == 409


def test_review_and_export_versions_stay_consistent(client, clean_run):
    first = adjudicate(client, clean_run).json()
    unpublished = client.get(f'/api/shifts/{clean_run}/{DAY}/export')
    assert (unpublished.status_code, unpublished.json()['code']) == (409, 'UNPUBLISHED')
    assert review(client, clean_run, 1, '退回').json()['code'] == 'REVIEW_NOTE'
    assert review(client, clean_run, 1, note='对账已核').status_code == 200
    bundle = client.get(f'/api/shifts/{clean_run}/{DAY}/export').json()
    assert bundle['manifest']['adjudication_version'] == first['version'] == 1
    assert bundle['manifest']['strategy'] == 'resequence'
    assert bundle['totals'] == {'demand': '18', 'allocated': '18', 'unmet': '0'}
    assert bundle['reviews'][0]['decision'] == '确认' and bundle['reconciliation']['mismatched'] == 0
    second = adjudicate(client, clean_run, strategy='freeze', picked=['O1'], base_version=1).json()
    assert second['version'] == 2
    assert client.get(f'/api/shifts/{clean_run}/{DAY}/export').status_code == 409
    assert review(client, clean_run, 1).status_code == 409
    assert review(client, clean_run, 2, note='冻结备货').status_code == 200
    bundle = client.get(f'/api/shifts/{clean_run}/{DAY}/export').json()
    assert bundle['manifest']['adjudication_version'] == 2
    assert bundle['manifest']['strategy'] == 'freeze'
    assert [row['version'] for row in bundle['reviews']] == [2, 1]


def test_multiple_shifts_are_isolated(client):
    rows = [order('O1', 6, time='2026-11-18T09:00:00+08:00'),
            order('O2', 6, day='2026-11-19', time='2026-11-19T09:00:00+08:00')]
    run_id = make_run(client, rows, [('O1', 6), ('O2', 6)])
    overview = client.get(f'/api/shifts/{run_id}').json()
    assert [item['shift'] for item in overview['shifts']] == ['2026-11-18', '2026-11-19']
    adjudicate(client, run_id)
    later = client.get(f'/api/shifts/{run_id}/2026-11-19').json()
    assert later['current'] is None
    missing = client.get(f'/api/shifts/{run_id}/2026-11-20')
    assert (missing.status_code, missing.json()['code']) == (404, 'SHIFT_UNKNOWN')


def test_unknown_run_and_shift(client):
    assert client.get('/api/shifts/not-found').status_code == 404
    response = client.post('/api/shifts/not-found/2026-11-18/adjudicate',
                           json={'strategy': 'freeze', 'picked': [], 'base_version': 0})
    assert response.status_code == 404


def test_sample_shift_never_double_occupies(client):
    run_id = client.post('/api/runs', json={}).json()['manifest']['run_id']
    overview = client.get(f'/api/shifts/{run_id}').json()
    shift, = overview['shifts']
    assert shift['orders'] == 26 and shift['current'] is None
    detail = client.get(f"/api/shifts/{run_id}/{shift['shift']}").json()
    assert any(row['over'] for row in detail['pool'])
    payload = adjudicate(client, run_id, day=shift['shift']).json()
    result = payload['result']
    for row in result['pool']:
        assert row['allocated'] <= row['available']
        assert not (row['blocked'] and row['allocated'])
    totals = result['totals']
    assert int(totals['allocated']) + int(totals['unmet']) == int(totals['demand'])
    failed = adjudicate(client, run_id, strategy='freeze', picked=['00101'],
                        base_version=1, day=shift['shift'])
    assert failed.status_code == 422 and failed.json()['code'] == 'FREEZE_INFEASIBLE'
    assert client.get(f"/api/shifts/{run_id}/{shift['shift']}").json()['current']['version'] == 1
    blocked = review(client, run_id, 1, day=shift['shift'])
    assert (blocked.status_code, blocked.json()['code']) == (422, 'RECONCILE_DIFF')
