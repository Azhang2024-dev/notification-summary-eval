# 自动化评测脚本

基于规则文件对 CSV / Excel 数据集进行自动化评测，并输出格式化的 Excel 报告。

## 项目结构

```
eval_project/
├── main.py                     # 主入口
├── requirements.txt
├── core/
│   ├── data_loader.py          # 数据加载（CSV / Excel → list[dict]）
│   ├── rule_engine.py          # 规则引擎（加载 YAML 规则并执行）
│   └── evaluator.py            # 评测器（串联加载 + 引擎 + 汇总）
├── utils/
│   ├── report_writer.py        # Excel 报告输出（3 个 Sheet）
│   └── logger.py               # 统一日志
├── rules/
│   ├── default_rules.yaml      # 示例规则文件（可复制修改）
│   └── custom_score_check.py   # 自定义规则函数示例
├── data/
│   └── sample.csv              # 示例数据集
├── output/                     # 报告输出目录（自动创建）
└── logs/                       # 日志目录（自动创建）
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 运行示例评测

```bash
python main.py
```

### 3. 指定文件运行

```bash
python main.py --data data/my_dataset.xlsx --rule rules/my_rules.yaml --output output/result.xlsx
```

### 4. 查看所有参数

```bash
python main.py --help
```

## 规则文件说明

规则文件为 YAML 格式，位于 `rules/` 目录。支持以下规则类型：

| 类型 | 说明 | 必填参数 |
|------|------|----------|
| `not_empty` | 字段非空检查 | `field` |
| `regex` | 正则表达式匹配 | `field`, `pattern` |
| `length` | 字段长度范围 | `field`, `min`, `max` |
| `contains` | 包含指定关键词 | `field`, `keyword` |
| `not_contains` | 不包含指定关键词 | `field`, `keyword` |
| `custom` | 自定义 Python 函数 | `field`, `func_module` |

### 规则示例

```yaml
rules:
  - id: R001
    name: 标题非空
    type: not_empty
    field: title
    severity: error          # error（计入失败）| warning（仅提示）
    message_fail: "标题不能为空"

  - id: R002
    name: 邮箱格式
    type: regex
    field: email
    pattern: "^[\\w.+-]+@[\\w-]+\\.[\\w.-]+$"
    severity: error
```

### 自定义规则

在 `rules/` 目录下创建 `<func_module>.py`，实现 `evaluate()` 函数：

```python
def evaluate(value, record: dict, rule: dict) -> tuple[bool, str]:
    # value  : 当前字段值
    # record : 完整数据行
    # rule   : 规则配置 dict
    if ...:
        return True, "通过说明"
    return False, "失败原因"
```

在 YAML 中引用：

```yaml
- id: R009
  name: 自定义检查
  type: custom
  field: score
  func_module: my_custom_check   # 对应 rules/my_custom_check.py
  severity: error
```

## 输出报告

Excel 报告包含 3 个 Sheet：

| Sheet | 内容 |
|-------|------|
| **摘要** | 整体通过率、各规则通过率统计 |
| **明细** | 每条记录 × 每条规则的详细结果（绿色=通过，红色=失败） |
| **失败记录** | 仅包含存在 error 的记录及失败原因 |
