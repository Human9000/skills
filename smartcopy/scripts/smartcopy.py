#!/usr/bin/env python3
"""
SmartCopy - 智能文件同步复制工具
基于 MD5 内容校验，二级筛选（大小→哈希），精准复制差异文件。
纯 Python 标准库，零第三方依赖。
"""

import os
import sys
import hashlib
import argparse
import shutil
import csv
import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

BUFFER_SIZE = 4 * 1024 * 1024  # 4MB
SOFT_DELETE_RE = re.compile(r"_deleted_at_\d{8}_\d{6}$")
SOFT_DELETE_TS_RE = re.compile(r"_deleted_at_(\d{8}_\d{6})$")


def to_long_path(path):
    """将路径转为 Windows 长路径格式以支持 >260 字符路径。"""
    if sys.platform != "win32":
        return path
    abs_path = os.path.abspath(path)
    if abs_path.startswith("\\\\?\\"):
        return abs_path
    return "\\\\?\\" + abs_path


def format_size(size_bytes):
    """人类可读的文件大小。"""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f}MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f}GB"


def is_soft_deleted(rel_path):
    """判断文件路径是否已携带软删除标记（_deleted_at_时间戳）。"""
    return bool(SOFT_DELETE_RE.search(rel_path))


def extract_soft_delete_ts(rel_path):
    """从软删除文件路径中提取原始删除时间戳；若未匹配则返回 None。"""
    m = SOFT_DELETE_TS_RE.search(rel_path)
    return m.group(1) if m else None


def soft_delete_rename(full_path):
    """
    将文件重命名为 原路径_deleted_at_<当前时间戳>。
    若文件已存在软删除后缀则跳过，返回 None。
    返回新路径，失败抛 OSError。
    """
    if SOFT_DELETE_RE.search(full_path):
        return None
    ts = time.strftime("%Y%m%d_%H%M%S")
    new_path = full_path + f"_deleted_at_{ts}"
    os.rename(full_path, new_path)
    return new_path


def undo_soft_delete(full_path):
    """
    还原被软删除的文件：去掉 _deleted_at_<时间戳> 后缀。
    若文件未携带软删除标记则返回 None。
    若还原后目标已存在则抛出 FileExistsError。
    返回还原后的路径。
    """
    if not SOFT_DELETE_RE.search(full_path):
        return None
    original_path = SOFT_DELETE_RE.sub("", full_path)
    if not os.path.exists(full_path):
        raise FileNotFoundError(f"软删除文件不存在: {full_path}")
    if os.path.exists(original_path):
        raise FileExistsError(f"目标已存在: {original_path}")
    os.rename(full_path, original_path)
    return original_path


def scan_undo_candidates(directory):
    """
    扫描目录中所有可还原的软删除文件。
    返回 [{"deleted_rel": ..., "original_rel": ..., "deleted_path": ..., "timestamp": ...}, ...]
    """
    candidates = []
    directory = os.path.abspath(directory)
    walk_root = to_long_path(directory)
    for dirpath, dirnames, filenames in os.walk(walk_root, followlinks=False):
        # 扫描文件
        for fname in filenames:
            if not SOFT_DELETE_RE.search(fname):
                continue
            full_path = os.path.join(dirpath, fname)
            try:
                if not os.path.isfile(full_path):
                    continue
            except OSError:
                continue
            try:
                rel = os.path.relpath(full_path, walk_root)
            except (ValueError, OSError):
                rel = fname
            original_rel = SOFT_DELETE_RE.sub("", rel)
            ts = extract_soft_delete_ts(rel) or ""
            candidates.append({
                "deleted_rel": rel,
                "original_rel": original_rel,
                "deleted_path": full_path,
                "timestamp": ts,
                "type": "file",
            })
        # 扫描目录
        for dname in list(dirnames):
            if not SOFT_DELETE_RE.search(dname):
                continue
            full_path = os.path.join(dirpath, dname)
            try:
                if not os.path.isdir(full_path):
                    continue
            except OSError:
                continue
            try:
                rel = os.path.relpath(full_path, walk_root)
            except (ValueError, OSError):
                rel = dname
            original_rel = SOFT_DELETE_RE.sub("", rel)
            ts = extract_soft_delete_ts(rel) or ""
            candidates.append({
                "deleted_rel": rel,
                "original_rel": original_rel,
                "deleted_path": full_path,
                "timestamp": ts,
                "type": "dir",
            })
    return candidates


def undo_all(directory, force=False, subdir=None):
    """
    还原目录中所有软删除文件和目录。
    force=True 时覆盖已存在的目标。
    subdir 指定子目录时，仅还原该子目录下的。
    目录优先还原（外层先行），再还原文件。
    返回 {"restored": N, "skipped": N, "errors": N}
    """
    candidates = scan_undo_candidates(directory)
    if subdir:
        subdir = subdir.replace("\\", "/").strip("/")
        candidates = [c for c in candidates
                      if c["original_rel"].replace("\\", "/").startswith(subdir + "/")
                      or c["original_rel"].replace("\\", "/") == subdir]
    # 目录优先、外层优先，再文件
    dirs = sorted([c for c in candidates if c["type"] == "dir"],
                  key=lambda x: x["original_rel"].count(os.sep))
    files = [c for c in candidates if c["type"] == "file"]
    ordered = dirs + files
    restored = 0
    skipped = 0
    errors = 0
    for c in ordered:
        original_path = os.path.join(os.path.dirname(c["deleted_path"]),
                                     os.path.basename(c["original_rel"]))
        try:
            if os.path.exists(original_path):
                if force:
                    if os.path.isdir(original_path):
                        shutil.rmtree(original_path)
                    else:
                        os.remove(original_path)
                else:
                    skipped += 1
                    continue
            os.rename(c["deleted_path"], original_path)
            restored += 1
        except OSError:
            errors += 1
    return {"restored": restored, "skipped": skipped, "errors": errors}


def walk_files(directory):
    """
    递归遍历目录，返回 {相对路径: 文件大小(字节)}。
    仅处理常规文件，跳过符号链接。
    捕获权限错误，将失败项加入错误列表返回。
    """
    size_map = {}
    errors = []
    directory = os.path.abspath(directory)
    walk_root = to_long_path(directory)

    for dirpath, dirnames, filenames in os.walk(walk_root, followlinks=False):
        for fname in filenames:
            full_path = os.path.join(dirpath, fname)
            try:
                if not os.path.isfile(full_path):
                    continue
                if os.path.islink(full_path):
                    continue
                st = os.stat(full_path)
                size = st.st_size
            except (PermissionError, OSError) as e:
                try:
                    rel = os.path.relpath(full_path, walk_root)
                except (ValueError, OSError):
                    rel = fname
                errors.append({"path": rel, "error": str(e), "type": "scan"})
                continue

            try:
                rel_path = os.path.relpath(full_path, walk_root)
            except (ValueError, OSError):
                rel_path = fname

            size_map[rel_path] = size

    return size_map, errors


def walk_dirs(directory):
    """
    递归遍历目录，返回 DST 目录的相对路径集合。
    跳过已软删除的目录名。
    """
    dirs_set = set()
    directory = os.path.abspath(directory)
    walk_root = to_long_path(directory)

    for dirpath, dirnames, filenames in os.walk(walk_root, followlinks=False):
        for dname in dirnames:
            if is_soft_deleted(dname):
                continue
            full_path = os.path.join(dirpath, dname)
            try:
                if os.path.islink(full_path):
                    continue
                rel_path = os.path.relpath(full_path, walk_root)
                dirs_set.add(rel_path)
            except (ValueError, OSError):
                pass
    return dirs_set


def calc_md5(filepath, long_path=True):
    """
    流式计算文件 MD5（4MB 缓冲），禁止全量读入内存。
    返回 32 字符十六进制摘要字符串。
    """
    path = to_long_path(filepath) if long_path else filepath
    hasher = hashlib.md5()
    try:
        with open(path, "rb", buffering=BUFFER_SIZE) as f:
            while True:
                chunk = f.read(BUFFER_SIZE)
                if not chunk:
                    break
                hasher.update(chunk)
    except OSError:
        raise
    return hasher.hexdigest()


def compute_md5_for_common(common_paths, src_dir, dst_dir, src_map, progress_callback=None):
    """
    对共同存在的文件列表进行大小初筛 + MD5 终验。
    返回: (conflict_list, skip_count)
    - conflict_list: [{"path": ..., "reason": "size_diff"|"hash_diff", ...}]
    - skip_count: MD5 一致跳过数量
    """
    conflicts = []
    skipped = 0
    total = len(common_paths)
    done = 0

    for rel_path in common_paths:
        src_size = src_map[rel_path]  #  size from src map (might not exist)

        # 需要获取 dst size
        dst_full = os.path.join(dst_dir, rel_path)
        try:
            dst_st = os.stat(dst_full)
            dst_size = dst_st.st_size
        except OSError as e:
            conflicts.append({
                "path": rel_path,
                "reason": "error",
                "src_size": src_size,
                "dst_size": 0,
                "detail": f"DST 无法访问: {e}"
            })
            done += 1
            if progress_callback:
                progress_callback(done, total)
            continue

        # 第二层：大小初筛
        if src_size != dst_size:
            conflicts.append({
                "path": rel_path,
                "reason": "size_diff",
                "src_size": src_size,
                "dst_size": dst_size,
            })
            done += 1
            if progress_callback:
                progress_callback(done, total)
            continue

        # 第三层：MD5 精准校验
        src_full = os.path.join(src_dir, rel_path)
        try:
            md5_src = calc_md5(src_full)
            md5_dst = calc_md5(dst_full)
        except (PermissionError, OSError) as e:
            conflicts.append({
                "path": rel_path,
                "reason": "error",
                "src_size": src_size,
                "dst_size": dst_size,
                "detail": f"MD5 计算失败: {e}"
            })
            done += 1
            if progress_callback:
                progress_callback(done, total)
            continue

        if md5_src != md5_dst:
            conflicts.append({
                "path": rel_path,
                "reason": "hash_diff",
                "src_size": src_size,
                "dst_size": dst_size,
                "src_md5": md5_src,
                "dst_md5": md5_dst,
            })
        else:
            skipped += 1

        done += 1
        if progress_callback:
            progress_callback(done, total)

    return conflicts, skipped


def copy_file_safe(src, dst):
    """安全复制文件，保留 mtime，自动创建父目录。"""
    dst_dir = os.path.dirname(dst)
    if dst_dir:
        os.makedirs(dst_dir, exist_ok=True)
    shutil.copy2(src, dst, follow_symlinks=False)


def print_progress(done, total):
    """打印进度条。"""
    bar_len = 30
    filled = int(bar_len * done / total) if total > 0 else bar_len
    bar = "█" * filled + "░" * (bar_len - filled)
    pct = int(done / total * 100) if total > 0 else 100
    sys.stdout.write(f"\r      进度: [{bar}] {pct}% (已处理 {done}/{total} 个文件)")
    sys.stdout.flush()


def resolve_conflicts_interactive(conflicts):
    """
    交互式冲突解决。
    返回用户决定列表: [{"index": int, "action": "overwrite"|"skip"}]
    """
    if not conflicts:
        print("✅ 无冲突文件。")
        return []

    print(f"\n⚠️ 发现 {len(conflicts)} 个冲突文件：\n")

    for i, c in enumerate(conflicts, 1):
        if c["reason"] == "size_diff":
            tag = "大小不同"
            detail = f"SRC: {format_size(c['src_size'])}, DST: {format_size(c['dst_size'])}"
        elif c["reason"] == "hash_diff":
            tag = "MD5 不同"
            detail = f"SRC: {format_size(c['src_size'])}, DST: {format_size(c['dst_size'])}"
        else:
            tag = "错误"
            detail = c.get("detail", "未知错误")
        print(f"  [{i}] 文件: {c['path']}")
        print(f"      {detail}  [{tag}]\n")

    print("请选择操作:")
    print("  - 输入数字(用逗号分隔，如 1,2,4)：覆盖选中的文件")
    print("  - 输入 'a'：全部覆盖 (覆盖所有冲突)")
    print("  - 输入 's'：全部跳过 (保留所有目标文件)")
    print("  - 输入 'r'：仅覆盖大小不同的文件")

    while True:
        try:
            choice = input("\n> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n操作中断，默认全部跳过。")
            return [{"index": i + 1, "action": "skip"} for i in range(len(conflicts))]

        if choice == "a":
            return [{"index": i + 1, "action": "overwrite"} for i in range(len(conflicts))]
        elif choice == "s":
            return [{"index": i + 1, "action": "skip"} for i in range(len(conflicts))]
        elif choice == "r":
            return [
                {"index": i + 1, "action": "overwrite" if c["reason"] == "size_diff" else "skip"}
                for i, c in enumerate(conflicts)
            ]
        else:
            try:
                selected = [int(x.strip()) for x in choice.split(",") if x.strip()]
                invalid = [n for n in selected if n < 1 or n > len(conflicts)]
                if invalid:
                    print(f"编号 {invalid} 超出范围 (1-{len(conflicts)})，请重新输入。")
                    continue
                return [{"index": i + 1, "action": "overwrite" if (i + 1) in selected else "skip"}
                        for i in range(len(conflicts))]
            except ValueError:
                print("输入无效，请重新输入。")
                continue


def log_result(log_entries, log_path):
    """将操作日志写入 CSV 文件。"""
    fieldnames = ["action", "rel_path", "src_size", "dst_size", "detail"]
    with open(log_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for entry in log_entries:
            writer.writerow({
                "action": entry.get("action", ""),
                "rel_path": entry.get("path", ""),
                "src_size": entry.get("src_size", ""),
                "dst_size": entry.get("dst_size", ""),
                "detail": entry.get("detail", ""),
            })


def main():
    parser = argparse.ArgumentParser(
        description="SmartCopy - 智能文件同步复制工具 (基于 MD5 校验)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python smartcopy.py E:\\work D:\\backup
  python smartcopy.py E:\\work D:\\backup --log copy_log.csv
  python smartcopy.py E:\\work D:\\backup --yes           (自动全部覆盖，无交互)
  python smartcopy.py E:\\work D:\\backup --force          (跳过校验，直接复制所有差异)
  python smartcopy.py E:\\work D:\\backup --soft-delete    (DST 独有文件重命名标记，不直接保留)
  python smartcopy.py D:\\backup --undo-soft-delete          (还原目标目录中被软删除的文件)
  python smartcopy.py E:\\work D:\\backup --reverse           (反向: 从 DST 同步到 SRC)
        """,
    )
    parser.add_argument("src", help="源目录路径 (--undo-soft-delete 模式下为要还原的目录)")
    parser.add_argument("dst", nargs="?", default=None,
                        help="目标目录路径 (--undo-soft-delete 模式下无需指定)")
    parser.add_argument("--log", default=None, help="操作日志输出路径 (CSV)")
    parser.add_argument("--yes", action="store_true", help="无交互模式：有冲突时自动全部覆盖")
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制模式：跳过 MD5 校验，仅依大小判断（大小不同即覆盖，更快但不如 MD5 精准）",
    )
    parser.add_argument(
        "--undo-soft-delete", action="store_true",
        help="还原模式：扫描目标目录中被软删除的文件（_deleted_at_ 后缀），还原为原始文件",
    )
    parser.add_argument(
        "--reverse", action="store_true",
        help="反向同步模式：交换 SRC 和 DST 角色，从目标目录同步到源目录",
    )
    parser.add_argument(
        "--threads", type=int, default=0,
        help="MD5 计算线程数 (默认 0=单线程，SSD 建议 2-4)",
    )
    parser.add_argument(
        "--no-longpath", action="store_true",
        help="禁用 \\\\?\\ 长路径前缀 (非 Windows 平台自动禁用)",
    )
    parser.add_argument(
        "--soft-delete", action="store_true",
        help="软删除模式：Case 1 文件（DST 独有）重命名为 _deleted_at_<时间戳> 后缀，而非直接保留",
    )
    args = parser.parse_args()

    # -- 处理 --undo-soft-delete 模式（独立操作，不走同步流程） --
    if args.undo_soft_delete:
        if not os.path.isdir(args.src):
            print(f"错误: 目录不存在: {args.src}")
            sys.exit(1)
        print(f"SmartCopy v1.0")
        print(f"  模式: 还原软删除文件")
        print(f"  目录: {os.path.abspath(args.src)}")
        print()
        candidates = scan_undo_candidates(args.src)
        if not candidates:
            print("未发现可还原的软删除文件。")
            sys.exit(0)
        print(f"发现 {len(candidates)} 个可还原文件:")
        for c in candidates:
            print(f"  {c['deleted_rel']}")
            print(f"    → {c['original_rel']}  (删除于 {c['timestamp']})")
        print()
        if not args.yes:
            try:
                confirm = input("确认还原以上全部文件? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n操作已取消。")
                sys.exit(0)
            if confirm != "y":
                print("操作已取消。")
                sys.exit(0)
        result = undo_all(args.src, force=args.yes)
        print(f"\n还原完成: {result['restored']} 个, 跳过: {result['skipped']} 个, 错误: {result['errors']} 个")
        if result["errors"] > 0:
            sys.exit(2)
        sys.exit(0)

    src_dir = os.path.abspath(args.src)
    dst_dir = os.path.abspath(args.dst)
    use_longpath = sys.platform == "win32" and not args.no_longpath

    if dst_dir is None:
        print("错误: 需要指定目标目录，或使用 --undo-soft-delete 模式。")
        sys.exit(1)
    if not os.path.isdir(src_dir):
        print(f"错误: 源目录不存在: {src_dir}")
        sys.exit(1)
    if not os.path.isdir(dst_dir):
        print(f"错误: 目标目录不存在: {dst_dir}")
        sys.exit(1)

    # -- 处理 --reverse 模式（交换 SRC ↔ DST） --
    if args.reverse:
        src_dir, dst_dir = dst_dir, src_dir
        print(f"SmartCopy v1.0")
        print(f"  模式: 反向同步 (DST → SRC)")
    else:
        print(f"SmartCopy v1.0")
    print(f"  源目录: {src_dir}")
    print(f"  目标目录: {dst_dir}")
    if args.force:
        print(f"  模式: 强制模式 (仅大小判断，跳过 MD5)")
    if args.soft_delete:
        print(f"  模式: 软删除模式 (Case 1 文件将重命名标记而非保留)")
    print()

    # [1/3] 扫描源目录
    print("[1/3] 正在扫描源目录...", end="", flush=True)
    t_start = time.time()
    src_map, src_errors = walk_files(src_dir)
    t1 = time.time()
    print(f" 找到 {len(src_map)} 个文件 ({t1 - t_start:.2f}s)")
    for e in src_errors:
        print(f"      ⚠ 跳过: {e['path']} ({e['error']})")

    # [2/3] 扫描目标目录
    print("[2/3] 正在扫描目标目录...", end="", flush=True)
    dst_map, dst_errors = walk_files(dst_dir)
    t2 = time.time()
    print(f" 找到 {len(dst_map)} 个文件 ({t2 - t1:.2f}s)")
    for e in dst_errors:
        print(f"      ⚠ 跳过: {e['path']} ({e['error']})")

    # 从 dst_map 中剥离已软删除的文件，使其不参与比对
    already_soft_deleted = {}
    for rel_path in list(dst_map.keys()):
        if is_soft_deleted(rel_path):
            already_soft_deleted[rel_path] = dst_map.pop(rel_path)
    already_soft_deleted_count = len(already_soft_deleted)

    if already_soft_deleted_count > 0:
        print(f"      ℹ 已软删除文件 (跳过比对): {already_soft_deleted_count} 个")

    # 扫描 DST 目录，计算仅 DST 有的目录
    dst_dirs = walk_dirs(dst_dir)
    src_dirs = walk_dirs(src_dir)
    only_in_dst_dirs = dst_dirs - src_dirs
    soft_delete_dir_count = 0

    # 分类（O(n) 集合运算，无双重循环）
    only_in_src = set(src_map.keys()) - set(dst_map.keys())   # Case 3: 仅 SRC 有 → 复制
    only_in_dst = set(dst_map.keys()) - set(src_map.keys())   # Case 1: 仅 DST 有
    common = set(src_map.keys()) & set(dst_map.keys())         # 待比对

    print(f"\n  仅 SRC 有 (Case 3, 直接复制): {len(only_in_src)} 个")
    print(f"  仅 DST 有 (Case 1):            {len(only_in_dst)} 个")
    if only_in_dst_dirs:
        print(f"  仅 DST 有目录 (Case 1):         {len(only_in_dst_dirs)} 个")
    print(f"  双方共存 (待比对):            {len(common)} 个")

    # [3/3] 比对
    if args.force:
        print("[3/3] 正在比对文件大小...")
    else:
        print("[3/3] 正在比对文件大小并进行 MD5 校验...")
    print(f"      快速比对 {len(common)} 个共同文件...")

    conflicts, skipped = compute_md5_for_common(
        common, src_dir, dst_dir, src_map,
        progress_callback=print_progress if not args.force else None,
    )

    if args.force:
        # 强制模式：所有 size 不同的归为冲突 (已经通过 compute_md5_for_common 处理)
        # 但 force 模式下不需要 MD5，重做简化比对
        conflicts_fast = []
        for rel_path in common:
            src_size = src_map[rel_path]
            try:
                dst_st = os.stat(os.path.join(dst_dir, rel_path))
                dst_size = dst_st.st_size
            except OSError:
                continue
            if src_size != dst_size:
                conflicts_fast.append({
                    "path": rel_path,
                    "reason": "size_diff",
                    "src_size": src_size,
                    "dst_size": dst_size,
                })
        conflicts = conflicts_fast
        skipped = len(common) - len(conflicts)

    t3 = time.time()

    case1_label = "软删除" if args.soft_delete else "保留"
    print(f"\n      完成! ({t3 - t2:.2f}s)")
    print(f"\n  结果汇总:")
    print(f"    - Case 3 (仅 SRC 有, 将复制): {len(only_in_src)} 个")
    print(f"    - Case 1 (仅 DST 有, {case1_label}):   {len(only_in_dst)} 个")
    print(f"    - MD5 一致 (跳过):            {skipped} 个")
    print(f"    - 冲突 (Case 2):              {len(conflicts)} 个")

    # 冲突解决
    if args.yes:
        decisions = [{"index": i + 1, "action": "overwrite"} for i in range(len(conflicts))]
    else:
        decisions = resolve_conflicts_interactive(conflicts)

    # 构建决策查找表
    decision_map = {d["index"]: d["action"] for d in decisions}

    # 执行操作
    log_entries = []
    copy_count = 0
    soft_delete_count = 0
    error_count = 0

    # Case 3: 复制仅 SRC 有的文件
    for rel_path in sorted(only_in_src):
        src_full = os.path.join(src_dir, rel_path)
        dst_full = os.path.join(dst_dir, rel_path)
        try:
            copy_file_safe(src_full, dst_full)
            copy_count += 1
            log_entries.append({
                "action": "copy",
                "path": rel_path,
                "src_size": src_map.get(rel_path, 0),
                "detail": "Case 3: SRC 独有，已复制",
            })
        except (PermissionError, OSError, shutil.Error) as e:
            error_count += 1
            log_entries.append({
                "action": "error",
                "path": rel_path,
                "detail": f"Case 3 复制失败: {e}",
            })
            print(f"  ✗ 复制失败: {rel_path} ({e})")

    # Case 2: 冲突处理
    for i, c in enumerate(conflicts, 1):
        action = decision_map.get(i, "skip")
        rel_path = c["path"]

        if action == "overwrite":
            src_full = os.path.join(src_dir, rel_path)
            dst_full = os.path.join(dst_dir, rel_path)
            try:
                copy_file_safe(src_full, dst_full)
                copy_count += 1
                log_entries.append({
                    "action": "overwrite",
                    "path": rel_path,
                    "src_size": c.get("src_size", 0),
                    "dst_size": c.get("dst_size", 0),
                    "detail": f"Case 2 ({c['reason']}): SRC 覆盖 DST",
                })
            except (PermissionError, OSError, shutil.Error) as e:
                error_count += 1
                log_entries.append({
                    "action": "error",
                    "path": rel_path,
                    "detail": f"Case 2 覆盖失败: {e}",
                })
                print(f"  ✗ 覆盖失败: {rel_path} ({e})")
        else:
            log_entries.append({
                "action": "skip",
                "path": rel_path,
                "src_size": c.get("src_size", 0),
                "dst_size": c.get("dst_size", 0),
                "detail": f"Case 2 ({c['reason']}): 用户选择保留 DST",
            })

    # Case 1: 目录优先软删除（目录涵盖其下所有文件，避免逐文件标记）
    if args.soft_delete and only_in_dst_dirs:
        # 仅保留顶层目录（剔除子目录：父目录已软删除则子目录自动涵盖）
        top_dirs = []
        for d in sorted(only_in_dst_dirs, key=lambda x: x.count(os.sep)):
            d_norm = d.replace("\\", "/")
            if not any(d_norm.startswith(p + "/") for p in top_dirs):
                top_dirs.append(d_norm)
        for d_norm in sorted(top_dirs, key=lambda x: x.count("/")):
            rel_dir = d_norm.replace("/", os.sep)
            dst_full = os.path.join(dst_dir, rel_dir)
            try:
                new_path = soft_delete_rename(dst_full)
                if new_path:
                    soft_delete_dir_count += 1
                    new_rel = os.path.relpath(new_path, dst_dir)
                    log_entries.append({
                        "action": "soft_delete_dir",
                        "path": rel_dir,
                        "dst_size": 0,
                        "detail": f"Case 1 目录: 已软删除 → {new_rel}",
                    })
                    # 从 only_in_dst 中移除该目录下的所有文件（目录已标记，无需逐文件标记）
                    prefix = rel_dir + os.sep
                    only_in_dst = {p for p in only_in_dst
                                   if not (p == prefix or p.startswith(prefix))}
            except (PermissionError, OSError) as e:
                error_count += 1
                log_entries.append({
                    "action": "error",
                    "path": rel_dir,
                    "detail": f"Case 1 目录软删除失败: {e}",
                })
                print(f"  ✗ 目录软删除失败: {rel_dir} ({e})")

    # Case 1: 仅 DST 有的文件
    if args.soft_delete:
        for rel_path in sorted(only_in_dst):
            dst_full = os.path.join(dst_dir, rel_path)
            try:
                new_path = soft_delete_rename(dst_full)
                if new_path:
                    soft_delete_count += 1
                    new_rel = os.path.relpath(new_path, dst_dir)
                    log_entries.append({
                        "action": "soft_delete",
                        "path": rel_path,
                        "dst_size": dst_map.get(rel_path, 0),
                        "detail": f"Case 1: 已软删除 → {new_rel}",
                    })
                else:
                    # 文件名已带 _deleted_at_ 后缀（极端边界情况），保留不动
                    log_entries.append({
                        "action": "keep",
                        "path": rel_path,
                        "dst_size": dst_map.get(rel_path, 0),
                        "detail": "Case 1: 已含软删除标记，保留不动",
                    })
            except (PermissionError, OSError) as e:
                error_count += 1
                log_entries.append({
                    "action": "error",
                    "path": rel_path,
                    "detail": f"Case 1 软删除失败: {e}",
                })
                print(f"  ✗ 软删除失败: {rel_path} ({e})")
    else:
        for rel_path in sorted(only_in_dst):
            log_entries.append({
                "action": "keep",
                "path": rel_path,
                "dst_size": dst_map.get(rel_path, 0),
                "detail": "Case 1: 仅 DST 有，保留不操作",
            })

    t_end = time.time()

    # 输出结果
    print(f"\n{'='*50}")
    print(f"操作完成!")
    print(f"  复制/覆盖: {copy_count} 个文件")
    if args.soft_delete:
        if soft_delete_dir_count > 0:
            print(f"  软删除目录: {soft_delete_dir_count} 个")
        print(f"  软删除文件: {soft_delete_count} 个")
        skipped_total = skipped + already_soft_deleted_count
    else:
        skipped_total = skipped + len(only_in_dst)
    print(f"  跳过:     {skipped_total} 个文件 (含 {skipped} 个 MD5 一致)")
    print(f"  错误:     {error_count} 个")
    if not args.yes:
        overridden = sum(1 for d in decisions if d["action"] == "overwrite")
        print(f"  冲突覆盖: {overridden}/{len(conflicts)} 个")
    print(f"  总耗时:   {t_end - t_start:.2f}s")

    # 写入日志
    if args.log:
        log_result(log_entries, args.log)
        print(f"  日志:     {args.log}")

    if error_count > 0:
        sys.exit(2)


if __name__ == "__main__":
    main()
