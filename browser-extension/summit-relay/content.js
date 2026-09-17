const ADAPTERS = {
  chatgpt: {
    host: "chatgpt.com",
    composer: ["#prompt-textarea", "textarea[data-id='root']"],
    send: ["button[data-testid='send-button']", "button[data-testid='composer-submit-button']"],
    stop: ["button[data-testid='stop-button']", "button[aria-label*='Stop' i]"],
    assistant: ["[data-message-author-role='assistant'] .markdown", "[data-message-author-role='assistant']"],
    authText: ["Log in", "Sign up"]
  },
  gemini: {
    host: "gemini.google.com",
    composer: ["rich-textarea .ql-editor[contenteditable='true']", ".ql-editor[contenteditable='true']", "[contenteditable='true'][aria-label*='prompt' i]"],
    send: ["button[aria-label*='Send message' i]", "button.send-button", ".send-button button"],
    stop: ["button[aria-label*='Stop' i]"],
    assistant: ["model-response .model-response-text", "model-response", ".model-response-text"],
    authText: ["Sign in"]
  },
  openwebui: {
    host: "localhost",
    composer: ["#chat-input", "textarea[placeholder*='message' i]", "[contenteditable='true'][data-placeholder]"],
    send: ["#send-message-button", "button[aria-label*='Send' i]"],
    stop: ["button[aria-label*='Stop' i]"],
    assistant: ["[data-message-role='assistant'] .prose", "[data-message-role='assistant']", ".assistant-message .prose", ".assistant-message"],
    authText: ["Sign in", "Log in"]
  }
};

function provider() {
  if (location.hostname === "chatgpt.com") return "chatgpt";
  if (location.hostname === "gemini.google.com") return "gemini";
  if (["localhost", "127.0.0.1"].includes(location.hostname) && location.port === "3000") return "openwebui";
  return null;
}

function first(selectors) {
  for (const selector of selectors) {
    const node = document.querySelector(selector);
    if (node) return node;
  }
  return null;
}

function assistantTexts(adapter) {
  for (const selector of adapter.assistant) {
    const nodes = [...document.querySelectorAll(selector)];
    const texts = nodes.map(node => (node.innerText || node.textContent || "").trim()).filter(Boolean);
    if (texts.length) return texts;
  }
  return [];
}

function visibleTextMatch(labels) {
  const candidates = [...document.querySelectorAll("a, button")];
  return candidates.some(node => {
    const text = (node.innerText || node.textContent || "").trim();
    const visible = node.getClientRects().length > 0;
    return visible && labels.includes(text);
  });
}

function setComposer(node, text) {
  node.focus();
  if (node instanceof HTMLTextAreaElement || node instanceof HTMLInputElement) {
    const prototype = node instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(prototype, "value").set;
    setter.call(node, text);
    node.dispatchEvent(new Event("input", {bubbles: true}));
    node.dispatchEvent(new Event("change", {bubbles: true}));
    return;
  }
  if (node.isContentEditable) {
    document.execCommand("selectAll", false, null);
    if (!document.execCommand("insertText", false, text)) node.textContent = text;
    node.dispatchEvent(new InputEvent("input", {bubbles: true, inputType: "insertText", data: text}));
    return;
  }
  throw new Error("composer_not_editable");
}

function sleep(milliseconds) {
  return new Promise(resolve => setTimeout(resolve, milliseconds));
}

async function waitForSend(adapter, timeoutMs) {
  const deadline = Date.now() + Math.min(timeoutMs, 15000);
  while (Date.now() < deadline) {
    const button = first(adapter.send);
    if (button && !button.disabled && button.getAttribute("aria-disabled") !== "true") return button;
    await sleep(250);
  }
  throw new Error("send_control_not_found");
}

async function waitForCompletedResponse(adapter, baseline, expected, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let candidate = "";
  let stableSince = 0;
  while (Date.now() < deadline) {
    const texts = assistantTexts(adapter);
    const latest = texts.length ? texts[texts.length - 1] : "";
    const changed = texts.length > baseline.count || (latest && latest !== baseline.latest);
    const generating = Boolean(first(adapter.stop));
    if (changed && latest) {
      if (latest !== candidate) {
        candidate = latest;
        stableSince = Date.now();
      }
      const exactReady = expected && latest === expected && !generating;
      const stableReady = !expected && !generating && Date.now() - stableSince >= 2500;
      if (exactReady || stableReady) return latest;
    }
    await sleep(500);
  }
  throw new Error("assistant_response_timeout");
}

async function runAction(action) {
  const name = provider();
  if (!name || action.worker !== ({chatgpt: "sophie", gemini: "bernie", openwebui: "josie"})[name]) {
    return {ok: false, error_code: "provider_mismatch", error_detail: "The designated tab does not match the requested worker."};
  }
  const adapter = ADAPTERS[name];
  if (visibleTextMatch(adapter.authText)) {
    return {ok: false, error_code: "authentication_required", error_detail: `${action.source} requires sign-in.`};
  }
  const composer = first(adapter.composer);
  if (!composer) {
    return {ok: false, error_code: "composer_not_found", error_detail: `No supported ${action.source} composer was found.`};
  }
  const before = assistantTexts(adapter);
  const baseline = {count: before.length, latest: before.length ? before[before.length - 1] : ""};
  try {
    setComposer(composer, action.payload);
    const send = await waitForSend(adapter, action.timeout_seconds * 1000);
    send.click();
    const text = await waitForCompletedResponse(
      adapter, baseline, action.expected_exact, action.timeout_seconds * 1000
    );
    return {ok: true, assistant_text: text};
  } catch (error) {
    return {ok: false, error_code: error.message || "dom_failure", error_detail: String(error).slice(0, 500)};
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || message.type !== "SUMMIT_RELAY_ACTION") return false;
  runAction(message.action).then(sendResponse).catch(error => sendResponse({
    ok: false, error_code: "content_script_failure", error_detail: String(error).slice(0, 500)
  }));
  return true;
});
