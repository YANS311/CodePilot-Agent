# CodePilot Agent 评测报告

**生成时间**: 2026-06-18 22:09:05

## 核心指标

| 指标 | 值 |
|------|-----|
| 任务成功率 (TSR) | 83.3% (25/30) |
| Pass@1 | 83.3% |
| 测试通过率 | 94.3% (83/88) |
| 工具效率 | 0.125 |
| 成功任务平均工具调用 | 8.0 |
| 平均工具调用 | 8.4 |
| 平均耗时 | 50857ms |
| 总耗时 | 1554891ms |

## 错误分布

| 错误类型 | 数量 |
|----------|------|
| test_not_executed | 3 |
| no_code_change | 2 |

## 按难度分组

| 难度 | 成功/总数 | 成功率 |
|------|-----------|--------|
| easy | 10/10 | 100% |
| medium | 11/12 | 92% |
| hard | 4/8 | 50% |

## 按类别分组

| 类别 | 成功/总数 | 成功率 |
|------|-----------|--------|
| bug-fix | 24/29 | 83% |
| enhancement | 1/1 | 100% |

## 失败任务详情

### fix-append-line: 修复 append_line 双重换行

- **难度**: medium
- **错误类型**: test_not_executed
- **错误原因**: 修改后未执行 run_tests 验证
- **工具调用**: 8

### fix-retry-request: 修复 retry_request 无延迟

- **难度**: hard
- **错误类型**: no_code_change
- **错误原因**: 声称修复但未实际调用 write_file
- **工具调用**: 9

### fix-config-all: 修复 config_parser 多个 bug

- **难度**: hard
- **错误类型**: test_not_executed
- **错误原因**: 修改后未执行 run_tests 验证
- **工具调用**: 6

### fix-file-processor-all: 修复 file_processor 多个 bug

- **难度**: hard
- **错误类型**: test_not_executed
- **错误原因**: 修改后未执行 run_tests 验证
- **工具调用**: 14

### fix-api-client-all: 修复 api_client 多个 bug

- **难度**: hard
- **错误类型**: no_code_change
- **错误原因**: 声称修复但未实际调用 write_file
- **工具调用**: 14

## 成功任务

| 任务 ID | 任务名称 | 工具调用 | 耗时 |
|---------|----------|----------|------|
| fix-subtract | 修复 subtract 算术错误 | 13 | 50198ms |
| fix-reverse-string | 修复 reverse_string off-by-one | 7 | 24549ms |
| fix-count-vowels | 修复 count_vowels off-by-one | 6 | 26306ms |
| fix-todo-list-pending | 修复 list_pending 条件反转 | 6 | 27519ms |
| fix-user-to-dict | 修复 User.to_dict 缺少字段 | 9 | 38590ms |
| fix-task-to-dict | 修复 Task.to_dict 缺少字段 | 6 | 25379ms |
| fix-import | 修复 import 错误 | 10 | 30972ms |
| fix-count-words | 修复 count_words 空行计算 | 9 | 76521ms |
| fix-capitalize-tabs | 修复 capitalize_words 只处理空格 | 8 | 69558ms |
| fix-todo-complete | 修复 TodoService.complete 未保存 | 10 | 40482ms |
| fix-divide-zero | 修复 divide 除零检查 | 7 | 28063ms |
| fix-factorial | 修复 factorial off-by-one | 9 | 32953ms |
| fix-merge-configs | 修复 merge_configs 不递归合并 | 7 | 26965ms |
| fix-get-config-value | 修复 get_config_value 默认值 | 9 | 82894ms |
| fix-replace-in-file | 修复 replace_in_file 相同参数 | 7 | 30037ms |
| fix-build-url | 修复 build_url 未编码参数 | 7 | 41197ms |
| fix-parse-response | 修复 parse_response 缺少 status | 6 | 27280ms |
| fix-list-by-priority | 修复 list_by_priority 返回 None | 7 | 27906ms |
| fix-find-longest-line | 修复 find_longest_line 多行同长 | 8 | 82797ms |
| add-validation | 添加参数类型校验 | 8 | 46929ms |
| fix-user-deactivate | 修复 User.deactivate 未记录时间 | 9 | 35504ms |
| fix-multi-file-todo | 修复 TodoService 多个 bug | 7 | 33719ms |
| fix-data-models-all | 修复 data_models 多个 bug | 8 | 36955ms |
| fix-string-utils-all | 修复 string_utils 多个 bug | 10 | 75321ms |
| fix-all-calculator | 修复 buggy_calculator 所有 bug | 7 | 37015ms |
