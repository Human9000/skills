# Human9000 Skills

Claude Code 技能（Skills）集合。每个 skill 是一个独立的功能模块。

---

## 技能列表

- **`smartcopy`** — 智能文件同步复制
  - 基于 MD5 内容校验，先比大小后算哈希，精准复制差异文件
  - 三层漏斗算法（元数据 O(n) → 大小初筛 → MD5 终验），万级文件秒级完成
  - 纯 Python 标准库，零依赖，免安装运行
  - 支持 >260 字符长路径、大文件流式读取、CSV 操作日志
  - 适用：文件夹备份、目录同步、文件迁移、内容级去重
- **`nano-flow`** — 极简项目协同
  - 投放问卷，一次性收集项目信息，无需多轮对话
  - 自动验证完整性，识别缺失和矛盾，提示补全
  - 并行生成完整项目文件管理体系
  - 产出的文件包括：项目状态、个人周报、会议材料、接口约定、团队配置分析、管理方法
  - 生成的 `nano-flow-init.md` 永久保留在项目中，作为项目配置的真实来源
  - 适用：新项目启动、团队协同体系搭建

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
