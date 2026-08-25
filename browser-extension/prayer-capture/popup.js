"use strict";

const captureButton = document.getElementById("capture");
const statusBox = document.getElementById("status");

function setStatus(message, kind = "") {
  statusBox.textContent = message;
  statusBox.className = kind;
}

function captureActiveSelection() {
  const selectedText = String(window.getSelection()?.toString() || "").trim();
  const visibleHeader = Array.from(document.querySelectorAll("header"))
    .map((element) => ({
      left: element.getBoundingClientRect().left,
      line: String(element.innerText || "").trim().split(/\r?\n/)[0]
    }))
    .filter((candidate) => candidate.line && candidate.line.length <= 160)
    .sort((a, b) => b.left - a.left)[0]?.line || "";
  return {
    url: location.href,
    title: String(document.title || "").slice(0, 300),
    header: visibleHeader,
    selected_text: selectedText,
    received_at: new Date().toISOString()
  };
}

captureButton.addEventListener("click", async () => {
  const config = globalThis.JOSIE_PRAYER_CONFIG;
  if (!config || !config.token || config.token === "LOCAL_TOKEN_GOES_HERE") {
    setStatus("Josie's local bridge has not been initialized.", "error");
    return;
  }
  captureButton.disabled = true;
  setStatus("Checking your selected text…");
  try {
    const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
    if (!tab?.id) throw new Error("No active browser tab was found.");
    const [execution] = await chrome.scripting.executeScript({
      target: {tabId: tab.id},
      func: captureActiveSelection
    });
    const payload = execution?.result;
    if (!payload?.selected_text) {
      throw new Error("Highlight the prayer request first, then click Capture.");
    }
    const response = await fetch(`${config.bridgeUrl}/intake`, {
      method: "POST",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        "X-Josie-Prayer-Token": config.token
      },
      body: JSON.stringify(payload)
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error("Josie rejected this page or capture. Confirm the approved conversation is open.");
    }
    setStatus(`Saved locally as prayer #${result.prayer_id}. No reply was sent.`, "success");
  } catch (error) {
    setStatus(error instanceof Error ? error.message : "The capture did not complete.", "error");
  } finally {
    captureButton.disabled = false;
  }
});
