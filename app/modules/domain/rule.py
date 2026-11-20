from datetime import date
from decimal import Decimal
from app.errors import DataError
from .values import parts, whole


def day(value):
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise DataError('BUSINESS', f'日期无效 {value}') from error


def evaluate(row):
    demand = whole(row['需求袋数'],0,1000000)
    as_of = day(row['轮换日'])
    eligible, ids = [], set()
    for item in parts(row['候选批次']):
        fields = item.split(',')
        if len(fields) != 5:
            raise DataError('BUSINESS', f'候选批字段数错误 {item}')
        lot, expires, stocks, retained, cultivar = fields
        stock = whole(stocks,0,1000000)
        retain = whole(retained,0,stock)
        if not lot or lot in ids:
            raise DataError('BUSINESS', f'候选批号重复或缺失 {lot}')
        ids.add(lot)
        expiry = day(expires)
        if expiry > as_of and cultivar == row['品种']:
            eligible.append((expiry,lot,stock-retain))
    balance, proof = demand, []
    for _,lot,available in sorted(eligible):
        issued = min(available,balance)
        balance -= issued
        if issued:
            proof.append((lot,issued,'袋'))
    return Decimal(demand-balance), [*proof,('未满足',balance,'袋')]
