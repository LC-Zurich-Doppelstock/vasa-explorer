// ---------------------------------------------------------------------------
// Markdown renderer — resolve from whichever way the UMD exposes it
// ---------------------------------------------------------------------------
const renderMarkdown = (function () {
    if (typeof marked === "function") return marked;
    if (typeof marked === "object" && typeof marked.parse === "function") return marked.parse;
    if (typeof marked === "object" && typeof marked.marked === "function") return marked.marked;
    console.error("marked library not found — markdown will render as plain text");
    return function (text) { return text; };
})();
console.log("renderMarkdown ready:", typeof renderMarkdown);

// ---------------------------------------------------------------------------
// DOM references
// ---------------------------------------------------------------------------
const chatEl = document.getElementById("chat");
const questionEl = document.getElementById("question");
const sendBtn = document.getElementById("send-btn");
const statusDot = document.getElementById("status-dot");
const welcomeHint = document.getElementById("welcome-hint");

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let sessionId = null;
let isLoading = false;

const DEFAULTS = {
    anthropic: "claude-sonnet-4-6",
    openai: "gpt-4o",
};

const KEY_HINTS = {
    anthropic: { placeholder: "sk-ant-...", text: "Your key is stored locally in your browser and sent directly to Anthropic." },
    openai:    { placeholder: "sk-...",     text: "Your key is stored locally in your browser and sent directly to OpenAI." },
};

let cachedModels = {};      // { provider: [...] }
let modalProvider = "anthropic"; // which tab is active in the modal
let serverKeyProvider = null;    // set if server has a key available

const SERVER_KEY_SENTINEL = "__server__";

// ---------------------------------------------------------------------------
// Per-provider localStorage helpers
// ---------------------------------------------------------------------------
function getProvider() {
    return localStorage.getItem("vasa_provider") || "anthropic";
}

function getApiKey(provider) {
    provider = provider || getProvider();
    const stored = localStorage.getItem("vasa_key_" + provider) || "";
    if (stored) return stored;
    if (provider === serverKeyProvider) return SERVER_KEY_SENTINEL;
    return "";
}

function getModel(provider) {
    provider = provider || getProvider();
    return localStorage.getItem("vasa_model_" + provider) || DEFAULTS[provider] || "";
}

// ---------------------------------------------------------------------------
// Settings modal — provider tabs
// ---------------------------------------------------------------------------
function switchProvider(provider) {
    modalProvider = provider;

    document.querySelectorAll(".provider-tab").forEach(tab => {
        tab.classList.toggle("active", tab.dataset.provider === provider);
    });

    const keyInput = document.getElementById("api-key-input");
    const storedKey = localStorage.getItem("vasa_key_" + provider) || "";
    keyInput.value = storedKey;
    keyInput.placeholder = KEY_HINTS[provider].placeholder;

    const hint = document.getElementById("key-hint");
    if (!storedKey && provider === serverKeyProvider) {
        hint.textContent = "A server-provided key is active. Enter your own key here to override it.";
    } else {
        hint.textContent = KEY_HINTS[provider].text;
    }

    fetchModels(provider, getApiKey(provider));
}

// ---------------------------------------------------------------------------
// Model fetching
// ---------------------------------------------------------------------------
async function fetchModels(provider, apiKey) {
    const select = document.getElementById("model-select");
    const status = document.getElementById("model-status");

    if (!apiKey) {
        select.innerHTML = '<option value="">Enter API key to load models</option>';
        select.disabled = true;
        status.textContent = "";
        cachedModels[provider] = [];
        return;
    }

    select.innerHTML = '<option value="">Loading models...</option>';
    select.disabled = true;
    status.textContent = "";

    try {
        const resp = await fetch("/api/models", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ api_key: apiKey, provider: provider }),
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || resp.statusText);
        }

        const data = await resp.json();
        const models = data.models || [];
        cachedModels[provider] = models;

        if (models.length === 0) {
            select.innerHTML = '<option value="">No models available</option>';
            select.disabled = true;
            return;
        }

        const savedModel = getModel(provider);
        select.innerHTML = models
            .map(m => `<option value="${m.id}" ${m.id === savedModel ? "selected" : ""}>${m.name} (${m.id})</option>`)
            .join("");
        select.disabled = false;

        if (!models.some(m => m.id === savedModel)) {
            select.selectedIndex = 0;
        }
    } catch (e) {
        select.innerHTML = '<option value="">Failed to load models</option>';
        select.disabled = true;
        status.textContent = e.message;
        status.style.color = "#ef4444";
    }
}

// ---------------------------------------------------------------------------
// Status dot
// ---------------------------------------------------------------------------
function updateStatusDot() {
    const provider = getProvider();
    const hasKey = !!getApiKey(provider);
    statusDot.classList.toggle("connected", hasKey);
    if (welcomeHint) {
        welcomeHint.textContent = hasKey
            ? "Try one of these examples:"
            : "Set up your API key in Settings to get started.";
    }
}

// ---------------------------------------------------------------------------
// Settings modal open / close / save
// ---------------------------------------------------------------------------
function openSettings() {
    modalProvider = getProvider();
    switchProvider(modalProvider);
    document.getElementById("settings-modal").classList.add("active");
}

function closeSettings() {
    document.getElementById("settings-modal").classList.remove("active");
}

function saveSettings() {
    const key = document.getElementById("api-key-input").value.trim();
    const select = document.getElementById("model-select");
    const model = select.value || DEFAULTS[modalProvider] || "";

    localStorage.setItem("vasa_key_" + modalProvider, key);
    localStorage.setItem("vasa_model_" + modalProvider, model);
    localStorage.setItem("vasa_provider", modalProvider);

    updateStatusDot();
    closeSettings();
}

// Debounced model fetch on key input
let fetchDebounce = null;
document.getElementById("api-key-input").addEventListener("input", () => {
    clearTimeout(fetchDebounce);
    fetchDebounce = setTimeout(() => {
        const key = document.getElementById("api-key-input").value.trim();
        fetchModels(modalProvider, key);
    }, 500);
});

// Close modal on overlay click
document.getElementById("settings-modal").addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closeSettings();
});

// ---------------------------------------------------------------------------
// Check server defaults on load
// ---------------------------------------------------------------------------
updateStatusDot();

(async function checkDefaults() {
    try {
        const resp = await fetch("/api/defaults");
        if (!resp.ok) return;
        const data = await resp.json();
        if (data.has_server_key && data.provider) {
            serverKeyProvider = data.provider;
            if (!localStorage.getItem("vasa_provider")) {
                localStorage.setItem("vasa_provider", data.provider);
            }
            if (!localStorage.getItem("vasa_model_" + data.provider) && data.model) {
                localStorage.setItem("vasa_model_" + data.provider, data.model);
            }
            updateStatusDot();
        }
    } catch (e) {
        // Server not reachable yet — user can configure manually
    }
})();

// ---------------------------------------------------------------------------
// Input handling
// ---------------------------------------------------------------------------
questionEl.addEventListener("input", () => {
    questionEl.style.height = "auto";
    questionEl.style.height = Math.min(questionEl.scrollHeight, 120) + "px";
});

questionEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendQuestion();
    }
});

function askExample(btn) {
    questionEl.value = btn.textContent;
    sendQuestion();
}

// ---------------------------------------------------------------------------
// Chat message rendering
// ---------------------------------------------------------------------------
function addMessage(role, text, image) {
    const welcome = chatEl.querySelector(".welcome");
    if (welcome) welcome.remove();

    const msg = document.createElement("div");
    msg.className = `message ${role}`;

    const label = document.createElement("div");
    label.className = "message-label";
    label.textContent = role === "user" ? "You" : "Gustav";

    const content = document.createElement("div");
    content.className = "message-content";

    if (role === "assistant") {
        content.innerHTML = renderMarkdown(text);
    } else {
        content.textContent = text;
    }

    if (image) {
        const img = document.createElement("img");
        img.src = image;
        img.alt = "Generated chart";
        content.appendChild(img);
    }

    msg.appendChild(label);
    msg.appendChild(content);
    chatEl.appendChild(msg);
    chatEl.scrollTop = chatEl.scrollHeight;
    return msg;
}

function addLoading() {
    const msg = document.createElement("div");
    msg.className = "message assistant";
    msg.id = "loading-msg";

    const label = document.createElement("div");
    label.className = "message-label";
    label.textContent = "Gustav";

    const content = document.createElement("div");
    content.className = "message-content loading";
    content.innerHTML = `Analyzing <span class="loading-dots"><span></span><span></span><span></span></span>`;

    msg.appendChild(label);
    msg.appendChild(content);
    chatEl.appendChild(msg);
    chatEl.scrollTop = chatEl.scrollHeight;
}

function removeLoading() {
    const el = document.getElementById("loading-msg");
    if (el) el.remove();
}

// ---------------------------------------------------------------------------
// Send question to backend
// ---------------------------------------------------------------------------
async function sendQuestion() {
    const text = questionEl.value.trim();
    if (!text || isLoading) return;

    const provider = getProvider();
    const apiKey = getApiKey(provider);
    const model = getModel(provider);

    if (!apiKey) {
        addMessage("assistant", "Please configure your API key in Settings first.");
        openSettings();
        return;
    }

    isLoading = true;
    sendBtn.disabled = true;
    questionEl.value = "";
    questionEl.style.height = "auto";

    addMessage("user", text);
    addLoading();

    try {
        const resp = await fetch("/api/ask", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                question: text,
                session_id: sessionId,
                api_key: apiKey,
                model: model,
                provider: provider,
            }),
        });

        removeLoading();

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            addMessage("assistant", `Error: ${err.detail || resp.statusText}`);
            return;
        }

        const data = await resp.json();
        sessionId = data.session_id;
        addMessage("assistant", data.text, data.image);
    } catch (e) {
        removeLoading();
        addMessage("assistant", `Connection error: ${e.message}`);
    } finally {
        isLoading = false;
        sendBtn.disabled = false;
        questionEl.focus();
    }
}
