# 种粮库轮换

面向种粮库保管员。按入库有效期优先挑批并保留每批法定留样，按整袋数量分配并单列未满足量。复算后按调出单核对独立清单，查看单据证据和差值，再登记复核结论。

## 启动

```sh
docker compose up --build
```

默认访问 http://localhost:18285。
打开工作台，点击运行即可使用内置的班次样例。选择导入可以换成自己的来源与独立账 CSV。
样例在 `sample_data/`，`shift.csv` 有分页表头、冲突修订、坏行、空值哨兵与业务拒绝，`external.csv` 有单边与数值差异。
端口可通过 `APP_PORT` 覆盖。运行记录和复核历史保存在 `ledger` 卷。

## 操作

- 在留样配给展开业务证据，核对原始字段与计算项。
- 在隔离裁决逐行检查原因。独立对账按键对比外部账并列出差值。
- 在批次复算重跑当前输入。在交付复核提交带版本意见，并导出证据包。

## 验证

```sh
docker compose config --quiet
docker compose exec -T app pytest -q
```

- [字段定义](docs/DATA-DICTIONARY.md)
- [模块规则和测试](docs/DEPTH.md)
- 接口文档位于 `/docs`。
