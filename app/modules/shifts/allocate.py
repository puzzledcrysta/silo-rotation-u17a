from app.errors import DataError

STRATEGIES = {'freeze': '冻结备货分配', 'resequence': '重排未发车'}


def adjudicate(shift, orders, pool, strategy, picked):
    """Deterministic shift allocation. Picked orders keep their staged lines untouched;
    undispatched orders are clipped to the remaining pool (freeze) or re-picked
    in expiry order (resequence). The pool is decremented once per issued bag,
    so no lot is ever occupied twice and retained samples stay untouched."""
    known = {order['key'] for order in orders}
    unknown = sorted(set(picked) - known)
    if unknown:
        raise DataError('PICKED_UNKNOWN', f"备货单不在班次内 {','.join(unknown)}")
    remaining = {lot: entry['available'] for lot, entry in pool.items()}
    blocked = {lot for lot, entry in pool.items() if entry['blocked']}
    sequence = sorted(orders, key=lambda order: (order['time'], order['key']))
    chosen = {}

    def freeze_staged(order):
        lines = []
        for line in order['independent']['lines']:
            lot, quantity = line['lot'], int(line['quantity'])
            if lot in blocked or remaining[lot] < quantity:
                left = 0 if lot in blocked else remaining[lot]
                raise DataError('FREEZE_INFEASIBLE',
                                f"调出单 {order['key']} 已备货 {lot} {quantity} 袋，班次可用 {left} 袋")
            remaining[lot] -= quantity
            lines.append({'lot': lot, 'quantity': str(quantity)})
        return lines, order['independent']['unmet']

    def clip_staged(order):
        lines, issued = [], 0
        for line in order['independent']['lines']:
            lot, quantity = line['lot'], int(line['quantity'])
            take = 0 if lot in blocked else min(quantity, remaining[lot])
            remaining[lot] -= take
            issued += take
            if take:
                lines.append({'lot': lot, 'quantity': str(take)})
        return lines, str(int(order['demand']) - issued)

    def repick(order):
        need, lines = int(order['demand']), []
        eligible = sorted((entry for entry in pool.values()
                           if entry['cultivar'] == order['cultivar'] and not entry['blocked']
                           and remaining[entry['lot']] > 0),
                          key=lambda entry: (entry['expiry'], entry['lot']))
        for entry in eligible:
            if not need:
                break
            take = min(remaining[entry['lot']], need)
            remaining[entry['lot']] -= take
            need -= take
            if take:
                lines.append({'lot': entry['lot'], 'quantity': str(take)})
        return lines, str(need)

    for order in (row for row in sequence if row['key'] in picked):
        lines, unmet = freeze_staged(order)
        chosen[order['key']] = ('已备货', lines, unmet)
    for order in (row for row in sequence if row['key'] not in picked):
        lines, unmet = clip_staged(order) if strategy == 'freeze' else repick(order)
        chosen[order['key']] = ('未发车', lines, unmet)

    result_orders = []
    for order in sequence:
        state, lines, unmet = chosen[order['key']]
        result_orders.append({'key': order['key'], 'line': order['line'], 'state': state,
                              'demand': order['demand'], 'cultivar': order['cultivar'],
                              'lines': lines, 'unmet': unmet,
                              'changed': lines != order['independent']['lines']})
    usage = []
    for lot in sorted(pool, key=lambda name: (pool[name]['expiry'], name)):
        entry = pool[lot]
        usage.append({**entry, 'allocated': entry['available'] - remaining[lot],
                      'left': remaining[lot]})
    totals = {'demand': str(sum(int(order['demand']) for order in result_orders)),
              'allocated': str(sum(int(line['quantity']) for order in result_orders
                                   for line in order['lines'])),
              'unmet': str(sum(int(order['unmet']) for order in result_orders))}
    return {'shift': shift, 'strategy': strategy, 'orders': result_orders,
            'pool': usage, 'totals': totals}
