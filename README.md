# Human9000 Skills

Claude Code 技能（Skills）集合。每个 skill 是一个独立的功能模块。

---

## 技能列表

- **`nano-flow`** — 极简项目协同。投放问卷→验证完整性→并行生成项目文件管理体系（项目状态、个人周报、会议材料、接口约定、团队分析、管理方法）。适用：新项目启动、团队协同体系搭建。

---

## 安装

```bash
npx skills add Human9000/skills --skill <skill-name> -g
```

`-g` 全局安装，所有项目可用。不加 `-g` 仅当前项目可用。

---

## 使用

在 Claude Code 中输入 `/<skill-name>` 即可触发对应技能。

---

## 贡献

skill 遵循 [agentskills.io](https://agentskills.io) 规范：

```
skill-name/
├── SKILL.md          ← 主文件（frontmatter + 指令）
└── ...               ← 模板、工具、参考文件
```

欢迎 PR。
