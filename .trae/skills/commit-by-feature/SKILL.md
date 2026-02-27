---
name: commit-by-feature
description: Group code changes by feature or bugfix and create separate commits. Use when user mentions忘记commit、按功能提交、拆分提交或提交太大。
allowed-tools: Read, Grep, Glob, RunCommand
---

# Commit by Feature

## Quick Start
1. 收集改动清单与差异
2. 按功能或缺陷归类文件与片段
3. 生成分组提交计划并逐组提交

## Instructions
1. 获取改动范围与上下文（状态、变更文件、关键 diff）
2. 识别功能边界与模块归属，形成分组
3. 输出分组清单与每组包含的文件/片段
4. 逐组执行暂存与提交，提交信息聚焦该功能
5. 提交前提示用户确认

## Examples
- “我忘记commit了，帮我按功能拆分提交”
- “这次修了多个bug，想分开commit”
- “改动太大了，帮我按模块拆分提交”

## Edge Cases
- 同一文件跨多个功能修改时，优先按块拆分并请求用户确认分组
- 无法明确分组时，先给出建议分组并询问用户选择

## Constraints
- 未经用户明确同意不得执行 commit
- 不自动合并或改写历史提交
- 不混合无关功能到同一提交

## Validation Checklist
- [ ] 分组规则清晰且互斥
- [ ] 每组包含的文件/片段明确
- [ ] 提交信息与功能一致
- [ ] 提交前已获得用户确认
