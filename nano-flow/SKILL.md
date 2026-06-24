---
name: nano-flow
description: Use when the user wants to initialize a new project, set up project management, bootstrap a team workspace, or mentions "nano-flow", "极简协同", "项目管理初始化", "项目搭建". Also use to update an existing project's management system or templates.
---

# nano-flow · 极简项目协同

核心理念：**给定当前团队配置，最小动作集合是什么。** 以周为单位，Markdown 文件即真相。

---

## 初始化流程

### 第一步：投放问卷

把 `templates/nano-flow-init.md` 复制到项目根目录，告诉用户："逐段填写，填完说'填完了'。"

### 第二步：验证循环

用户说"填完了"后，逐段检查：

| 段 | 不可为空 | 可为空但会追问 | 空也可以 |
|----|---------|-------------|---------|
| 一、项目身份 | 项目名 | 一句话描述、关键优势 | — |
| 二、团队 | 成员名、角色 | 信息从哪来/到哪去、备份人 | — |
| 三、约束 | 三条红线 | 取舍测试 | — |
| 四、里程碑 | 第一个里程碑(M1) | M2-M5 | — |
| 五、关键指标 | — | 全部（但会问一句"没有量化目标吗？"） | 全部 |
| 六、补充信息 | — | — | 全部 |

**追问规则：**
- 缺失项 → 提示"XX 段 YY 字段没填，这个会影响 ZZZ 的判断。要补吗？还是先不管？"
- 矛盾项 → 提示具体矛盾（如"信息流表显示星形，但成员间有直连标注"）
- 用户说"先不管"或给了原因 → 记录原因，跳过，不再追问
- 用户补充 → 回到验证循环

### 第三步：生成

验证通过（或用户确认跳过）后，**同时启动以下 agent**：

| Agent | 做什么 | 读哪些文件 |
|-------|--------|----------|
| Agent 1 | 生成 `CLAUDE.md` | `templates/CLAUDE模板.md` |
| Agent 2 | 生成 `99-current/`（README + 4 模板） | `templates/项目状态.md` `templates/个人周报.md` `templates/周会材料.md` `templates/接口约定.md` |
| Agent 3 | 生成 `00-proj/YYMMDD.md`（填方向/里程碑/红线/团队配置/管理方法/Mermaid 图） | `templates/项目状态.md` `methodology.md` |
| Agent 4 | 生成 `10-item/{name}/` 每人初始周报 + `03-meeting/` + `01-artifacts/问题归档.md` | `templates/个人周报.md` `templates/周会材料.md` `templates/问题归档.md` |
| Agent 5 | 生成 `99-tool/`（可选） | 复制 handbook + 阶段模板 |

### 第四步：保留问卷

生成的 `nano-flow-init.md` 留在项目根目录，永久保留。下次项目变更时，直接改这个文件，重新触发 skill。

---

## 团队分析

四个变量从信息流表直接读出。完整方法论见 `methodology.md`。

| 变量 | 看哪列 | 关键动作 |
|------|--------|---------|
| 枢纽结构 | 信息从哪来/到哪去 | 全经过一人=星形→不设Sprint；直连多=网状→可设Sprint |
| 单点依赖 | 备份人 | 全无=高单点→接口约定强制执行；补备份人 |
| 注意力碎片化 | 时间 | 有兼职→信息主动推送，变更电话确认 |
| 新人比例 | 经验 | 有新人→2周学习期，不独立负责跨角色接口 |

---

## 更新已有项目

1. 读 `nano-flow-init.md` 和 `99-current/README.md`
2. 问"什么变了"
3. 只改受影响文件，不动其他
4. 更新 `nano-flow-init.md` 保持一致
