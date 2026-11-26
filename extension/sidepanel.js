// Side panel: sends the active tab's rendered HTML to the local capture
// server (src/jobfit/ingest/capture/server.py), which does all the parsing,
// and shows everything it read. /previews reads without storing; /captures
// stores when Save is clicked. Re-reads when the tab switches or navigates
// (LinkedIn changes the URL when you click another job in the list).
const SERVER = "http://127.0.0.1:8765";
const START_HINT = "Start the server: uv run python -m jobfit.ingest.capture.server";
// LinkedIn updates the URL before it renders the newly selected job.
const RENDER_DELAY_MS = 1000;
// The first save loads the guard model; a preview should answer at once.
const TIMEOUT_MS = { "/previews": 15000, "/captures": 120000 };

const $ = (id) => document.getElementById(id);
let page = null;
let readCount = 0; // ignores answers to reads that a newer read replaced
let timer = null;

function show(text, kind = "") {
  $("message").textContent = text;
  $("message").className = kind;
}

function setField(id, value) {
  $(id).textContent = value || "not found";
  $(id).className = value ? "" : "missing";
}

async function readTab() {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab?.id || !/^https?:/.test(tab.url || "")) {
    throw new Error("Open a job posting in this tab.");
  }
  let results;
  try {
    results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => document.documentElement.outerHTML,
    });
  } catch {
    throw new Error("Can't read this page. Supported: LinkedIn job pages.");
  }
  return { url: tab.url, html: results[0].result };
}

async function post(path, body) {
  let response;
  try {
    response = await fetch(SERVER + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(TIMEOUT_MS[path]),
    });
  } catch (error) {
    if (error.name === "TimeoutError") {
      throw new Error(`No answer from ${SERVER} after ${TIMEOUT_MS[path] / 1000} s. ` +
        "Is another program using that port? " + START_HINT);
    }
    throw new Error("The jobfit capture server isn't running. " + START_HINT);
  }
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || `Server error ${response.status}`);
  return result;
}

function setStored(stored) {
  $("stored").innerHTML = stored ? '<span class="badge">already saved</span>' : "not yet";
}

function fill(fields) {
  setField("title", fields.title);
  setField("company", fields.company);
  setField("location", fields.location);
  setField("posted", fields.posted_at && fields.posted_at.slice(0, 10));
  setField("external_id", fields.external_id);
  $("url").textContent = fields.url;
  $("url").href = fields.url;
  setStored(fields.already_stored);
  $("chars").textContent = `${fields.description_chars.toLocaleString()} characters`;
  $("description").textContent = fields.description || "No description found.";
  $("description").className = fields.description ? "" : "missing";
  $("fields").hidden = false;
}

async function preview() {
  const id = ++readCount;
  $("save").disabled = true;
  show("Reading the page…");
  try {
    const tabPage = await readTab();
    const fields = await post("/previews", tabPage);
    if (id !== readCount) return;
    page = tabPage;
    fill(fields);
    $("save").disabled = false;
    show("");
  } catch (error) {
    if (id !== readCount) return;
    page = null;
    $("fields").hidden = true;
    show(error.message, "error");
  }
}

function previewSoon(delay = RENDER_DELAY_MS) {
  clearTimeout(timer);
  timer = setTimeout(preview, delay);
}

async function save() {
  $("save").disabled = true;
  show("Saving… (the first save loads the guard model, a few seconds)");
  try {
    const result = await post("/captures", page);
    if (result.status === "blocked") {
      show("Not saved: this company is on the blocklist.", "warn");
      return;
    }
    setStored(true);
    if (result.status === "already_stored") {
      show("Already saved earlier; marked as seen today.", "ok");
    } else if (result.quarantined) {
      show("Saved, but quarantined by the guard. Review it on the postings page.", "warn");
    } else if (result.duplicate) {
      show("Saved as a duplicate of a posting already stored.", "ok");
    } else {
      show("Saved.", "ok");
    }
  } catch (error) {
    $("save").disabled = false;
    show(error.message, "error");
  }
}

chrome.tabs.onActivated.addListener(() => previewSoon(0));
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (tab.active && (changeInfo.url || changeInfo.status === "complete")) previewSoon();
});
$("refresh").addEventListener("click", () => previewSoon(0));
$("save").addEventListener("click", save);
preview();
