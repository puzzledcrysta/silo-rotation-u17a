import json
from datetime import datetime, timezone
from hashlib import sha256
from sqlite3 import IntegrityError
from app.errors import DataError
from app.settings import RULE_VERSION
from app.store import connection
from app.modules.runs.repository import lookup
from . import repository
from .allocate import STRATEGIES, adjudicate
from .pool import build_pool, naive_view, orders_by_shift

SHIFT_RULE = f'{RULE_VERSION}+shift-1'
PUBLIC_ORDER = ('key', 'line', 'time', 'revision', 'demand', 'cultivar', 'independent')


def fingerprint(run_id, shift, strategy, picked):
    material = f"{SHIFT_RULE}:{run_id}:{shift}:{strategy}:{','.join(picked)}"
    return sha256(material.encode()).hexdigest()


def shift_orders(run_row, shift):
    groups = orders_by_shift(run_row['source'])
    if shift not in groups:
        raise DataError('SHIFT_UNKNOWN', '没有此班次', 404)
    return groups[shift]


def published(current, trail):
    return bool(current and trail) and \
        trail[0]['adjudication'] == current['version'] and trail[0]['decision'] == '确认'


def overview(run_id):
    with connection() as db:
        row = lookup(db, run_id)
        shifts = []
        for shift, orders in sorted(orders_by_shift(row['source']).items()):
            current = repository.latest(db, run_id, shift)
            trail = repository.reviews(db, run_id, shift)
            shifts.append({'shift': shift, 'orders': len(orders),
                           'demand': str(sum(int(order['demand']) for order in orders)),
                           'current': current['version'] if current else None,
                           'published': published(current, trail)})
        return {'run': run_id, 'shifts': shifts}


def detail(run_id, shift):
    with connection() as db:
        row = lookup(db, run_id)
        orders = shift_orders(row, shift)
        pool = build_pool(orders, shift)
        current = repository.latest(db, run_id, shift)
        run = json.loads(row['result'])
        return {'shift': shift,
                'pool': naive_view(orders, pool),
                'orders': [{key: order[key] for key in PUBLIC_ORDER}
                           for order in sorted(orders, key=lambda order: (order['time'], order['key']))],
                'current': json.loads(current['result']) if current else None,
                'versions': repository.versions(db, run_id, shift),
                'reviews': repository.reviews(db, run_id, shift),
                'reconciliation': {'mismatched': run['book']['mismatched'],
                                   'delta': run['book']['delta']}}


def adjudicate_shift(run_id, shift, strategy, picked, base_version):
    if strategy not in STRATEGIES:
        raise DataError('STRATEGY_INVALID', '裁决策略无效')
    picked = sorted(set(picked))
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = lookup(db, run_id)
        adjudication_id = fingerprint(run_id, shift, strategy, picked)
        existing = repository.by_id(db, adjudication_id)
        if existing:
            return json.loads(existing['result'])
        orders = shift_orders(row, shift)
        current = repository.latest(db, run_id, shift)
        version = current['version'] if current else 0
        if version != base_version:
            raise DataError('STALE', '班次裁决版本已过期，请刷新', 409)
        result = adjudicate(shift, orders, build_pool(orders, shift), strategy, set(picked))
        created = datetime.now(timezone.utc).isoformat()
        payload = {'id': adjudication_id, 'version': version + 1, 'shift': shift,
                   'strategy': strategy, 'picked': picked, 'created': created, 'result': result}
        try:
            repository.save(db, adjudication_id, run_id, shift, payload['version'],
                            strategy, picked, payload, created)
        except IntegrityError:
            existing = repository.by_id(db, adjudication_id)
            if existing:
                return json.loads(existing['result'])
            raise DataError('STALE', '班次裁决版本已过期，请刷新', 409) from None
        return payload


def review_shift(run_id, shift, version, decision, note):
    note = note.strip()
    if decision not in {'确认', '退回'}:
        raise DataError('REVIEW_DECISION', '复核结论无效')
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        run = json.loads(lookup(db, run_id)['result'])
        current = repository.latest(db, run_id, shift)
        if current is None:
            raise DataError('SHIFT_NO_VERSION', '班次尚未裁决')
        if current['version'] != version:
            raise DataError('STALE', '班次裁决版本已过期，请刷新', 409)
        if decision == '确认' and (not run.get('book') or run['book']['mismatched']):
            raise DataError('RECONCILE_DIFF', '独立对账未完成或存在差异，不能发布')
        if decision == '退回' and not note:
            raise DataError('REVIEW_NOTE', '退回时须填写复核意见')
        trail = repository.reviews(db, run_id, shift)
        record = {'version': (trail[0]['version'] if trail else 0) + 1,
                  'adjudication': version, 'decision': decision, 'note': note,
                  'changed': datetime.now(timezone.utc).isoformat()}
        repository.save_review(db, run_id, shift, record['version'], version,
                               decision, note, record['changed'])
        return record


def export_shift(run_id, shift):
    with connection() as db:
        row = lookup(db, run_id)
        current = repository.latest(db, run_id, shift)
        if current is None:
            raise DataError('SHIFT_NO_VERSION', '班次尚未裁决')
        trail = repository.reviews(db, run_id, shift)
        if not published(current, trail):
            raise DataError('UNPUBLISHED', '当前裁决版本未确认，不能导出', 409)
        run = json.loads(row['result'])
        payload = json.loads(current['result'])
        bundle = {'manifest': {**run['manifest'], 'shift': shift, 'rule': SHIFT_RULE,
                               'adjudication': payload['id'],
                               'adjudication_version': payload['version'],
                               'strategy': payload['strategy'], 'picked': payload['picked']},
                  'orders': payload['result']['orders'], 'pool': payload['result']['pool'],
                  'totals': payload['result']['totals'],
                  'reconciliation': run['book'], 'reviews': trail}
        return json.dumps(bundle, ensure_ascii=False, indent=2)
