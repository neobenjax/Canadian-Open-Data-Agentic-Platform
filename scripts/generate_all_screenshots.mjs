import puppeteer from 'puppeteer-core';
import path from 'path';

const chromePath = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const targetUrl = 'http://localhost:6274/?MCP_PROXY_AUTH_TOKEN=5ec1563517a5c7435eb2bde5b51522c0e54694667862849383209bc8de0b494c';
const uvExe = 'C:\\Users\\besaz\\.local\\bin\\uv.exe';
const projectDir = 'D:\\AI\\PARTY PROJECTS\\AI Engineer - Collaboration';

async function fillField(page, selector, text) {
  await page.waitForSelector(selector, { timeout: 4000 });
  await page.click(selector);
  await page.keyboard.down('Control');
  await page.keyboard.press('A');
  await page.keyboard.up('Control');
  await page.keyboard.press('Backspace');
  await page.type(selector, text);
}

async function main() {
  console.log('🚀 Starting Anthropic MCP Inspector Test & Screenshot Automation...');
  const browser = await puppeteer.launch({
    executablePath: chromePath,
    headless: true,
    args: ['--no-sandbox', '--window-size=1600,1050'],
    defaultViewport: { width: 1600, height: 1050 }
  });
  const page = await browser.newPage();
  await page.goto(targetUrl, { waitUntil: 'networkidle2' });

  await page.waitForSelector('#command-input');
  await page.evaluate((cmd, dir) => {
    const setReactInput = (selector, val) => {
      const input = document.querySelector(selector);
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(input, val);
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
    };
    setReactInput('#command-input', cmd);
    setReactInput('#arguments-input', `run --directory "${dir}" python -m candata_mcp`);
  }, uvExe, projectDir);

  // Connect
  await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'));
    const c = btns.find(b => b.innerText?.trim() === 'Connect');
    if (c) c.click();
  });

  await page.waitForFunction(() => document.body.innerText.includes('candata-mcp'), { timeout: 15000 });
  await new Promise(r => setTimeout(r, 2000));
  console.log('✅ Connected to CanData-MCP FastMCP server!');

  // Navigate to Tools tab
  const tabButtons = await page.$$('button[role="tab"]');
  for (const tab of tabButtons) {
    const text = await page.evaluate(el => el.innerText?.trim(), tab);
    if (text === 'Tools') {
      await tab.click();
      break;
    }
  }
  await new Promise(r => setTimeout(r, 1000));

  // Click List Tools
  const listToolsBtn = await page.evaluateHandle(() => {
    return Array.from(document.querySelectorAll('button')).find(b => b.innerText?.trim() === 'List Tools');
  });
  if (listToolsBtn) await listToolsBtn.asElement().click();
  await new Promise(r => setTimeout(r, 1500));

  // -------------------------------------------------------------
  // Screenshot 1: Tools Catalog Overview
  // -------------------------------------------------------------
  const shot1 = path.resolve('docs/assets/screenshots/01_mcp_inspector_tools_catalog.png');
  await page.screenshot({ path: shot1 });
  console.log('📸 [1/4] Saved Tools Catalog Overview:', shot1);

  // -------------------------------------------------------------
  // Test 1: Run query_valet_policy_rate
  // -------------------------------------------------------------
  console.log('🧪 Testing query_valet_policy_rate...');
  await page.evaluate(() => {
    const all = Array.from(document.querySelectorAll('*'));
    const item = all.find(e => e.innerText?.trim() === 'query_valet_policy_rate');
    if (item) item.click();
  });
  await new Promise(r => setTimeout(r, 1000));

  // Set limit = 3
  await fillField(page, '#limit', '3');

  // Click Run Tool
  await page.evaluate(() => {
    const runBtn = Array.from(document.querySelectorAll('button')).find(b => b.innerText?.trim() === 'Run Tool');
    if (runBtn) runBtn.click();
  });

  console.log('Waiting for query_valet_policy_rate execution...');
  await new Promise(r => setTimeout(r, 4000));

  const shot2 = path.resolve('docs/assets/screenshots/02_mcp_inspector_query_policy_rate.png');
  await page.screenshot({ path: shot2 });
  console.log('📸 [2/4] Saved Policy Rate Tool Result:', shot2);

  // -------------------------------------------------------------
  // Test 2: Run execute_sql_analytics
  // -------------------------------------------------------------
  console.log('🧪 Testing execute_sql_analytics (DuckDB SQL Math)...');
  await page.evaluate(() => {
    const all = Array.from(document.querySelectorAll('*'));
    const item = all.find(e => e.innerText?.trim() === 'execute_sql_analytics');
    if (item) item.click();
  });
  await new Promise(r => setTimeout(r, 1000));

  await fillField(page, '#source', 'valet');
  await fillField(page, '#series_id', 'V39079');
  await fillField(page, '#sql_query', 'SELECT count(*) AS total_obs, avg(value) AS avg_rate FROM series');

  // Click Run Tool
  await page.evaluate(() => {
    const runBtn = Array.from(document.querySelectorAll('button')).find(b => b.innerText?.trim() === 'Run Tool');
    if (runBtn) runBtn.click();
  });

  console.log('Waiting for execute_sql_analytics execution...');
  await new Promise(r => setTimeout(r, 4000));

  const shot3 = path.resolve('docs/assets/screenshots/03_mcp_inspector_execute_sql_analytics.png');
  await page.screenshot({ path: shot3 });
  console.log('📸 [3/4] Saved DuckDB SQL Analytics Result:', shot3);

  // -------------------------------------------------------------
  // Test 3: Run query_statcan_vector
  // -------------------------------------------------------------
  console.log('🧪 Testing query_statcan_vector...');
  await page.evaluate(() => {
    const all = Array.from(document.querySelectorAll('*'));
    const item = all.find(e => e.innerText?.trim() === 'query_statcan_vector');
    if (item) item.click();
  });
  await new Promise(r => setTimeout(r, 1000));

  await fillField(page, '#vector_id', 'v41690973');
  await fillField(page, '#limit', '3');

  // Click Run Tool
  await page.evaluate(() => {
    const runBtn = Array.from(document.querySelectorAll('button')).find(b => b.innerText?.trim() === 'Run Tool');
    if (runBtn) runBtn.click();
  });

  console.log('Waiting for query_statcan_vector execution...');
  await new Promise(r => setTimeout(r, 5000));

  const shot4 = path.resolve('docs/assets/screenshots/04_mcp_inspector_query_statcan_vector.png');
  await page.screenshot({ path: shot4 });
  console.log('📸 [4/4] Saved StatCan Vector Result:', shot4);

  console.log('🎉 All MCP Inspector showcase screenshots generated successfully!');
  await browser.close();
}

main().catch(err => {
  console.error('Automation error:', err);
  process.exit(1);
});
