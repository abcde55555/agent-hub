#!/usr/bin/env python3
"""Create and validate project workflow files; never dispatch or modify Git."""

import argparse
import copy
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

SKILL = Path(__file__).resolve().parents[1]
TASK_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
SHA = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?\Z")
MODES = {"prototype", "implement", "review"}
PHASES = {"NOT_STARTED", "IN_PROGRESS", "NEEDS_DECISION", "BLOCKED",
          "READY_FOR_INTEGRATION", "REVIEW_COMPLETE"}


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"对象格式错误: {path}")
    return data


def inside(root, candidate):
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"路径越出项目或经过外部符号链接: {candidate}")
    return candidate


def locations(args):
    root = Path(args.project).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("project 必须是现有目录")
    rel = PurePosixPath(args.workflow_dir)
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise ValueError("workflow-dir 必须是项目内相对目录")
    flow = inside(root, root / str(rel))
    if flow == root:
        raise ValueError("workflow-dir 必须是独立子目录")
    return root, flow


def new_file(root, path, content):
    inside(root, path)
    if path.is_symlink():
        raise ValueError(f"拒绝写入符号链接文件: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(content)


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def git(root, *args):
    try:
        result = subprocess.run(["git", "-C", str(root), *args],
                                capture_output=True, text=True, timeout=15)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def init(args):
    root, flow = locations(args)
    config_path = inside(root, flow / "coordination.json")
    if flow.exists() and any(flow.iterdir()) and not config_path.exists():
        raise ValueError("已有协作目录不是本工具创建的；先映射现有资料或选择其他 workflow-dir")
    if config_path.exists() and read_json(config_path).get("schema_version") != 1:
        raise ValueError("现有协调记录版本不兼容，保留原文件并先确认迁移")
    config = {
        "schema_version": 1,
        "project": {"root": str(root), "project_id": None, "host_id": None},
        "models": {
            "planner": {"model": "gpt-6.1-sol", "source": None},
            "worker": {"model": "gpt-6-luna", "thinking": "high", "source": None}},
        "authority": {"source": None, "create_chats": False,
                      "message_new_chats": False, "message_threads": [],
                      "worktrees": False, "starting_state": None,
                      "local_integration": False},
        "assignments": {}}
    files = {
        "project.md": (SKILL / "assets/project.md").read_text(encoding="utf-8"),
        "iteration.md": (SKILL / "assets/iteration.md").read_text(encoding="utf-8"),
        "protocol.md": (SKILL / "references/project-protocol.md").read_text(encoding="utf-8"),
        "coordination.json": json_text(config)}
    # Resolve all destinations before creating any of them.
    for name in files:
        path = inside(root, flow / name)
        if path.is_symlink():
            raise ValueError(f"现有目标是符号链接: {path}")
    created, preserved = [], []
    for name, content in files.items():
        path = flow / name
        if path.exists():
            preserved.append(name)
        else:
            new_file(root, path, content)
            created.append(name)
    return {"workflow": str(flow), "created": created, "preserved": preserved,
            "git_head": git(root, "rev-parse", "--verify", "HEAD")}


def task_dir(root, flow, task_id):
    if not TASK_ID.fullmatch(task_id):
        raise ValueError("任务编号仅允许字母、数字、下划线、连字符，最长 64 字符")
    return inside(root, flow / "tasks" / task_id)


def new_task(args):
    root, flow = locations(args)
    if not (flow / "coordination.json").is_file():
        raise ValueError("先 init 或确认现有协作协议")
    target = task_dir(root, flow, args.id)
    if target.exists():
        raise ValueError(f"任务已存在，保留原文件: {target}")
    task = copy.deepcopy(read_json(SKILL / "assets/task.json"))
    head = git(root, "rev-parse", "--verify", "HEAD")
    task.update(task_id=args.id, mode=args.mode)
    task["baseline"].update(kind="git" if head else "unversioned", base_sha=head,
                            uncommitted_changes=git(root, "status", "--short"))
    status = {"schema_version": 1, "task_id": args.id, "revision": 1,
              "phase": "NOT_STARTED", "updated_at_utc": utc_now(),
              "workspace": None, "head_sha": None, "summary": None,
              "blocker": None, "next_action": None}
    new_file(root, target / "task.json", json_text(task))
    new_file(root, target / "status.json", json_text(status))
    return {"task": str(target / "task.json"), "ready": False, "mode": args.mode}


def text_value(value):
    if not isinstance(value, str) or not value.strip():
        return False
    val = value.strip()
    if val.upper() in {"TODO", "TBD", "FIXME", "PLACEHOLDER"} or val in {"待填写", "待补充"}:
        return False
    return not (val.startswith("<") and val.endswith(">"))


def strings(value, nonempty=False):
    return isinstance(value, list) and (bool(value) or not nonempty) and all(text_value(x) for x in value)


def valid_scope(path):
    if not text_value(path) or "\\" in path:
        return False
    rel = PurePosixPath(path)
    return (bool(rel.parts) and not rel.is_absolute() and ".." not in rel.parts
            and rel.parts[0] != ".git")


def check_task(root, path, expected_id, ready):
    task = read_json(path)
    errors = []

    def need(ok, message):
        if not ok:
            errors.append(f"{expected_id}: {message}")

    need(task.get("schema_version") == 1, "schema_version 必须为 1")
    need(task.get("task_id") == expected_id, "task_id 与目录不一致")
    need(type(task.get("revision")) is int and task["revision"] > 0, "revision 必须为正整数")
    need(isinstance(task.get("mode"), str) and task["mode"] in MODES, "未知 mode")
    need(type(task.get("ready")) is bool, "ready 必须为布尔值")
    scope = task.get("scope", {})
    need(isinstance(scope, dict), "scope 必须为对象")
    scope = scope if isinstance(scope, dict) else {}
    paths = scope.get("write_paths", [])
    need(isinstance(paths, list) and all(valid_scope(x) for x in paths), "write_paths 必须是项目内相对路径")
    if task.get("mode") == "review":
        need(paths == [], "review 仅写自身报告、状态和证据，write_paths 应为空")
    acceptance = task.get("acceptance", [])
    need(isinstance(acceptance, list), "acceptance 必须是列表")
    acceptance = acceptance if isinstance(acceptance, list) else []
    ids = []
    for ac in acceptance:
        if not isinstance(ac, dict):
            need(False, "AC 必须为对象")
            continue
        for key in ["id", "given", "when", "then", "verification"]:
            need(text_value(ac.get(key)), f"AC 缺少 {key}")
        for key in ["required", "requires_human"]:
            need(type(ac.get(key)) is bool, f"AC.{key} 必须为布尔值")
        ids.append(ac.get("id"))
    need(len(ids) == len({str(x) for x in ids}), "AC 编号重复")
    if ready:
        need(task.get("ready") is True, "合同仍是草稿")
        for key in ["title", "user_goal"]:
            need(text_value(task.get(key)), f"缺少 {key}")
        scenario = task.get("scenario", {})
        scenario = scenario if isinstance(scenario, dict) else {}
        for key in ["actor", "start", "expected_result"]:
            need(text_value(scenario.get(key)), f"scenario 缺少 {key}")
        need(strings(scenario.get("actions"), True), "scenario.actions 需要实际步骤")
        baseline = task.get("baseline", {})
        baseline = baseline if isinstance(baseline, dict) else {}
        need(isinstance(baseline.get("kind"), str) and baseline["kind"] in {"git", "unversioned"}, "baseline.kind 不合法")
        if baseline.get("kind") == "git":
            sha = baseline.get("base_sha")
            need(isinstance(sha, str) and bool(SHA.fullmatch(sha)), "Git 基线需要完整 SHA")
            if isinstance(sha, str) and SHA.fullmatch(sha):
                need(git(root, "cat-file", "-t", sha) == "commit", "基线 SHA 在当前仓库不是有效提交")
        need(strings(baseline.get("source_refs"), True), "baseline.source_refs 需要权威资料来源")
        need(text_value(baseline.get("uncommitted_changes")), "说明已有改动与处理方式；无改动写清无")
        need(bool(acceptance), "需要可观察 AC")
        need(any(isinstance(ac, dict) and ac.get("required") is True for ac in acceptance), "至少一项必要 AC")
        if task.get("mode") != "review":
            need(bool(paths), "实现/原型需要明确 write_paths")
        verification = task.get("verification", {})
        verification = verification if isinstance(verification, dict) else {}
        need(text_value(verification.get("entrypoint")), "说明验证入口")
        need(strings(verification.get("commands")), "verification.commands 应为字符串列表")
        need(strings(verification.get("limits")), "verification.limits 应为字符串列表")
        if task.get("mode") == "review":
            review = task.get("review_target", {})
            review = review if isinstance(review, dict) else {}
            for key in ["base_sha", "head_sha"]:
                sha = review.get(key)
                need(isinstance(sha, str) and bool(SHA.fullmatch(sha)), f"review_target.{key} 需要完整 SHA")
                if isinstance(sha, str) and SHA.fullmatch(sha):
                    need(git(root, "cat-file", "-t", sha) == "commit", f"review_target.{key} 不存在")
    status_path = path.with_name("status.json")
    if status_path.exists():
        status = read_json(inside(root, status_path))
        need(status.get("task_id") == expected_id, "status.task_id 不一致")
        need(isinstance(status.get("phase"), str) and status["phase"] in PHASES, "status.phase 不合法")
    return errors


def check(args):
    root, flow = locations(args)
    config = read_json(inside(root, flow / "coordination.json"))
    errors = []
    if config.get("schema_version") != 1:
        errors.append("coordination.schema_version 必须为 1")
    authority = config.get("authority")
    if not isinstance(authority, dict):
        errors.append("authority 必须为对象")
        authority = {}
    keys = ["create_chats", "message_new_chats", "worktrees", "local_integration"]
    for key in keys:
        if type(authority.get(key)) is not bool:
            errors.append(f"authority.{key} 必须为布尔值")
    if not strings(authority.get("message_threads")):
        errors.append("authority.message_threads 应为 ID 字符串列表")
    if any(authority.get(k) is True for k in keys) or authority.get("message_threads"):
        if not text_value(authority.get("source")):
            errors.append("已开启授权缺少直接人类指令 source；配置本身不授予权限")
    for name in ["project.md", "iteration.md", "protocol.md"]:
        if not inside(root, flow / name).is_file():
            errors.append(f"缺少 {name}")
    if args.task:
        paths = [task_dir(root, flow, args.task) / "task.json"]
    else:
        paths = sorted((flow / "tasks").glob("*/task.json"))
    for path in paths:
        inside(root, path)
        if not path.is_file():
            errors.append(f"任务不存在: {path}")
        else:
            errors.extend(check_task(root, path, path.parent.name, args.ready))
    result = {"ok": not errors, "workflow": str(flow), "checked_tasks": len(paths),
              "ready_check": args.ready, "errors": errors}
    if args.task and not errors:
        result["task_sha256"] = hashlib.sha256(paths[0].read_bytes()).hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ["init", "new-task", "check"]:
        cmd = sub.add_parser(name)
        cmd.add_argument("--project", required=True)
        cmd.add_argument("--workflow-dir", default="docs/ai-workflow")
        if name == "new-task":
            cmd.add_argument("--id", required=True)
            cmd.add_argument("--mode", choices=sorted(MODES), default="implement")
        if name == "check":
            cmd.add_argument("--task")
            cmd.add_argument("--ready", action="store_true")
    args = parser.parse_args()
    try:
        result = {"init": init, "new-task": new_task, "check": check}[args.command](args)
    except (OSError, ValueError) as exc:
        print(json_text({"ok": False, "errors": [str(exc)]}), end="")
        return 1
    print(json_text(result), end="")
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
