from collections import defaultdict
from app.modules.domain.rule import day
from app.modules.domain.values import parts, whole
from app.pipeline import stages


def orders_by_shift(source):
    """Join domain-accepted rows with their ready records, grouped by shift day (轮换日)."""
    result = stages(source)
    ready = {row['key']: row for row in result['quality']['ready']}
    groups = defaultdict(list)
    for row in result['accepted']:
        record = ready[row['key']]
        fields = record['fields']
        lines = [{'lot': item['metric'], 'quantity': item['value']}
                 for item in row['proof'] if item['metric'] != '未满足']
        unmet = next(item['value'] for item in row['proof'] if item['metric'] == '未满足')
        groups[fields['轮换日']].append({
            'key': row['key'], 'line': row['line'], 'revision': record['revision'],
            'time': record['time'], 'cultivar': fields['品种'],
            'demand': str(whole(fields['需求袋数'], 0, 1000000)),
            'candidates': fields['候选批次'],
            'independent': {'lines': lines, 'unmet': unmet}})
    return groups


def build_pool(orders, shift):
    """Latest submitted snapshot per lot wins; lots expiring on the shift day stop issuing."""
    closing = day(shift)
    snapshots = {}
    for order in orders:
        rank = (order['time'], order['revision'], -order['line'])
        for item in parts(order['candidates']):
            lot, expires, stocks, retained, cultivar = item.split(',')
            if lot not in snapshots or rank > snapshots[lot][0]:
                stock = whole(stocks, 0, 1000000)
                snapshots[lot] = (rank, {'lot': lot, 'expiry': expires, 'cultivar': cultivar,
                                         'stock': stock, 'retained': whole(retained, 0, stock)})
    pool = {}
    for lot, (_, snapshot) in snapshots.items():
        available = snapshot['stock'] - snapshot['retained']
        pool[lot] = {**snapshot, 'available': available,
                     'blocked': day(snapshot['expiry']) <= closing}
    return pool


def naive_view(orders, pool):
    """Sum independent per-order picks per lot to expose double occupation."""
    demanded = defaultdict(int)
    for order in orders:
        for line in order['independent']['lines']:
            demanded[line['lot']] += int(line['quantity'])
    view = []
    for lot in sorted(pool, key=lambda name: (pool[name]['expiry'], name)):
        entry = pool[lot]
        need = demanded.get(lot, 0)
        view.append({**entry, 'demanded': need, 'over': max(0, need - entry['available'])})
    return view
