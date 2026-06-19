# CodePilot Agent 评测报告

**生成时间**: 2026-06-19 14:27:46
**版本**: D11.6 — Reliability-Aware Budget Guardrail

## 三方对比 (D11 → D11.5 → D11.6)

| 指标 | D11 Baseline | D11.5 | D11.6 | 趋势 |
|------|-------------|-------|-------|------|
| **TSR** | 90.0% (27/30) | 86.7% (26/30) | **90.0% (27/30)** | ↑ 恢复 |
| Test Pass Rate | — | 95.5% (84/88) | **96.6% (85/88)** | ↑ +1.1% |
| Pass@1 | 90.0% | 86.7% | **90.0%** | ↑ 恢复 |
| Tool Efficiency | — | 0.150 | 0.144 | ↓ -4% |
| Tool Calls/Success | 8.4 | 6.7 | 6.9 | ↑ +0.2 |
| **Avg Tool Calls** | 8.4 | 6.5 | **7.0** | ↑ 仍优于基线 |
| **Avg Duration** | — | 40669ms | **32517ms** | ↓ -20% |

### 关键结论

1. **TSR 恢复**: D11.6 修复了 D11.5 的回归，TSR 从 86.7% 恢复到 90.0%
2. **效率保持**: Avg Tool Calls 7.0 仍优于 D11 基线 8.4（-17%）
3. **速度提升**: Avg Duration 32517ms 比 D11.5 快 20%
4. **fix-list-by-priority 修复**: D11.5 失败的 fix-list-by-priority 在 D11.6 中通过

### 核心改动

| 改动 | D11.5 | D11.6 |
|------|-------|-------|
| Budget Policy | 禁止 read_file（≤3次） | 允许 read_file（未读目标） |
| Completion Guardrail | 无 | write_file + run_tests 校验 |
| No-Code-Change Detector | 无 | 检测无 write_file 的完成声明 |

## 核心指标

| 指标 | 值 |
|------|-----|
| 任务成功率 (TSR) | 90.0% (27/30) |
| Pass@1 | 90.0% |
| 测试通过率 | 96.6% (85/88) |
| 工具效率 | 0.144 |
| 成功任务平均工具调用 | 6.9 |
| 平均工具调用 | 7.0 |
| 平均耗时 | 32517ms |
| 总耗时 | 1027842ms |

## 错误分布

| 错误类型 | 数量 |
|----------|------|
| test_not_executed | 2 |
| no_code_change | 1 |

## 按难度分组

| 难度 | 成功/总数 | 成功率 |
|------|-----------|--------|
| easy | 10/10 | 100% |
| medium | 11/12 | 92% |
| hard | 6/8 | 75% |

## 按类别分组

| 类别 | 成功/总数 | 成功率 |
|------|-----------|--------|
| bug-fix | 26/29 | 90% |
| enhancement | 1/1 | 100% |

## 失败任务详情

### fix-append-line: 修复 append_line 双重换行

- **难度**: medium
- **错误类型**: test_not_executed
- **错误原因**: 修改后未执行 run_tests 验证
- **工具调用**: 6

### fix-retry-request: 修复 retry_request 无延迟

- **难度**: hard
- **错误类型**: no_code_change
- **错误原因**: 声称修复但未实际调用 write_file
- **工具调用**: 8

### fix-file-processor-all: 修复 file_processor 多个 bug

- **难度**: hard
- **错误类型**: test_not_executed
- **错误原因**: 修改后未执行 run_tests 验证
- **工具调用**: 9

## 成功任务

| 任务 ID | 任务名称 | 工具调用 | 耗时 |
|---------|----------|----------|------|
| fix-subtract | 修复 subtract 算术错误 | 7 | 19155ms |
| fix-reverse-string | 修复 reverse_string off-by-one | 6 | 16921ms |
| fix-count-vowels | 修复 count_vowels off-by-one | 6 | 16390ms |
| fix-todo-list-pending | 修复 list_pending 条件反转 | 8 | 30780ms |
| fix-user-to-dict | 修复 User.to_dict 缺少字段 | 8 | 25891ms |
| fix-task-to-dict | 修复 Task.to_dict 缺少字段 | 8 | 20328ms |
| fix-import | 修复 import 错误 | 7 | 16532ms |
| fix-count-words | 修复 count_words 空行计算 | 4 | 26015ms |
| fix-capitalize-tabs | 修复 capitalize_words 只处理空格 | 7 | 25516ms |
| fix-todo-complete | 修复 TodoService.complete 未保存 | 8 | 25875ms |
| fix-divide-zero | 修复 divide 除零检查 | 4 | 14344ms |
| fix-factorial | 修复 factorial off-by-one | 6 | 17530ms |
| fix-merge-configs | 修复 merge_configs 不递归合并 | 4 | 17639ms |
| fix-get-config-value | 修复 get_config_value 默认值 | 9 | 59015ms |
| fix-replace-in-file | 修复 replace_in_file 相同参数 | 6 | 18530ms |
| fix-build-url | 修复 build_url 未编码参数 | 6 | 17063ms |
| fix-parse-response | 修复 parse_response 缺少 status | 7 | 20702ms |
| fix-list-by-priority | 修复 list_by_priority 返回 None | 10 | 32030ms |
| fix-find-longest-line | 修复 find_longest_line 多行同长 | 4 | 46061ms |
| add-validation | 添加参数类型校验 | 4 | 21592ms |
| fix-user-deactivate | 修复 User.deactivate 未记录时间 | 8 | 24172ms |
| fix-multi-file-todo | 修复 TodoService 多个 bug | 6 | 18734ms |
| fix-config-all | 修复 config_parser 多个 bug | 7 | 47171ms |
| fix-data-models-all | 修复 data_models 多个 bug | 11 | 25641ms |
| fix-string-utils-all | 修复 string_utils 多个 bug | 11 | 104139ms |
| fix-api-client-all | 修复 api_client 多个 bug | 7 | 29219ms |
| fix-all-calculator | 修复 buggy_calculator 所有 bug | 8 | 24484ms |
