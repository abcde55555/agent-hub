#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { chromium } from "playwright";

// State management
let browserInstance = null;
let contextInstance = null;
let activePage = null;
const pages = new Map();

async function getOrLaunchBrowser() {
  if (!browserInstance || !browserInstance.isConnected()) {
    const headless = process.env.BROWSER_HEADLESS !== "false";
    const launchOptions = {
      headless,
      args: ["--no-sandbox", "--disable-setuid-sandbox"],
    };
    const macChrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
    if (fs.existsSync(macChrome)) {
      launchOptions.executablePath = macChrome;
    }
    browserInstance = await chromium.launch(launchOptions);
    contextInstance = await browserInstance.newContext({
      viewport: { width: 1280, height: 800 },
    });
  }
  return { browser: browserInstance, context: contextInstance };
}

async function getActivePage() {
  const { context } = await getOrLaunchBrowser();
  if (!activePage || activePage.isClosed()) {
    activePage = await context.newPage();
    const id = `tab_${Date.now()}`;
    pages.set(id, activePage);
  }
  return activePage;
}

const server = new Server(
  {
    name: "standalone-browser-mcp",
    version: "1.0.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

// Define tool schemas
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: "browser_navigate",
        description: "Navigate active browser page to a specific URL and wait for DOM content to load.",
        inputSchema: {
          type: "object",
          properties: {
            url: { type: "string", description: "Target URL (http/https)" },
            waitUntil: {
              type: "string",
              enum: ["domcontentloaded", "load", "networkidle"],
              default: "domcontentloaded",
            },
          },
          required: ["url"],
        },
      },
      {
        name: "browser_snapshot",
        description: "Capture the AI/ARIA accessibility tree snapshot of the current page as ground truth for element locators.",
        inputSchema: {
          type: "object",
          properties: {
            interestingOnly: { type: "boolean", default: true },
          },
        },
      },
      {
        name: "browser_click",
        description: "Click an element located by role, text, label, placeholder, or CSS/XPath selector.",
        inputSchema: {
          type: "object",
          properties: {
            role: { type: "string", description: "ARIA role like 'button', 'link', 'checkbox'" },
            name: { type: "string", description: "Accessible name / button text / link text" },
            text: { type: "string", description: "Exact or partial text" },
            selector: { type: "string", description: "CSS or XPath selector" },
            timeoutMs: { type: "number", default: 5000 },
          },
        },
      },
      {
        name: "browser_type",
        description: "Fill or type text into an input or textarea element.",
        inputSchema: {
          type: "object",
          properties: {
            text: { type: "string", description: "Text content to input" },
            role: { type: "string", description: "Role, usually 'textbox'" },
            name: { type: "string", description: "Accessible name or placeholder" },
            selector: { type: "string", description: "CSS or XPath selector" },
            clearFirst: { type: "boolean", default: true },
          },
          required: ["text"],
        },
      },
      {
        name: "browser_screenshot",
        description: "Capture a screenshot of the visible viewport or full page.",
        inputSchema: {
          type: "object",
          properties: {
            fullPage: { type: "boolean", default: false },
            filePath: { type: "string", description: "Optional local file path to save the screenshot" },
          },
        },
      },
      {
        name: "browser_tabs",
        description: "List, create, or switch browser tabs.",
        inputSchema: {
          type: "object",
          properties: {
            action: { type: "string", enum: ["list", "new", "switch", "close"], default: "list" },
            tabId: { type: "string", description: "Target tab ID for switch or close" },
            url: { type: "string", description: "Initial URL for new tab" },
          },
        },
      },
      {
        name: "browser_exec_js",
        description: "Execute custom JavaScript in the browser context or page runner.",
        inputSchema: {
          type: "object",
          properties: {
            code: { type: "string", description: "JavaScript code snippet to execute" },
          },
          required: ["code"],
        },
      },
      {
        name: "browser_close",
        description: "Close the browser and clean up all resources.",
        inputSchema: {
          type: "object",
          properties: {},
        },
      },
    ],
  };
});

// Handle tool execution
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  try {
    if (name === "browser_navigate") {
      const page = await getActivePage();
      const waitUntil = args.waitUntil || "domcontentloaded";
      await page.goto(args.url, { waitUntil, timeout: 30000 });
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify({
              status: "success",
              url: page.url(),
              title: await page.title(),
            }),
          },
        ],
      };
    }

    if (name === "browser_snapshot") {
      const page = await getActivePage();
      let snapshotText = "";
      if (typeof page.ariaSnapshot === "function") {
        snapshotText = await page.ariaSnapshot();
      } else if (page.accessibility?.snapshot) {
        const snapshot = await page.accessibility.snapshot({
          interestingOnly: args.interestingOnly !== false,
        });
        snapshotText = JSON.stringify(snapshot, null, 2);
      } else {
        snapshotText = await page.locator("body").ariaSnapshot();
      }
      return {
        content: [
          {
            type: "text",
            text: snapshotText,
          },
        ],
      };
    }

    if (name === "browser_click") {
      const page = await getActivePage();
      let locator = null;
      if (args.role) {
        locator = page.getByRole(args.role, args.name ? { name: args.name } : undefined);
      } else if (args.name) {
        locator = page.getByRole("button", { name: args.name }).or(page.getByText(args.name));
      } else if (args.text) {
        locator = page.getByText(args.text);
      } else if (args.selector) {
        locator = page.locator(args.selector);
      } else {
        throw new Error("Must provide one of: role, name, text, or selector");
      }
      await locator.first().click({ timeout: args.timeoutMs || 5000 });
      return {
        content: [{ type: "text", text: JSON.stringify({ status: "success", action: "clicked" }) }],
      };
    }

    if (name === "browser_type") {
      const page = await getActivePage();
      let locator = null;
      if (args.role) {
        locator = page.getByRole(args.role, args.name ? { name: args.name } : undefined);
      } else if (args.name) {
        locator = page.getByPlaceholder(args.name).or(page.getByLabel(args.name));
      } else if (args.selector) {
        locator = page.locator(args.selector);
      } else {
        locator = page.locator("input:focus, textarea:focus");
      }
      if (args.clearFirst !== false) {
        await locator.first().fill(args.text, { timeout: 5000 });
      } else {
        await locator.first().type(args.text, { timeout: 5000 });
      }
      return {
        content: [{ type: "text", text: JSON.stringify({ status: "success", action: "typed" }) }],
      };
    }

    if (name === "browser_screenshot") {
      const page = await getActivePage();
      const dir = path.resolve(process.cwd(), "screenshots");
      if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
      const filename = args.filePath || path.join(dir, `screenshot_${Date.now()}.png`);
      const buffer = await page.screenshot({
        fullPage: Boolean(args.fullPage),
        path: filename,
      });
      const base64 = buffer.toString("base64");
      return {
        content: [
          {
            type: "text",
            text: `Browser screenshot saved to: ${filename}`,
          },
          {
            type: "image",
            data: base64,
            mimeType: "image/png",
          },
        ],
      };
    }

    if (name === "browser_tabs") {
      const action = args.action || "list";
      const { context } = await getOrLaunchBrowser();
      if (action === "list") {
        const list = context.pages().map((p, idx) => ({
          index: idx,
          url: p.url(),
          isCurrent: p === activePage,
        }));
        return { content: [{ type: "text", text: JSON.stringify(list, null, 2) }] };
      }
      if (action === "new") {
        activePage = await context.newPage();
        if (args.url) await activePage.goto(args.url);
        return { content: [{ type: "text", text: JSON.stringify({ status: "created", url: activePage.url() }) }] };
      }
      if (action === "switch") {
        const pagesList = context.pages();
        const target = pagesList[Number(args.tabId)] || pagesList[0];
        if (target) {
          activePage = target;
          await activePage.bringToFront();
          return { content: [{ type: "text", text: JSON.stringify({ status: "switched", url: activePage.url() }) }] };
        }
      }
    }

    if (name === "browser_exec_js") {
      const page = await getActivePage();
      const fn = new Function("page", "browser", "context", `return (async () => { ${args.code} })();`);
      const result = await fn(page, browserInstance, contextInstance);
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify({ status: "success", result: result ?? null }, null, 2),
          },
        ],
      };
    }

    if (name === "browser_close") {
      if (browserInstance) {
        await browserInstance.close();
        browserInstance = null;
        contextInstance = null;
        activePage = null;
        pages.clear();
      }
      return { content: [{ type: "text", text: JSON.stringify({ status: "closed" }) }] };
    }

    throw new Error(`Unknown tool: ${name}`);
  } catch (err) {
    return {
      content: [{ type: "text", text: JSON.stringify({ error: err.message, stack: err.stack }) }],
      isError: true,
    };
  }
});

const transport = new StdioServerTransport();
await server.connect(transport);
