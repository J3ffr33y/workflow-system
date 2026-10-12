# 功能测试表

`functional-test-checklist.xlsx` 是手工验收用的测试表：逐项测试当前系统的功能，每一项都写明老系统（new-system-doc 第一部分）的要求，作为最低标准。

- **说明** 页：怎么用、测试前准备、"对照"一列的含义。
- **汇总** 页：按模块自动统计已测、通过、不通过、通过率。
- **测试用例** 页：编号、前置条件、操作步骤、预期结果、老系统要求、对照、测试结果（下拉）、问题/备注。

## 修改用例

用例写在 `cases.py`，表格由 `build.py` 生成，这样每次增删用例在 git 里都能看到具体改了哪一行：

```bash
cd docs/testing
pip install openpyxl
python build.py functional-test-checklist.xlsx
```

已经填了测试结果的表格不要覆盖，另存一份（例如 `functional-test-checklist-2026-10-20.xlsx`）再填。
