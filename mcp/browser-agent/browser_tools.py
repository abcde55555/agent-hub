"""
browser_tools.py — 浏览器操作工具层（Playwright + CDP）

四大能力封成确定性工具：网络请求记录 / 看页面 / 精确点击填表 / 自主滚动翻页。

【持久化】浏览器作为独立常驻进程启动（--remote-debugging-port + 固定 user-data-dir），
MCP server 用 connect_over_cdp 连接：
  - server 重启 → 浏览器仍在，CDP 重连，登录态不丢；
  - 浏览器重启 → profile 目录里 cookies/localStorage/登录态自动恢复。
  profile 目录：~/.browser-agent/profiles/<name>

【操作记录】每次会话落盘到 ~/.browser-agent/logs/<profile>/<session>/：
  - action.log.jsonl  每个动作一条（时间/工具/参数[密码脱敏]/前后URL/结果）
  - screenshots/      每步动作后截图 PNG
  - trace.zip         Playwright Trace，`playwright show-trace trace.zip` 逐帧回放
"""
from __future__ import annotations
import asyncio
import json
import os
import re
import shutil
import socket
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright, Page, BrowserContext, ElementHandle

# ---------- 路径常量 ----------
HOME = Path.home()
PROFILE_ROOT = HOME / ".browser-agent" / "profiles"
LOG_ROOT = HOME / ".browser-agent" / "logs"
DEFAULT_PORT = 9222

INTERACTIVE_SELECTOR = (
    'a[href], button, input:not([type=hidden]), select, textarea, '
    '[role=button], [role=link], [role=checkbox], [role=tab], [role=menuitem], '
    '[onclick], [contenteditable="true"], [contenteditable=""]'
)
INTERESTING_TYPES = {"xhr", "fetch", "document", "websocket"}
MAX_BODY_CAPTURE = 20_000


@dataclass
class Flow:
    idx: int
    method: str
    url: str
    rtype: str
    status: int | None = None
    ctype: str = ""
    post_data: str | None = None
    req_headers: dict[str, str] | None = None
    body: str | None = None
    body_truncated: bool = False

    def summary(self) -> dict[str, Any]:
        d = {
            "idx": self.idx, "method": self.method, "status": self.status,
            "rtype": self.rtype, "ctype": self.ctype, "url": self.url,
        }
        if self.post_data:
            d["post_data"] = self.post_data[:500]
        if self.body is not None:
            d["body_preview"] = self.body[:1000]
            d["body_truncated"] = self.body_truncated
        return d


def _cdp_ready(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


class BrowserTools:
    def __init__(self) -> None:
        self._pw = None
        self.browser = None
        self.ctx: BrowserContext | None = None
        self.page: Page | None = None
        self._flows: list[Flow] = []
        self._elements: dict[int, ElementHandle] = {}
        self.profile = "default"
        self.port = DEFAULT_PORT
        self._proc = None
        # 操作记录
        self.session_dir: Path | None = None
        self._log_fp = None
        self._seq = 0

    # ========== 生命周期（常驻浏览器 + 持久化 profile） ==========
    async def start(self, headless: bool = False, profile: str = "default",
                    port: int = DEFAULT_PORT, proxy: str | None = None) -> dict[str, Any]:
        """启动/连接常驻浏览器。profile 隔离登录态；proxy 例 'http://127.0.0.1:8080'。"""
        self.profile = re.sub(r"[^A-Za-z0-9_.-]", "_", profile)
        self.port = port
        PROFILE_ROOT.mkdir(parents=True, exist_ok=True)
        user_data_dir = PROFILE_ROOT / self.profile
        user_data_dir.mkdir(parents=True, exist_ok=True)

        # 会话记录目录
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.session_dir = LOG_ROOT / self.profile / f"session-{ts}"
        (self.session_dir / "screenshots").mkdir(parents=True, exist_ok=True)
        self._log_fp = open(self.session_dir / "action.log.jsonl", "a", encoding="utf-8")

        self._pw = await async_playwright().start()

        launched = False
        if not _cdp_ready(port):
            exe = self._pw.chromium.executable_path
            args = [
                exe,
                f"--remote-debugging-port={port}",
                f"--user-data-dir={user_data_dir}",
                "--no-first-run", "--no-default-browser-check",
                "--disable-features=Translate,GlobalMediaControls",
            ]
            if headless:
                args.append("--headless=new")
            if proxy:
                args += [f"--proxy-server={proxy}", "--ignore-certificate-errors"]
            self._proc = subprocess.Popen(
                args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            launched = True
            for _ in range(40):
                if _cdp_ready(port):
                    break
                await asyncio.sleep(0.5)

        self.browser = await self._pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        self.ctx = self.browser.contexts[0] if self.browser.contexts else await self.browser.new_context()
        self.page = self.ctx.pages[0] if self.ctx.pages else await self.ctx.new_page()
        self._bind_capture()

        # 新标签页也绑定请求记录
        self.ctx.on("page", lambda p: self._bind_page(p))

        # Playwright Trace（可逐帧回放）
        try:
            await self.ctx.tracing.start(screenshots=True, snapshots=True, sources=True)
        except Exception:
            pass

        info = {
            "launched_new": launched, "reused_existing": not launched,
            "profile": self.profile, "profile_dir": str(user_data_dir),
            "cdp": f"http://127.0.0.1:{port}",
            "session_dir": str(self.session_dir),
            "reconnected": not launched,
        }
        await self._record("start_browser", {"headless": headless, "profile": self.profile,
                                             "proxy": proxy, **info}, screenshot=False)
        return info

    async def stop(self, close_browser: bool = False) -> dict[str, Any]:
        """默认只断开连接、保留常驻浏览器（登录态不丢）。close_browser=True 才真正关闭。"""
        trace_path = None
        try:
            trace_path = await self.flush_trace()
        except Exception:
            pass
        await self._record("stop_browser", {"close_browser": close_browser}, screenshot=False)
        if self._log_fp:
            self._log_fp.close()
            self._log_fp = None
        if close_browser and self.browser:
            # 优雅关闭 Chromium：发 CDP Browser.close，让其把 cookies/localStorage flush 到 profile
            try:
                cdp = await self.browser.new_browser_cdp_session()
                await cdp.send("Browser.close")
            except Exception:
                try:
                    await self.browser.close()
                except Exception:
                    pass
            if self._proc:
                try:
                    await asyncio.wait_for(asyncio.to_thread(self._proc.wait), timeout=10)
                except Exception:
                    try:
                        self._proc.terminate()
                    except Exception:
                        pass
        elif self.browser:
            # 仅断开 Playwright 连接，浏览器进程常驻、登录态保留
            try:
                await self.browser.close()
            except Exception:
                pass
        if self._pw:
            try:
                await self._pw.stop()
            except Exception:
                pass
        self.browser = None
        self.ctx = None
        self.page = None
        return {"closed_browser": close_browser, "trace": trace_path,
                "session_dir": str(self.session_dir) if self.session_dir else None}

    async def goto(self, url: str, wait: str = "domcontentloaded"):
        before = self.page.url
        await self.page.goto(url, wait_until=wait, timeout=60_000)
        try:
            await self.page.wait_for_load_state("networkidle", timeout=8_000)
        except Exception:
            pass
        await self._record("navigate", {"url": url, "from": before})

    # ========== 操作轨迹 ==========
    async def _record(self, action: str, args: dict[str, Any],
                      ok: bool = True, error: str | None = None,
                      screenshot: bool = True):
        if not self.session_dir:
            return
        self._seq += 1
        rec = {
            "seq": self._seq, "ts": datetime.now().isoformat(timespec="seconds"),
            "action": action, "args": args, "ok": ok,
            "url": self.page.url if self.page else None,
            "title": (await self._safe_title()) if self.page else None,
        }
        if error:
            rec["error"] = error
        shot = None
        if screenshot and self.page:
            try:
                shot = self.session_dir / "screenshots" / f"{self._seq:04d}-{action}.png"
                await self.page.screenshot(path=str(shot), full_page=False)
                rec["screenshot"] = str(shot)
            except Exception:
                shot = None
        if self._log_fp:
            self._log_fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
            self._log_fp.flush()

    async def _safe_title(self) -> str:
        try:
            return await self.page.title()
        except Exception:
            return ""

    async def flush_trace(self) -> str | None:
        """把当前 trace 落盘为 trace.zip 并立即继续录制（分段）。"""
        if not self.ctx or not self.session_dir:
            return None
        path = str(self.session_dir / f"trace-{self._seq:04d}.zip")
        try:
            await self.ctx.tracing.stop(path=path)
            await self.ctx.tracing.start(screenshots=True, snapshots=True, sources=True)
            return path
        except Exception:
            return None

    def get_action_log(self, last: int = 30) -> dict[str, Any]:
        """返回最近操作记录（供 agent / 人回顾）。"""
        if not self.session_dir:
            return {"actions": []}
        lines = (self.session_dir / "action.log.jsonl").read_text(encoding="utf-8").splitlines()
        recs = [json.loads(l) for l in lines if l.strip()]
        return {
            "session_dir": str(self.session_dir),
            "total": len(recs),
            "actions": recs[-last:],
        }

    # ========== 能力 1：网络请求记录（context 级，覆盖所有标签页） ==========
    def _bind_capture(self):
        async def on_response(resp):
            try:
                req = resp.request
                rtype = req.resource_type
                flow = Flow(
                    idx=len(self._flows), method=req.method, url=resp.url,
                    rtype=rtype, status=resp.status,
                    ctype=resp.headers.get("content-type", ""),
                    post_data=req.post_data, req_headers=dict(req.headers),
                )
                if (rtype in INTERESTING_TYPES and "json" in flow.ctype) or rtype in ("xhr", "fetch"):
                    try:
                        text = await resp.text()
                        flow.body_truncated = len(text) > MAX_BODY_CAPTURE
                        flow.body = text[:MAX_BODY_CAPTURE]
                    except Exception:
                        pass
                self._flows.append(flow)
            except Exception:
                pass

        self.ctx.on("response", lambda r: asyncio.create_task(on_response(r)))
        for p in self.ctx.pages:
            self._bind_page(p)

    def _bind_page(self, page: Page):
        # 预留：页面级钩子（未来可插入页面脚本）。请求记录已在 context 级统一监听。
        _ = page

    def list_traffic(self, pattern: str = "", rtypes: set[str] | None = None):
        out = []
        for f in self._flows:
            if rtypes and f.rtype not in rtypes:
                continue
            if pattern and not re.search(pattern, f.url):
                continue
            out.append(f.summary())
        return out

    async def get_body(self, idx: int) -> str | None:
        return self._flows[idx].body

    async def set_interceptor(self, url_glob: str, modify: dict[str, Any]):
        async def handler(route):
            req = route.request
            kwargs: dict[str, Any] = {}
            if "headers" in modify:
                kwargs["headers"] = {**req.headers, **modify["headers"]}
            if "post_data" in modify:
                kwargs["post_data"] = modify["post_data"]
            if "url" in modify:
                kwargs["url"] = modify["url"]
            await route.continue_(**kwargs)
        await self.page.route(url_glob, handler)
        await self._record("set_interceptor", {"glob": url_glob, "modify": list(modify)},
                           screenshot=False)

    async def mock_response(self, url_glob: str, status: int = 200, body: str = "",
                            content_type: str = "application/json",
                            extra_headers: dict[str, str] | None = None):
        async def handler(route):
            await route.fulfill(status=status, content_type=content_type,
                                body=body, headers=extra_headers or {})
        await self.page.route(url_glob, handler)
        await self._record("mock_response", {"glob": url_glob, "status": status},
                           screenshot=False)

    async def block_request(self, url_glob: str):
        await self.page.route(url_glob, lambda route: route.abort())
        await self._record("block_request", {"glob": url_glob}, screenshot=False)

    async def replay_request(self, idx: int, method: str | None = None,
                             url: str | None = None, post_data: str | None = None,
                             extra_headers: dict[str, str] | None = None) -> dict[str, Any]:
        f = self._flows[idx]
        m = (method or f.method).upper()
        target = url or f.url
        drop = {"content-length", "host", "connection", "cookie"}
        hdrs = {k: v for k, v in (f.req_headers or {}).items() if k.lower() not in drop}
        if extra_headers:
            hdrs.update(extra_headers)
        data = post_data if post_data is not None else f.post_data
        resp = await self.ctx.request.fetch(target, method=m, headers=hdrs, data=data)
        text = await resp.text()
        out = {
            "idx": idx, "method": m, "url": target, "status": resp.status,
            "req_post_data": (data or "")[:500],
            "body_preview": text[:2000], "body_len": len(text),
        }
        await self._record("replay_request",
                           {"idx": idx, "method": m, "url": target,
                            "post_data": (data or "")[:200], "status": resp.status},
                           screenshot=False)
        return out

    # ========== 能力 2：看页面 ==========
    async def snapshot_interactive(self) -> list[dict[str, Any]]:
        handles = await self.page.query_selector_all(INTERACTIVE_SELECTOR)
        self._elements = {}
        items: list[dict[str, Any]] = []
        idx = 0
        for h in handles:
            try:
                info = await h.evaluate(
                    """el => {
                        const vis = !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                        return {
                          tag: el.tagName.toLowerCase(),
                          type: el.type || null,
                          role: el.getAttribute('role'),
                          name: el.getAttribute('aria-label') || el.name ||
                                el.getAttribute('placeholder') ||
                                (el.innerText||'').trim().slice(0,60) ||
                                (['submit','button','reset'].includes(el.type) ? el.value : '') ||
                                el.id || '',
                          href: el.getAttribute('href'),
                          editable: ['INPUT','TEXTAREA','SELECT'].includes(el.tagName) || el.isContentEditable,
                          visible: vis
                        };
                    }"""
                )
                if not info["visible"]:
                    continue
                info["idx"] = idx
                self._elements[idx] = h
                items.append(info)
                idx += 1
            except Exception:
                continue
        self._last_snapshot = {it["idx"]: it for it in items}
        return items

    async def get_text(self) -> str:
        return (await self.page.inner_text("body"))[:8000]

    # ========== 能力 3：精确操作 ==========
    async def click(self, idx: int) -> dict[str, Any]:
        h = self._require(idx)
        info = self._elements_info(idx)
        await h.scroll_into_view_if_needed(timeout=5_000)
        await h.click(timeout=8_000)
        await self._settle()
        await self._record("click", {"idx": idx, "target": info})
        return {"clicked": idx, "url": self.page.url}

    async def fill(self, idx: int, text: str) -> dict[str, Any]:
        h = self._require(idx)
        info = self._elements_info(idx)
        tag = await h.evaluate("el => el.tagName")
        is_pw = info and str(info.get("type", "")).lower() == "password"
        await h.scroll_into_view_if_needed(timeout=5_000)
        if tag == "SELECT":
            await h.select_option(label=text)
        else:
            await h.click()
            await h.fill("")
            await h.fill(text)
        await self._record("fill", {"idx": idx, "target": info,
                                    "text": "***REDACTED***" if is_pw else text})
        return {"filled": idx}

    def _elements_info(self, idx: int) -> dict[str, Any] | None:
        # 仅用于日志：从最近快照找标签/类型
        return getattr(self, "_last_snapshot", {}).get(idx)

    def _require(self, idx: int) -> ElementHandle:
        if idx not in self._elements:
            raise KeyError(f"元素 idx={idx} 不存在（可能已翻页/导航，请重新 snapshot）")
        return self._elements[idx]

    async def _settle(self):
        try:
            await self.page.wait_for_load_state("networkidle", timeout=6_000)
        except Exception:
            pass

    # ========== 能力 4：滚动 / 翻页 ==========
    async def scroll(self, direction: str = "down", pages: int = 1):
        for _ in range(pages):
            if direction == "down":
                await self.page.keyboard.press("PageDown")
            else:
                await self.page.keyboard.press("PageUp")
            await asyncio.sleep(0.6)
            await self._settle()
        await self._record("scroll", {"direction": direction, "pages": pages})

    async def next_page(self, name_pattern: str = r"next|»|下一页|下一頁|>") -> bool:
        items = await self.snapshot_interactive()
        for it in items:
            label = f'{it["name"]} {it.get("href") or ""}'.lower()
            if re.search(name_pattern, label, re.I) and it["tag"] in ("a", "button"):
                before = self.page.url
                await self.click(it["idx"])
                await self._settle()
                await self._record("next_page", {"clicked_idx": it["idx"],
                                                 "from": before, "to": self.page.url})
                return True
        return False

    async def auto_scroll_capture(self, item_selector: str,
                                  max_rounds: int = 30,
                                  idle_stop: int = 3) -> list[dict[str, Any]]:
        seen: set[str] = set()
        collected: list[dict[str, Any]] = []
        idle = 0
        for rnd in range(1, max_rounds + 1):
            await self.page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            await self._settle()
            await asyncio.sleep(0.8)
            handles = await self.page.query_selector_all(item_selector)
            new = 0
            for h in handles:
                try:
                    text, href = await h.evaluate(
                        "el => [(el.innerText||'').trim().slice(0,200), "
                        "el.querySelector('a')?.getAttribute('href') || null]")
                    sig = str(hash(text + str(href)))
                    if sig in seen:
                        continue
                    seen.add(sig)
                    collected.append({"round": rnd, "text": text, "href": href})
                    new += 1
                except Exception:
                    continue
            idle = idle + 1 if new == 0 else 0
            if idle >= idle_stop:
                break
        await self._record("auto_scroll_capture",
                           {"selector": item_selector, "collected": len(collected),
                            "rounds": rnd}, screenshot=False)
        return collected
