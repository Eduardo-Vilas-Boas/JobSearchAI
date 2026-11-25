// Sends the open tab's rendered HTML to the local capture server
// (src/jobfit/ingest/capture/server.py), which does all the parsing: first
// /previews to show what it read, then /captures when Save is clicked.
const SERVER = "http://127.0.0.1:8765";
const START_HINT = "Start the server: uv run python -m jobfit.ingest.capture.server";

const $ = (id) => document.getElementById(id);
let page = null;

function show(text, kind = "") {
  $("message").textContent = text;
  $("message").className = kind;
}

async function readTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const [{ result: html }] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => document.documentElement.outerHTML,
  });
  return { url: tab.url, html };
}

async function post(path) {
  let response;
  try {
    response = await fetch(SERVER + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(page),
    });
  } catch {
    throw new Error("The jobfit capture server isn't running. " + START_HINT);
  }
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || `Server error ${response.status}`);
  return body;
}

function fill(fields) {
  $("title").textContent = fields.title || "—";
  $("company").textContent = fields.company || "—";
  $("location").textContent = fields.location || "—";
  $("posted").textContent = fields.posted_at ? fields.posted_at.slice(0, 10) : "—";
  if (fields.description_chars !== undefined) {
    $("description").textContent = `${fields.description_chars.toLocaleString()} characters`;
  }
  $("fields").hidden = false;
}

async function preview() {
  try {
    page = await readTab();
    fill(await post("/previews"));
    $("save").disabled = false;
    show("");
  } catch (error) {
    show(error.message, "error");
  }
}

async function save() {
  $("save").disabled = true;
  show("Saving… (the first save loads the guard model, a few seconds)");
  try {
    const result = await post("/captures");
    fill(result);
    if (result.status === "blocked") {
      show("Not saved: this company is on the blocklist.", "warn");
    } else if (result.status === "already_stored") {
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

$("save").addEventListener("click", save);
preview();
