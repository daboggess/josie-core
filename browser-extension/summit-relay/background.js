importScripts("config.js");

const config = globalThis.JOSIE_SUMMIT_CONFIG;
const POLL_ALARM = "summit-relay-poll";
let busy = false;
let timer = null;

function schedule(delay = config.pollIntervalMs) {
  if (timer !== null) clearTimeout(timer);
  timer = setTimeout(poll, delay);
}

async function bridge(path, options = {}) {
  const response = await fetch(`${config.bridgeUrl}${path}`, {
    cache: "no-store",
    ...options,
    headers: {
      "X-Josie-Summit-Token": config.token,
      ...(options.body ? {"Content-Type": "application/json"} : {}),
      ...(options.headers || {})
    }
  });
  if (!response.ok) throw new Error(`bridge_http_${response.status}`);
  return response.json();
}

async function reportFailure(action, code, detail, tab = null) {
  const payload = {
    action_id: action.action_id,
    ok: false,
    assistant_text: "",
    tab_id: tab ? tab.id : null,
    page_url: tab && tab.url ? tab.url : "",
    page_title: tab && tab.title ? tab.title : "",
    error_code: code,
    error_detail: String(detail || "").slice(0, 500)
  };
  await bridge("/result", {method: "POST", body: JSON.stringify(payload)});
}

async function execute(action) {
  const allTabs = await chrome.tabs.query({});
const matches = allTabs.filter(tab =>
  action.url_patterns.some(pattern => {
    const prefix = pattern.endsWith("*") ? pattern.slice(0, -1) : pattern;
    return tab.url && tab.url.startsWith(prefix);
  })
);
  const tabs = matches.filter(tab => tab.id && tab.url);
  if (tabs.length !== 1) {
    await reportFailure(
      action,
      tabs.length === 0 ? "designated_tab_unavailable" : "designated_tab_ambiguous",
      `Expected exactly one ${action.worker} tab; found ${tabs.length}.`
    );
    return;
  }
  const tab = tabs[0];
  let result;
  try {
    result = await chrome.tabs.sendMessage(tab.id, {type: "SUMMIT_RELAY_ACTION", action});
  } catch (error) {
    await reportFailure(action, "content_bridge_unavailable", error.message, tab);
    return;
  }
  if (!result || result.ok !== true) {
    await reportFailure(
      action,
      result && result.error_code ? result.error_code : "invalid_content_result",
      result && result.error_detail ? result.error_detail : "The page returned no valid result.",
      tab
    );
    return;
  }
  await bridge("/result", {
    method: "POST",
    body: JSON.stringify({
      action_id: action.action_id,
      ok: true,
      assistant_text: result.assistant_text,
      tab_id: tab.id,
      page_url: tab.url || "",
      page_title: tab.title || "",
      error_code: "",
      error_detail: ""
    })
  });
}

async function poll() {
  if (busy) return schedule();
  busy = true;
  try {
    const message = await bridge("/next");
    if (message.status === "action" && message.action) {
      await execute(message.action);
    }
  } catch (_) {
    // The local service being stopped is normal. No cloud fallback is allowed.
  } finally {
    busy = false;
    schedule();
  }
}

async function ensureAlarm() {
  await chrome.alarms.create(POLL_ALARM, {
    delayInMinutes: 0.05,
    periodInMinutes: 0.5
  });
}

chrome.alarms.onAlarm.addListener(alarm => {
  if (alarm.name === POLL_ALARM) poll();
});
chrome.runtime.onInstalled.addListener(() => { ensureAlarm(); schedule(250); });
chrome.runtime.onStartup.addListener(() => { ensureAlarm(); schedule(250); });
ensureAlarm();
schedule(250);
