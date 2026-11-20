import pytest
from app.errors import DataError
from app.modules.intake.service import intake
from app.settings import KEY


def test_bom(source):
    # TRAP-02
    assert source.startswith(b'\xef\xbb\xbf')
    assert intake(source)['header'][0] == KEY


def test_multiline(source):
    # TRAP-03
    raw = intake(source)
    assert '\n' in raw['rows'][0]['raw'][-1]
    assert [row['line'] for row in raw['rows'][:2]] == [2,4]


def test_repeated(source):
    # TRAP-04
    report = intake(source)
    assert len(report['header_lines']) == 1
    assert report['header_lines'][0] not in {row['line'] for row in report['rows']}


def test_width(source):
    # TRAP-05
    bad, = intake(source)['rejected']
    assert (bad['code'],bad['raw']) == ('WIDTH',['残行','2'])


def test_empty_states():
    # TRAP-18
    for text,code in [(b'','EMPTY'),(b' \n','BLANK_FILE'),(b'header\n','HEADER_ONLY')]:
        with pytest.raises(DataError) as error:
            intake(text)
        assert error.value.code == code


def test_gb18030(source):
    decoded = source.decode('utf-8-sig')
    assert intake(decoded.encode('gb18030'))['encoding'] == 'gb18030'
    assert intake(decoded.encode('gb18030'))['header'][0] == KEY


def test_truncated_rejected():
    with pytest.raises(DataError) as error:
        intake(b'name,note\nfoo,"broken')
    assert error.value.code == 'CSV' and '2' in str(error.value)
