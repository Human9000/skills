---
name: smartcopy
description: 智能文件同步复制 — 基于 MD5 内容校验，先比大小后算哈希，精准复制差异文件。当用户需要同步/备份/迁移文件夹、比较两个目录差异、按内容更新文件、用 MD5 校验文件一致性时使用。
---

# SmartCopy · 智能文件同步复制

三层漏斗算法（元数据 O(n) → 大小初筛 → MD5 终验），万级文件秒级完成。纯 Python 标准库，零依赖。

## 使用方式

```bash
python scripts/smartcopy.py <SRC目录> <DST目录> [选项]
```

| 选项 | 说明 |
|------|------|
| `--log PATH` | CSV 操作日志 |
| `--yes` | 无交互模式，冲突全部覆盖 |
| `--force` | 仅依大小判断，跳过 MD5（更快） |
| `--threads N` | MD5 并行线程数（0=单线程，SSD 建议 2-4） |
| `--no-longpath` | 禁用长路径前缀 |
| `--soft-delete` | 软删除模式：DST 独有文件重命名为 `_deleted_at_<时间戳>` 后缀 |

## 三种 Case

| SRC | DST | 行为 |
|-----|-----|------|
| ✗ | ✓ | Case 1: 保留 DST（默认）或软删除标记（`--soft-delete`） |
| ✓ | ✓ | Case 2: 大小/MD5 不同 → 冲突，用户决策 |
| ✓ | ✗ | Case 3: 复制 SRC→DST，自动建父目录 |
| ✓ | ✓ | MD5 相同 → 跳过 |

## 冲突解决

```
⚠️ 发现 N 个冲突文件：

[1] 文件: \data\config.xml (SRC: 1.2KB, DST: 1.1KB)  [大小不同]
[2] 文件: \images\logo.png (SRC: 500KB, DST: 500KB)  [MD5 不同]

操作:
  数字(如 1,2) = 覆盖选中  |  a = 全部覆盖  |  s = 全部跳过  |  r = 仅覆盖大小不同的
```

## 典型用法

```bash
# 交互模式
python scripts/smartcopy.py E:\work D:\backup --log log.csv

# 自动覆盖 + 软删除
python scripts/smartcopy.py E:\work D:\backup --yes --soft-delete --log log.csv

# SSD 加速
python scripts/smartcopy.py E:\work D:\backup --yes --threads 4
```

## 约束

- 不物理删除 DST 文件（支持 `--soft-delete` 软删除标记），跳过符号链接
- 流式读取 4MB 缓冲，大文件安全
- 支持 >260 字符长路径，复制保留 mtime
