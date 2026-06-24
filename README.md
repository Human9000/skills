# Human9000 Skills

Claude Code 技能（Skills）集合。每个 skill 是一个独立的功能模块，可通过 `npx skills` 安装使用。

---

## 技能列表

### nano-flow · 极简项目协同

> 给定当前团队配置，最小动作集合是什么？

一键初始化完整的项目文件管理体系。投放问卷 → 验证完整性 → 并行生成所有文件（项目状态、个人周报、会议材料、接口约定、团队分析、管理方法）。

**适用：** 新项目启动、团队协同体系搭建、项目管理系统重建

**安装：**

```bash
npx skills add Human9000/skills --skill nano-flow -g
```

**使用：**

```
/nano-flow
```

---

## 安装单个 skill

```bash
npx skills add Human9000/skills --skill <skill-name> -g
```

`-g` 全局安装，所有项目可用。不加 `-g` 仅当前项目可用。

---

## 技能结构规范

本仓库中的 skill 遵循 [agentskills.io](https://agentskills.io) 规范：

```
skill-name/
├── SKILL.md          ← 主文件（frontmatter + 指令）
└── ...               ← 模板、工具、参考文件
```

欢迎 PR 贡献新的 skill。
