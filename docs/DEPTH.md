# 种粮库轮换深度登记

- 规模：中型
- 核心规则：按入库有效期优先挑批并保留每批法定留样，按整袋数量分配并单列未满足量。
- 使用者与工作流：种粮库保管员按调出单复算来源批次，对照外部记录后提交复核。

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 来源采信 | 接收分段记录、定位坏行 | `POST /api/intake` | `app/modules/intake/service.py` | `tests/test_intake.py` |
| M2 字段解释 | 归一主键、版本、时间和原字段 | `POST /api/contract` | `app/modules/contract/service.py` | `tests/test_contract.py` |
| M3 隔离裁决 | 归并重复、隔离争议版本 | `POST /api/quality` | `app/modules/quality/versions.py` | `tests/test_quality.py` |
| M4 留样配给 | 复算业务明细与边界证据 | `POST /api/domain` | `app/modules/domain/rule.py` | `tests/test_domain.py` |
| M5 独立对账 | 核对外部记录并分别计量 | `POST /api/reconcile` | `app/modules/reconcile/service.py` | `tests/test_reconcile.py` |
| M6 批次复算 | 保存运行、查询历史、复算原输入 | `POST /api/runs` | `app/modules/runs/service.py` | `tests/test_runs.py` |
| M7 交付复核 | 复核差异、阻止陈旧提交、导出证据 | `GET /api/export` | `app/modules/review/decisions.py` | `tests/test_review.py` |
| M8 班次裁决 | 裁决冻结或重排、发布前对账闸门 | `POST /api/shifts/{run}/{shift}/adjudicate` | `app/modules/shifts/allocate.py` | `tests/test_shifts.py` |

## 班次裁决规则

班次以轮换日划分。批次池取班次内最晚提交的批次快照（时刻、修订号、行号依次裁决），到期日当天停调，法定留样不参与分配。
保管员勾选已备货调出单后二选一：`freeze` 冻结备货分配，未发车单沿用原挑批并按剩余池裁减；`resequence` 重排未发车单，按到期优先从剩余池重挑。
已备货单逐袋冻结，与当前池冲突则整次裁决失败并保留旧版。分配逐袋扣减，任何批次不会被重复占用。
裁决指纹为 规则+批次+班次+策略+备货单 的 SHA-256，同班次重跑返回原版本。确认发布要求独立对账无差异，导出仅限已确认的当前版本。

## 陷阱登记

| TRAP | 现象 | 样例 | 处理位置 | 测试 |
|---|---|---|---|---|
| TRAP-02 | BOM | shift.csv | `app/modules/intake/service.py` | `tests/test_intake.py::test_bom` |
| TRAP-03 | 引号内换行 | shift.csv | `app/modules/intake/service.py` | `tests/test_intake.py::test_multiline` |
| TRAP-04 | 重复表头 | shift.csv | `app/modules/intake/service.py` | `tests/test_intake.py::test_repeated` |
| TRAP-05 | 列数不齐 | shift.csv | `app/modules/intake/service.py` | `tests/test_intake.py::test_width` |
| TRAP-07 | 空值哨兵 | shift.csv | `app/modules/contract/service.py` | `tests/test_contract.py::test_missing` |
| TRAP-08 | 主键前导零 | shift.csv | `app/modules/contract/service.py` | `tests/test_contract.py::test_leading_zero` |
| TRAP-11 | 偏移时间归一 | shift.csv | `app/modules/contract/service.py` | `tests/test_contract.py::test_offsets` |
| TRAP-14 | 等版本冲突 | shift.csv | `app/modules/quality/versions.py` | `tests/test_quality.py::test_conflicting` |
| TRAP-18 | 三种空态 | 测试构造输入 | `app/modules/intake/service.py` | `tests/test_intake.py::test_empty_states` |
| TRAP-26 | 陈旧复核 | 测试构造输入 | `app/modules/review/decisions.py` | `tests/test_review.py::test_stale` |
| TRAP-19 | 同期限批次按编号稳定选取 | cases.csv | `app/modules/domain/rule.py` | `tests/test_domain.py::test_rotate` |
| TRAP-27 | 同班次重复占批 | shift.csv | `app/modules/shifts/pool.py` | `tests/test_shifts.py::test_naive_view_exposes_double_occupation` |
| TRAP-28 | 晚到修订改变可用库存 | 测试构造输入 | `app/modules/shifts/pool.py` | `tests/test_shifts.py::test_late_revision_changes_available_inventory` |
| TRAP-29 | 冻结分配与库存冲突 | 测试构造输入 | `app/modules/shifts/allocate.py` | `tests/test_shifts.py::test_freeze_infeasible_keeps_old_version` |
| TRAP-30 | 未确认版本导出 | 测试构造输入 | `app/modules/shifts/service.py` | `tests/test_shifts.py::test_review_and_export_versions_stay_consistent` |

## 对账规则

输入记录数 = 计入 + 隔离 + 去重和替换 + 空白记录 + 重复表头。
业务账按调出单全外连接。差异分别标记漏记、外部单边和数值不符，以袋对差。

## 范围

本地文件与单机复核。单次来源文本限 128 KiB。复合字段单项最多 240 段。
