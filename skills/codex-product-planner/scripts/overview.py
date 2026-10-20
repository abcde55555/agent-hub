#!/usr/bin/env python3
"""Build an offline project overview from explicit annotations and existing records."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlsplit

SKILL = Path(__file__).resolve().parents[1]
DATA_TAG = re.compile(r'<script id="overview-data" type="application/json">(.*?)</script>', re.S)
PHASES = {"NOT_STARTED", "IN_PROGRESS", "NEEDS_DECISION", "BLOCKED",
          "READY_FOR_INTEGRATION", "REVIEW_COMPLETE"}
MAX_BYTES = 8 * 1024 * 1024


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def load(path):
    if path.stat().st_size > MAX_BYTES:
        raise ValueError(f"JSON 超过读取上限: {path}")
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError(f"JSON 必须为对象: {path}")
    return result


def inside(root, path):
    if not path.resolve().is_relative_to(root):
        raise ValueError(f"路径越出项目或经过外部符号链接: {path}")
    return path


def locations(args):
    root = Path(args.project).expanduser().resolve(strict=True)
    rel = PurePosixPath(args.workflow_dir)
    if not root.is_dir() or rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise ValueError("需要现有项目目录及项目内 workflow-dir")
    flow = inside(root, root / str(rel))
    if flow == root or ".git" in rel.parts:
        raise ValueError("workflow-dir 必须为独立的项目子目录")
    out = inside(root, flow / "overview")
    for name in ("model.json", "index.html"):
        path = inside(root, out / name)
        if path.is_symlink():
            raise ValueError(f"展示写入目标不能为符号链接: {path}")
    return root, flow, out


def file_hash(path):
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reference(root, out, ref):
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError("来源必须是非空路径或 https URL")
    if ref.startswith("https://") and urlsplit(ref).netloc:
        return {"label": ref, "href": ref, "external": True, "exists": None}
    match = re.fullmatch(r"(.+?):([1-9][0-9]*)", ref)
    name = match[1] if match else ref
    rel = PurePosixPath(name)
    if rel.is_absolute() or ".." in rel.parts or ".git" in rel.parts or ":" in name or "\\" in name:
        raise ValueError(f"来源需为项目内相对文件路径: {ref}")
    path = inside(root, root / name)
    if path == out or path.is_relative_to(out):
        raise ValueError("来源不能引用生成的展示目录，以免循环依赖")
    exists = path.is_file()
    sha = file_hash(path) if exists else None
    href = quote(os.path.relpath(path, out), safe="/")
    return {"label": ref, "href": href, "path": name, "external": False,
            "exists": exists, "sha256": sha}


def validate(model):
    if model.get("schema_version") != 1:
        raise ValueError("overview schema_version 必须为 1")
    for key in ("name", "summary"):
        if model.get(key) is not None and not isinstance(model[key], str):
            raise ValueError(f"{key} 必须为文字或 null")
    if model.get("stage") not in {"unknown", "legacy", "development", "completed"}:
        raise ValueError("未知项目 stage")
    goal = model.get("goal")
    if not isinstance(goal, dict) or any(type(goal.get(k)) is not bool for k in ("confirmed", "roadmap_complete")):
        raise ValueError("goal 需要 confirmed、roadmap_complete 布尔值")
    if goal.get("text") is not None and not isinstance(goal["text"], str):
        raise ValueError("goal.text 必须为文字或 null")
    if goal["confirmed"] and (not goal.get("text") or not goal.get("source_refs")):
        raise ValueError("已确认目标需要文字和来源")
    basis = model.get("basis")
    if not isinstance(basis, dict):
        raise ValueError("basis 必须为对象")
    for key in ("head_sha", "fingerprint"):
        if basis.get(key) is not None and not isinstance(basis[key], str):
            raise ValueError(f"basis.{key} 必须为文字或 null")
    panorama = model.get("panorama")
    if not isinstance(panorama, dict):
        raise ValueError("panorama 必须为对象")
    groups = [(panorama, "nodes", "label", {"planned", "implemented", "verified", "unknown"}),
              (model, "milestones", "title", {"planned", "active", "verified", "unknown"}),
              (model, "technical", "title", None), (model, "gaps", "text", None),
              (model, "next_steps", "text", None)]
    items = [goal]
    for parent, key, title, states in groups:
        rows = parent.get(key)
        if not isinstance(rows, list):
            raise ValueError(f"{key} 必须为列表")
        ids = set()
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get(title), str) or not row[title].strip():
                raise ValueError(f"{key} 每项需要 {title}")
            if states:
                ident = row.get("id")
                if not isinstance(ident, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", ident) or ident in ids:
                    raise ValueError(f"{key} 的 id 缺失或重复")
                ids.add(ident)
                if row.get("state") not in states:
                    raise ValueError(f"{key} 的 state 无效")
                if row["state"] in {"verified", "implemented"} and not row.get("source_refs"):
                    raise ValueError(f"{ident} 需要证据来源")
            for field in ("summary", "done_when", "owner"):
                if field in row and not isinstance(row[field], str):
                    raise ValueError(f"{key}.{field} 必须为文字")
            items.append(row)
    for row in items:
        refs = row.get("source_refs", [])
        if not isinstance(refs, list) or any(not isinstance(x, str) for x in refs):
            raise ValueError("source_refs 必须为文字列表")
    nodes = {n["id"] for n in panorama["nodes"]}
    edges = panorama.get("edges")
    if not isinstance(edges, list):
        raise ValueError("panorama.edges 必须为列表")
    for edge in edges:
        if not isinstance(edge, dict) or edge.get("from") not in nodes or edge.get("to") not in nodes or not isinstance(edge.get("label"), str):
            raise ValueError("全景关系需要有效的 from、to 和 label")
    milestones = {m["id"]: m for m in model["milestones"]}
    visiting, visited = set(), set()

    def visit(ident):
        if ident in visiting:
            raise ValueError("里程碑依赖形成循环")
        if ident in visited:
            return
        visiting.add(ident)
        deps = milestones[ident].get("depends_on", [])
        if not isinstance(deps, list) or any(not isinstance(x, str) or x not in milestones for x in deps):
            raise ValueError("里程碑 depends_on 需要有效 id 列表")
        for dep in deps:
            visit(dep)
        visiting.remove(ident)
        visited.add(ident)
    for ident in milestones:
        visit(ident)
    for key in ("sources", "task_sources"):
        model.setdefault(key, [])
        if not isinstance(model.get(key, []), list):
            raise ValueError(f"{key} 必须为列表")
    for source in model.get("sources", []):
        if not isinstance(source, dict) or not isinstance(source.get("path"), str) or source.get("role") not in {"current", "plan", "historical", "conflict", "reference"} or not isinstance(source.get("note", ""), str):
            raise ValueError("资料索引需要 path、role 和可选 note")
    for source in model.get("task_sources", []):
        if not isinstance(source, dict) or not isinstance(source.get("task_id"), str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", source["task_id"]):
            raise ValueError("外部任务需要 task_id")
        if not isinstance(source.get("directory"), str) or not Path(source["directory"]).is_absolute():
            raise ValueError("外部任务 directory 需要已获授权读取的绝对路径")
    return items


def git_version(root, flow):
    def run(*args):
        try:
            result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                                    timeout=12, env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
        except (OSError, subprocess.TimeoutExpired):
            return None
        return result.stdout if result.returncode == 0 else None
    head = run("rev-parse", "--verify", "HEAD")
    if not head:
        return {"kind": "unversioned", "head_sha": None, "dirty": None,
                "scope": "仅显式引用的本地文件；没有有效 Git 提交", "complete": True}
    top = run("rev-parse", "--show-toplevel")
    repo_root = Path(os.fsdecode(top).strip()).resolve() if top else root
    paths = [".", f":(exclude){flow.relative_to(root).as_posix()}"]
    status = run("status", "--porcelain=v1", "-z", "--untracked-files=all", "--", *paths)
    diff = run("diff", "--no-ext-diff", "--no-textconv", "--binary", "HEAD", "--", *paths)
    tree = run("ls-tree", "-r", "-z", "--full-name", "HEAD", "--", ".")
    flow_prefix = os.fsencode(flow.relative_to(repo_root).as_posix())
    product_tree, gitlinks, notes = [], [], []
    for entry in (tree or b"").split(b"\0"):
        if b"\t" in entry:
            path = entry.split(b"\t", 1)[1]
            if path != flow_prefix and not path.startswith(flow_prefix + b"/"):
                product_tree.append(entry.hex())
                if entry.startswith(b"160000 "):
                    gitlinks.append(repo_root / os.fsdecode(path))
    complete = status is not None and diff is not None and tree is not None
    if gitlinks:
        status2 = run("status", "--porcelain=v2", "-z", "--untracked-files=no", "--", *paths)
        dirty_submodule = status2 is None
        for entry in (status2 or b"").split(b"\0"):
            fields = entry.split(b" ", 3)
            if len(fields) >= 3 and fields[0] in {b"1", b"2"} and fields[2].startswith(b"S") and fields[2][2:] != b"..":
                dirty_submodule = True
        if dirty_submodule or any(not (path / ".git").exists() for path in gitlinks):
            complete = False
            notes.append("子模块有未提交内容或尚未初始化；当前工具不递归核验其内容，相关结论待复核")
    untracked = []
    entries = (status or b"").split(b"\0")
    for entry in entries:
        if entry.startswith(b"?? "):
            name = os.fsdecode(entry[3:])
            if len(untracked) >= 200:
                complete = False
                break
            # Porcelain paths are relative to the Git top level, even with -C.
            path = repo_root / name
            if path.is_symlink():
                # Hash the link itself; never follow an unrelated external target.
                sha = hashlib.sha256(os.fsencode(os.readlink(path))).hexdigest()
            else:
                inside(root, path)
                sha = file_hash(path)
            untracked.append({"path": path.relative_to(root).as_posix(), "sha256": sha})
            complete = complete and sha is not None
    return {"kind": "git", "head_sha": head.decode().strip(), "dirty": bool(status),
            "product_tree_sha256": digest(product_tree),
            "diff_sha256": hashlib.sha256(diff or b"").hexdigest(),
            "status_sha256": hashlib.sha256(status or b"").hexdigest(), "untracked": untracked,
            "scope": "当前项目 Git 版本、工作区差异与显式引用文件；排除协作目录", "complete": complete, "notes": notes}


def records(root, flow, out, model, inputs, warnings):
    central = {p.name: inside(root, p) for p in (flow / "tasks").glob("*") if p.is_dir()}
    paths = dict(central)
    for source in model.get("task_sources", []):
        paths[source["task_id"]] = Path(source["directory"]).expanduser().resolve()
    result = []
    for ident, folder in sorted(paths.items()):
        row = {"id": ident, "phase": "UNKNOWN", "title": ident, "directory": str(folder)}
        try:
            task_path, status_path = folder / "task.json", folder / "status.json"
            for path in (task_path, status_path):
                # Explicit task directories permit these records, never symlinked files.
                if path.is_symlink() or not path.resolve().is_relative_to(folder.resolve()):
                    raise ValueError("任务记录不能经符号链接跳出白名单")
                inputs[str(path)] = file_hash(path)
            task, status = load(task_path), load(status_path)
            if task.get("task_id") != ident or status.get("task_id") != ident or task.get("revision") != status.get("revision"):
                raise ValueError("任务身份或 revision 不一致")
            canonical = central.get(ident, flow / "tasks" / ident) / "task.json"
            inside(root, canonical)
            if canonical.is_symlink():
                raise ValueError("中央合同不能为符号链接")
            inputs[str(canonical)] = file_hash(canonical)
            if task_path.resolve() != canonical.resolve():
                row["reported_phase"] = status.get("phase")
                row["revision"] = task.get("revision")
                if not canonical.is_file():
                    raise ValueError("外部执行记录尚未与中央合同核对")
                expected = load(canonical)
                row["canonical_revision"] = expected.get("revision")
                if expected.get("task_id") != ident or digest(expected) != digest(task):
                    raise ValueError("外部执行合同与中央当前合同不一致，旧版本进展不可送验")
            row.update(title=task.get("title") or ident, revision=task.get("revision"),
                       summary=status.get("summary"), next_action=status.get("next_action"),
                       head_sha=status.get("head_sha"), workspace=status.get("workspace"))
            if status.get("phase") not in PHASES:
                raise ValueError("任务执行阶段无效")
            row["phase"] = status["phase"]
            revision = task.get("revision")
            if type(revision) is not int or revision < 1:
                raise ValueError("任务 revision 需要正整数")
            report = folder / f"report-r{revision}.md"
            if report.is_symlink():
                raise ValueError("报告不能是符号链接")
            inputs[str(report)] = file_hash(report)
            row["report"] = str(report) if report.is_file() else None
            row["report_href"] = quote(os.path.relpath(report, out), safe="/") if report.is_file() and report.is_relative_to(root) else None
            if row["phase"] in {"READY_FOR_INTEGRATION", "REVIEW_COMPLETE"} and not report.is_file():
                row["warning"] = "报告尚未取得；执行阶段不代表检查通过或已集成"
                warnings.append(f"{ident}: {row['warning']}")
        except (OSError, ValueError, TypeError) as exc:
            row["phase"] = "UNKNOWN"
            row["warning"] = str(exc)
            warnings.append(f"{ident}: {exc}")
        result.append(row)
    return result


def assemble(root, flow, out):
    model_path = out / "model.json"
    model = load(model_path)
    items = validate(model)
    warnings, refs = [], {}
    raw_refs = [ref for item in items for ref in item.get("source_refs", [])]
    raw_refs += [s["path"] for s in model.get("sources", [])]
    for ref in dict.fromkeys(raw_refs):
        refs[ref] = reference(root, out, ref)
        if not refs[ref]["external"] and not refs[ref].get("sha256"):
            warnings.append(f"来源缺失或超过读取上限: {ref}")
    local = {ref["path"]: ref.get("sha256") for ref in refs.values() if not ref["external"]}
    version = git_version(root, flow)
    warnings.extend(version.get("notes", []))
    # A documentation-only commit must not invalidate unchanged product content.
    product_version = {k: v for k, v in version.items() if k != "head_sha"}
    basis = {"head_sha": version["head_sha"], "fingerprint": digest({"version": product_version, "local_sources": local})}
    conflict = any(s["role"] == "conflict" for s in model.get("sources", []))
    basis_matches = model.get("basis", {}).get("fingerprint") == basis["fingerprint"] and version["complete"] and bool(local) and all(local.values()) and not conflict
    if conflict:
        warnings.append("存在资料冲突，相关现状与核验结论待复核")
    if not basis_matches:
        warnings.append("展示解释尚未与当前版本和引用范围对齐；已核验状态降为待复核")
    inputs = {str(model_path): file_hash(model_path)}
    for name in ("project.md", "iteration.md", "protocol.md", "coordination.json"):
        path = inside(root, flow / name)
        inputs[str(path)] = file_hash(path)
    tasks = records(root, flow, out, model, inputs, warnings)
    template = SKILL / "assets/overview.html"
    inputs["renderer"] = file_hash(Path(__file__))
    inputs["template"] = file_hash(template)
    for item in items:
        item["references"] = [refs[r] for r in item.get("source_refs", [])]
        if item.get("state") in {"implemented", "verified"}:
            evidence = [r for r in item["references"] if not r["external"] and r.get("sha256")]
            item["effective_state"] = item["state"] if basis_matches and evidence else "outdated"
        else:
            item["effective_state"] = item.get("state")
    goal = model["goal"]
    milestones = model["milestones"]
    scope_defined = bool(goal["confirmed"] and goal["roadmap_complete"] and milestones and
                         all(m.get("done_when") for m in milestones) and basis_matches)
    progress = {"defined": scope_defined, "verified": sum(m["effective_state"] == "verified" for m in milestones), "total": len(milestones)}
    fingerprint = digest({"product_fingerprint": basis["fingerprint"], "inputs": inputs, "references": refs})
    return {"schema_version": 1, "model": model, "tasks": tasks, "references": refs,
            "version": version, "basis": basis, "basis_matches": bool(basis_matches),
            "progress": progress, "warnings": warnings, "root": str(root),
            "fingerprint": fingerprint, "input_count": len(inputs) + len(local)}


def previous(path):
    if not path.is_file():
        return None
    match = DATA_TAG.search(path.read_text(encoding="utf-8"))
    if not match:
        raise ValueError("已有 index.html 不是本工具生成的页面，保留原文件")
    return json.loads(match[1])


def render_html(data):
    embedded = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    template = (SKILL / "assets/overview.html").read_text(encoding="utf-8")
    if template.count("<!--OVERVIEW_DATA-->") != 1:
        raise ValueError("展示模板缺少唯一数据插槽")
    return template.replace("<!--OVERVIEW_DATA-->", f'<script id="overview-data" type="application/json">{embedded}</script>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "inspect", "render", "check"))
    parser.add_argument("--project", required=True)
    parser.add_argument("--workflow-dir", default="docs/ai-workflow")
    args = parser.parse_args()
    try:
        root, flow, out = locations(args)
        model_path, html_path = out / "model.json", out / "index.html"
        if args.command == "init":
            created = not model_path.exists()
            if created:
                out.mkdir(parents=True, exist_ok=True)
                with model_path.open("x", encoding="utf-8") as stream:
                    stream.write((SKILL / "assets/overview.json").read_text(encoding="utf-8"))
            result = {"ok": True, "created": created, "model": str(model_path), "requires_agent_curation": True}
        else:
            data = assemble(root, flow, out)
            old = previous(html_path)
            fresh = bool(old and old.get("fingerprint") == data["fingerprint"] and
                         html_path.read_text(encoding="utf-8") == render_html(old))
            result = {"ok": True, "basis": data["basis"], "basis_matches": data["basis_matches"],
                      "html": str(html_path), "fresh": fresh, "warnings": data["warnings"],
                      "tasks": len(data["tasks"]), "input_count": data["input_count"]}
            if args.command == "inspect":
                result["scope"] = data["version"]["scope"]
            elif args.command == "check":
                result["ok"] = fresh and not data["warnings"]
            elif args.command == "render":
                if not fresh:
                    data["generated_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                    html = render_html(data)
                    temporary = None
                    try:
                        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=out, prefix=".overview-", suffix=".tmp", delete=False) as stream:
                            temporary = Path(stream.name)
                            stream.write(html)
                        os.replace(temporary, html_path)
                    finally:
                        if temporary and temporary.exists():
                            temporary.unlink()
                result.update(changed=not fresh, fresh=True)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)], "previous_html_preserved": True}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
