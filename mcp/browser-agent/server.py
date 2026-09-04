"""
server.py — 把浏览器能力暴露为 MCP 工具，供 Claude Code / Codex 等 agent 调用。

注册（二选一命令行，或写配置）：
  Claude Code : claude mcp add browser-agent -- python3 /绝对路径/server.py
  Codex       : 在 ~/.codex/config.toml 加
                [mcp_servers.browser-agent]
                command = "python3"
                args = ["/绝对路径/server.py"]

工具集：
  start_browser / navigate / snapshot / click / fill /
  scroll / next_page / auto_scroll_capture /
  list_traffic / get_traffic_body / set_interceptor / page_text / stop_browser

会话为单例、有状态：浏览器在多次工具调用间保持（登录态、页面、网络请求记录都保留）。
注意：导航/翻页后元素 idx 失效，click/fill 前先 snapshot 重新取号。
"""
from __future__ import annotations
import json
from typing import Any

from fastmcp import FastMCP

from browser_tools import BrowserTools

mcp = FastMCP("browser-agent")
_bt: BrowserTools | None = None


async def _get() -> BrowserTools:
    global _bt
    if _bt is None:
        _bt = BrowserTools()
        await _bt.start(headless=False)  # 默认可见，方便人工登录
    return _bt


def _j(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


@mcp.tool()
async def start_browser(headless: bool = False,
                        profile: str = "default",
                        proxy: str | None = None) -> str:
    """启动或连接【常驻】浏览器。浏览器独立进程常驻 + profile 持久化登录态：
      - server 重启后再次调用会自动重连，登录态不丢；
      - 浏览器关掉后，同 profile 重启会恢复 cookies/localStorage。
    参数：
      - headless: False 显示窗口（手动登录时用），True 后台无头。
      - profile:  隔离不同任务/账号的目录名（如 'work'、'task1'），默认 'default'。
      - proxy:    可选，浏览器代理地址，如 'http://127.0.0.1:8080'。
    全程自动记录操作日志/截图/trace（见 get_action_log / flush_trace）。"""
    global _bt
    if _bt is not None:
        await _bt.stop(close_browser=False)
    _bt = BrowserTools()
    info = await _bt.start(headless=headless, profile=profile, proxy=proxy)
    return _j({"ok": True, **info})


@mcp.tool()
async def navigate(url: str) -> str:
    """打开网址并等待加载。"""
    bt = await _get()
    await bt.goto(url)
    return _j({"ok": True, "url": bt.page.url, "title": await bt.page.title()})


@mcp.tool()
async def snapshot() -> str:
    """列出当前页所有可交互元素（带 idx）。click/fill 用这里的 idx。
    每次导航/翻页后需重新 snapshot。"""
    bt = await _get()
    items = await bt.snapshot_interactive()
    return _j({"url": bt.page.url, "count": len(items), "elements": items})


@mcp.tool()
async def click(idx: int) -> str:
    """按 snapshot 返回的 idx 精确点击元素。"""
    bt = await _get()
    r = await bt.click(idx)
    return _j(r)


@mcp.tool()
async def fill(idx: int, text: str) -> str:
    """按 idx 填写输入框/文本域，或按可见文本选择下拉项。"""
    bt = await _get()
    r = await bt.fill(idx, text)
    return _j(r)


@mcp.tool()
async def scroll(direction: str = "down", pages: int = 1) -> str:
    """滚动页面。direction: 'down'/'up'；pages 为滚动次数。"""
    bt = await _get()
    await bt.scroll(direction, pages)
    return _j({"ok": True, "direction": direction, "pages": pages})


@mcp.tool()
async def next_page() -> str:
    """自动寻找并点击「下一页 / » / next」按钮。返回是否成功翻页。"""
    bt = await _get()
    ok = await bt.next_page()
    return _j({"advanced": ok, "url": bt.page.url})


@mcp.tool()
async def auto_scroll_capture(item_selector: str,
                              max_rounds: int = 30,
                              idle_stop: int = 3) -> str:
    """自动滚动页面并采集列表项内容。
    item_selector 为每条内容的 CSS 选择器（如 '.comment'、'article'）。
    自动滚到底、去重，连续 idle_stop 轮无新增即停。返回采集条数与内容。"""
    bt = await _get()
    items = await bt.auto_scroll_capture(item_selector, max_rounds, idle_stop)
    return _j({"collected": len(items), "items": items})


@mcp.tool()
async def list_traffic(pattern: str = "", xhr_only: bool = True) -> str:
    """列出本次会话记录到的网络请求摘要（方法/状态/类型/URL）。
    xhr_only=true 只看 XHR/fetch（接口请求）；pattern 为 URL 正则过滤。
    内联了 XHR/fetch 的响应体预览。"""
    bt = await _get()
    rtypes = {"xhr", "fetch"} if xhr_only else None
    flows = bt.list_traffic(pattern=pattern, rtypes=rtypes)
    return _j({"count": len(flows), "traffic": flows})


@mcp.tool()
async def get_traffic_body(idx: int) -> str:
    """按 list_traffic 里的 idx 取某条请求的完整响应体（常用于读接口 JSON）。"""
    bt = await _get()
    body = await bt.get_body(idx)
    if body is None:
        return _j({"idx": idx, "error": "无内联响应体（可能非 XHR/fetch）"})
    return _j({"idx": idx, "body": body})


@mcp.tool()
async def set_interceptor(url_glob: str,
                          post_data: str | None = None,
                          headers: dict[str, str] | None = None) -> str:
    """对匹配 url_glob 的请求在发出前进行改写（浏览器本地的请求路由，不改动服务器）。
    可改 post_data（请求体）和/或 headers，用于接口调试、构造不同参数观察页面表现。例：
    set_interceptor('**/api/**', post_data='page=2')"""
    bt = await _get()
    modify: dict[str, Any] = {}
    if post_data is not None:
        modify["post_data"] = post_data
    if headers:
        modify["headers"] = headers
    await bt.set_interceptor(url_glob, modify)
    return _j({"ok": True, "glob": url_glob, "modify": list(modify)})


@mcp.tool()
async def mock_response(url_glob: str, body: str, status: int = 200,
                        content_type: str = "application/json") -> str:
    """本地模拟接口响应：匹配 url_glob 的请求不发到服务器，直接返回你给的 body。
    用于前后端联调、模拟各种返回状态或测试数据。例：
    mock_response('**/api/user', body='{"code":0,"data":{}}')"""
    bt = await _get()
    await bt.mock_response(url_glob, status=status, body=body, content_type=content_type)
    return _j({"ok": True, "glob": url_glob, "status": status})


@mcp.tool()
async def block_request(url_glob: str) -> str:
    """中断匹配的请求（页面会收到网络错误）。用于模拟接口不可用，或屏蔽某域名的资源加载。"""
    bt = await _get()
    await bt.block_request(url_glob)
    return _j({"ok": True, "glob": url_glob, "action": "abort"})


@mcp.tool()
async def replay_request(idx: int, post_data: str | None = None,
                         url: str | None = None, method: str | None = None,
                         extra_headers: dict[str, str] | None = None) -> str:
    """重新发送 list_traffic 中记录的某条请求，复用浏览器登录态(cookie)，
    可改 post_data/url/method/请求头，用于接口调试与结果验证。idx 来自 list_traffic。
    例：replay_request(7, post_data='{"page":2}')"""
    bt = await _get()
    r = await bt.replay_request(idx, method=method, url=url,
                                post_data=post_data, extra_headers=extra_headers)
    return _j(r)


@mcp.tool()
async def page_text() -> str:
    """取当前页面正文文本（截断到 8000 字）。"""
    bt = await _get()
    return _j({"url": bt.page.url, "text": await bt.get_text()})


@mcp.tool()
async def stop_browser(close_browser: bool = False) -> str:
    """断开与浏览器的连接。默认 close_browser=False：只断开、保留常驻浏览器和登录态
    （下次 start_browser 自动重连）。close_browser=True 才真正关闭浏览器进程
    （profile 登录态仍保存在磁盘，下次同 profile 恢复）。"""
    global _bt
    if _bt is not None:
        r = await _bt.stop(close_browser=close_browser)
        _bt = None
        return _j({"ok": True, **r})
    return _j({"ok": True, "note": "no active session"})


@mcp.tool()
async def get_action_log(last: int = 30) -> str:
    """查看本会话的操作记录（每个 navigate/click/fill/scroll 等动作一条，
    含时间、参数[密码已脱敏]、前后 URL、对应截图路径）。用于回顾操作过程。"""
    bt = await _get()
    return _j(bt.get_action_log(last=last))


@mcp.tool()
async def flush_trace() -> str:
    """把当前 Playwright trace 落盘为 trace.zip（可回放），并继续录制。
    回放命令：playwright show-trace <返回的路径>。可逐帧查看每步 DOM 快照/截图/网络/动作。"""
    bt = await _get()
    path = await bt.flush_trace()
    return _j({"trace": path,
               "replay": f"playwright show-trace {path}" if path else None})


if __name__ == "__main__":
    mcp.run()  # 默认 stdio，供 Claude Code / Codex 接入
