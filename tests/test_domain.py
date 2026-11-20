from decimal import Decimal
import pytest
from app.errors import DataError
from app.modules.domain.rule import evaluate


def test_rotate(cases):
    # TRAP-19
    actual, evidence = evaluate(cases['rotate'])
    assert actual == Decimal('12')
    assert evidence == [('A',4,'袋'),('B',8,'袋'),('未满足',0,'袋')]
    tied = dict(cases['rotate'],候选批次='B,2026-12-01,12,2,稻01;A,2026-12-01,7,3,稻01')
    assert evaluate(tied)[1] == evidence


def test_expiry(cases):
    actual, evidence = evaluate(cases['expiry'])
    assert actual == Decimal('2')


def test_cultivar(cases):
    actual, evidence = evaluate(cases['cultivar'])
    assert actual == Decimal('0')


def test_retain_all(cases):
    actual, evidence = evaluate(cases['retain_all'])
    assert actual == Decimal('0')


def test_bad_lot(cases):
    with pytest.raises(DataError) as error:
        evaluate(cases['bad_lot'])
    assert error.value.code in {'BUSINESS','NUMBER','RANGE','TIMESTAMP'}


def test_retain_over(cases):
    with pytest.raises(DataError) as error:
        evaluate(cases['retain_over'])
    assert error.value.code in {'BUSINESS','NUMBER','RANGE','TIMESTAMP'}


def test_bad_day(cases):
    with pytest.raises(DataError) as error:
        evaluate(cases['bad_day'])
    assert error.value.code in {'BUSINESS','NUMBER','RANGE','TIMESTAMP'}

