const chatWindow = document.getElementById("chat-window");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const drawerToggle = document.getElementById("drawer-toggle");
const sidebar = document.getElementById("sidebar");
const nameGate = document.getElementById("name-gate");
const nameForm = document.getElementById("name-form");
const nameInput = document.getElementById("name-input");

const SESSION_ID = "web-session-" + Math.random().toString(36).slice(2, 10);
const NAME_KEY = "kisanDostFarmerName";

// ---------------------------------------------------------------------------
// Chat messages
// ---------------------------------------------------------------------------

function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// A small, dependency-free markdown-lite renderer for bot replies: handles
// **bold**, *italic*, "- " / "* " bullet lists, "1. " numbered lists, and
// blank-line paragraph breaks. Everything is HTML-escaped first, so the
// model's own text can never inject markup.
function renderMarkdown(text) {
  const lines = escapeHtml(text).split(/\r?\n/);
  let html = "";
  let listType = null;
  let paragraphBuffer = [];

  function inline(str) {
    str = str.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    str = str.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
    return str;
  }

  function flushParagraph() {
    if (paragraphBuffer.length) {
      html += `<p>${paragraphBuffer.join("<br>")}</p>`;
      paragraphBuffer = [];
    }
  }

  function closeList() {
    if (listType) {
      html += `</${listType}>`;
      listType = null;
    }
  }

  for (const rawLine of lines) {
    const line = rawLine.trim();
    const ulMatch = line.match(/^[-*]\s+(.*)/);
    const olMatch = line.match(/^\d+\.\s+(.*)/);

    if (ulMatch) {
      flushParagraph();
      if (listType !== "ul") {
        closeList();
        html += "<ul>";
        listType = "ul";
      }
      html += `<li>${inline(ulMatch[1])}</li>`;
    } else if (olMatch) {
      flushParagraph();
      if (listType !== "ol") {
        closeList();
        html += "<ol>";
        listType = "ol";
      }
      html += `<li>${inline(olMatch[1])}</li>`;
    } else if (line === "") {
      closeList();
      flushParagraph();
    } else {
      closeList();
      paragraphBuffer.push(inline(line));
    }
  }
  closeList();
  flushParagraph();
  return html;
}

function addMessage(text, sender, isError = false) {
  const row = document.createElement("div");
  row.className = `message ${sender}${isError ? " error" : ""}`;

  const bubble = document.createElement("div");
  bubble.className = "bubble";

  if (sender === "bot" && !isError) {
    bubble.classList.add("rich");
    bubble.innerHTML = renderMarkdown(text);
  } else {
    bubble.textContent = text;
  }

  row.appendChild(bubble);
  chatWindow.appendChild(row);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

async function sendMessage(message) {
  addMessage(message, "user");
  updateFarmPanel(message);

  chatInput.disabled = true;
  const submitButton = chatForm.querySelector("button");
  submitButton.disabled = true;

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, session_id: SESSION_ID }),
    });

    if (!response.ok) {
      throw new Error(`Server returned ${response.status}`);
    }

    const data = await response.json();
    addMessage(data.reply, "bot");
  } catch (err) {
    addMessage(
      "Connection error — make sure the server is running (uvicorn app:app --reload).",
      "bot",
      true
    );
    console.error(err);
  } finally {
    chatInput.disabled = false;
    submitButton.disabled = false;
    chatInput.focus();
  }
}

chatForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const message = chatInput.value.trim();
  if (!message) return;
  chatInput.value = "";
  sendMessage(message);
});

// ---------------------------------------------------------------------------
// Quick-ask chips — fill and send in one tap
// ---------------------------------------------------------------------------

document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    const prompt = chip.getAttribute("data-prompt");
    if (!prompt) return;
    sendMessage(prompt);
    if (window.innerWidth <= 780) closeDrawer();
  });
});

// ---------------------------------------------------------------------------
// Mobile drawer toggle
// ---------------------------------------------------------------------------

function closeDrawer() {
  sidebar.classList.remove("open");
  drawerToggle.setAttribute("aria-expanded", "false");
}

drawerToggle.addEventListener("click", () => {
  const isOpen = sidebar.classList.toggle("open");
  drawerToggle.setAttribute("aria-expanded", String(isOpen));
});

// ---------------------------------------------------------------------------
// Name gate — now asks EVERY time the page loads/refreshes (not just once),
// and always greets using whatever name is typed into the overlay that
// visit. The name is still saved to localStorage in case you want to reuse
// it elsewhere, but it is no longer used to skip the overlay.
// ---------------------------------------------------------------------------

function initNameGate() {
  nameGate.classList.remove("hidden");
  nameInput.focus();
}

nameForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const name = nameInput.value.trim();
  if (!name) return;
  localStorage.setItem(NAME_KEY, name);
  nameGate.classList.add("hidden");
  sendMessage(`My name is ${name}.`);
});

initNameGate();

// ---------------------------------------------------------------------------
// Lightweight client-side heuristic to auto-fill the "Your farm" panel.
// This is a cosmetic best-effort guess from keywords in what the farmer
// typed — it does not call the backend and won't always be right.
// ---------------------------------------------------------------------------

const DISTRICTS = [
  "multan", "lahore", "faisalabad", "sialkot", "gujranwala", "bahawalpur",
  "sargodha", "sahiwal", "rahim yar khan", "dera ghazi khan", "hyderabad",
  "karachi", "sukkur", "larkana", "peshawar", "mardan", "quetta", "khanewal",
];
const SEASONS = { rabi: "Rabi", kharif: "Kharif" };
const WATER_TERMS = ["low water", "kam pani", "no water", "less water", "high water", "ziada pani"];

function setField(name, value) {
  const el = document.querySelector(`[data-field="${name}"]`);
  if (!el || !value) return;
  el.textContent = value;
  el.classList.add("filled");
}

function updateFarmPanel(message) {
  const lower = message.toLowerCase();

  const district = DISTRICTS.find((d) => lower.includes(d));
  if (district) {
    setField("district", district.replace(/\b\w/g, (c) => c.toUpperCase()));
  }

  const seasonKey = Object.keys(SEASONS).find((s) => lower.includes(s));
  if (seasonKey) {
    setField("season", SEASONS[seasonKey]);
  }

  const waterTerm = WATER_TERMS.find((t) => lower.includes(t));
  if (waterTerm) {
    setField("water", waterTerm.includes("low") || waterTerm.includes("kam") ? "Low" : "High");
  }

  const acreMatch = lower.match(/(\d+(\.\d+)?)\s*acres?/);
  if (acreMatch) {
    setField("land", `${acreMatch[1]} acres`);
  }
}
