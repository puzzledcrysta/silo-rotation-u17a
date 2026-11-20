import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_ROOT = ROOT / 'sample_data'
DB = Path(os.getenv('WORKBENCH_DB', str(ROOT/'state/ledger.sqlite3')))
TITLE = '种粮库轮换'
SLUG = 'silo-rotation'
KEY = '调出单'
FIELDS = ('需求袋数', '轮换日', '候选批次', '品种')
ROLE = '种粮库保管员'
UNIT = '袋'
SIGNATURE = '留样计量线'
RULE_VERSION = 'silo-rotation-1.0'
TABS = {'intake': '来源采信', 'contract': '字段解释', 'quality': '隔离裁决', 'domain': '留样配给', 'reconcile': '独立对账', 'runs': '批次复算', 'review': '交付复核'}
