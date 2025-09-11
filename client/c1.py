# /mnt/data/c1.py
import streamlit as st
import streamlit.components.v1 as components
import json
import secrets
import os
from datetime import datetime

st.set_page_config(page_title="Secure Chat (Multiuser)", layout="wide")
st.title("Anonymous Chat — Encrypted Messaging")

# ---------- Controls ----------
col1, col2, col3 = st.columns([2, 1, 1])

# Friendly name list
FRIENDLY = ["John", "Bob", "Maya", "Liam", "Ava", "Noah", "Zara", "Ishaan", "Rina", "Leo"]

with col1:
    username_input = st.text_input("Username (leave blank to auto-generate)", value="")
with col2:
    pick = st.selectbox("Pick a friendly name (or Random)", options=["Random"] + FRIENDLY, index=0)
with col3:
    dark_mode = st.checkbox("Dark mode", value=True)

anonymous = st.checkbox("Anonymous label", value=False)

# Server WebSocket base URL - hidden input (no UI), fall back to env or default Render address
default_ws_url = os.getenv("WS_SERVER_URL", "wss://chat-app-4b0u.onrender.com")
ws_base_url = default_ws_url  # not shown to user

# Build a stable WebSocket username for this browser session so settings changes don't create a new user
if "ws_username" not in st.session_state:
    # Use an opaque stable connection id; visible name is handled via label
    st.session_state.ws_username = f"user-{secrets.token_hex(4)}"

# Always use the stable session username for the connection
username = st.session_state.ws_username
if anonymous:
    anon_label = st.text_input("Anonymous label (optional)", value=f"Anon-{secrets.token_hex(3)}")
else:
    anon_label = None

# Display label should reflect exactly what the user typed if provided; else the selected friendly name; else a fallback
if "display_label" not in st.session_state:
    st.session_state.display_label = username_input.strip() or (pick if pick != "Random" else "Guest")
else:
    st.session_state.display_label = username_input.strip() or (pick if pick != "Random" else st.session_state.display_label)

display_label = (anon_label if anonymous else st.session_state.display_label)

st.info("🔒 Using server-provided strong passphrase for encryption")
st.markdown("---")

# ---------- HTML/JS template ----------
html_template = """
<style>
:root {
  --bg: #ffffff;
  --panel: #f6f6f8;
  --text: #111827;
  --muted: #6b7280;
  --bubble-sent: #dcf8c6;
  --bubble-recv: #ffffff;
  --bubble-sent-text: #111827;
  --bubble-recv-text: #111827;
  --accent: #3b82f6;
}
.dark {
  --bg: #0b1220;
  --panel: #0f1724;
  --text: #e6eef8;
  --muted: #9aa8bf;
  --bubble-sent: #0b94ff33; /* translucent accent */
  --bubble-recv: #0b122633;
  --bubble-sent-text: #ffffff;
  --bubble-recv-text: #e6eef8;
  --accent: #0ea5e9;
}
body { background: var(--bg); color: var(--text); font-family: Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial; }
.container { display:flex; gap:16px; padding:12px; height:640px; box-sizing:border-box; }
.left { flex:1; display:flex; flex-direction:column; }
.right { width:300px; border-left:1px solid rgba(100,100,100,0.08); padding-left:12px; box-sizing:border-box; }
.header { font-weight:600; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center; }
.chatbox { flex:1; background:var(--panel); padding:12px; border-radius:8px; overflow:auto; display:flex; flex-direction:column; gap:8px; }
.input-row { display:flex; gap:8px; margin-top:8px; align-items:center; }
.text-input { flex:1; padding:10px 12px; border-radius:8px; border:1px solid rgba(0,0,0,0.08); background:transparent; color:#000 !important; }
.send-btn { padding:10px 14px; border-radius:8px; border:none; background:var(--accent); color:white; cursor:pointer; }
.user-item { padding:6px 8px; cursor:pointer; border-radius:6px; margin-bottom:6px; }
.user-item:hover { background: rgba(0,0,0,0.03); }
.chat-bubble { max-width:75%; padding:10px 12px; border-radius:16px; box-shadow: 0 1px 0 rgba(0,0,0,0.03); display:inline-block; word-break:break-word; }
.bubble-row { display:flex; gap:8px; align-items:flex-end; }
.bubble-left { justify-content:flex-start; }
.bubble-right { justify-content:flex-end; align-self:flex-end; }
.meta { font-size:11px; color:var(--muted); margin-top:4px; }
.ts { font-size:11px; color:var(--muted); margin-left:6px; }
.sender-name { font-weight:600; font-size:12px; margin-bottom:4px; color:var(--muted); }
/* Active chat buttons as rounded red bubbles */
#active-chats button { background:#ef4444; color:#fff; border:none; border-radius:9999px; padding:8px 12px; cursor:pointer; }
#active-chats button:hover { filter:brightness(0.95); }
/* Live users title as multicolour red bubbly rounded box */
.live-title { display:inline-block; padding:6px 12px; border-radius:9999px; color:#fff; background:linear-gradient(90deg, #dc2626, #ef4444, #f87171); }
/* Live users entries as red rounded boxes */
.user-item { background:#ef4444; color:#fff; border:none; border-radius:9999px; padding:8px 12px; margin-bottom:6px; }
.user-item:hover { background:#dc2626; }
</style>

<div id="root" class="__THEME__" style="background:var(--bg);">
  <div class="container">
    <div class="right">
      <h4 class="live-title" style="margin-top:0">Live users</h4>
      <div id="userlist" style="font-family:monospace; white-space:pre-wrap; max-height:300px; overflow-y:auto;"></div>

      <div style="margin-top:12px;">
        <div><strong>Active chats:</strong></div>
        <div id="active-chats" style="margin-top:8px; max-height:200px; overflow-y:auto;"></div>
      </div>
    </div>
    <div class="left">
      <div class="header">
        <div>Chat with: <span id="current-peer">Select a user</span></div>
        <div style="font-size:13px; color:var(--muted)">You: <strong id="me">{me_display}</strong></div>
      </div>
      <div id="chatbox" class="chatbox"></div>
      <div class="input-row">
        <input id="out" class="text-input" placeholder="Type a message and press Enter" />
        <button id="send" class="send-btn">Send</button>
      </div>
      <div id="status" style="color:var(--muted); margin-top:8px;"></div>
    </div>
  </div>
</div>

<script>
const username = __USERNAME__;
const anonymous = __ANON__;
const anon_label = __ANON_LABEL__;
const wsBaseUrl = __WS_BASE__;
const isDark = __DARK__;
const displayLabel = __DISPLAY_LABEL__;

// Update entire page background according to mode
try {
  document.documentElement.style.setProperty('--bg', isDark ? '#064e3b' : '#10b981');
} catch(_) {}

let ws = null;
let chatHistories = {};
let currentPeer = null;
let latestUsers = {};
let defaultPassphrase = null;

function fmtLocal(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch(e) { return iso; }
}

function setStatus(s) {
  document.getElementById("status").textContent = s;
}

function clearChatbox() {
  const cb = document.getElementById("chatbox"); cb.innerHTML = "";
}

function appendBubble({from_label, sender_username, text, ts, mine=false}) {
  const cb = document.getElementById("chatbox");
  const row = document.createElement("div");
  row.className = "bubble-row " + (mine ? "bubble-right" : "bubble-left");

  const wrapper = document.createElement("div");
  wrapper.style.display = "flex";
  wrapper.style.flexDirection = "column";
  wrapper.style.alignItems = mine ? "flex-end" : "flex-start";

  const bubble = document.createElement("div");
  bubble.className = "chat-bubble";
  bubble.style.background = mine ? "var(--bubble-sent)" : "var(--bubble-recv)";
  bubble.style.color = mine ? "var(--bubble-sent-text)" : "var(--bubble-recv-text)";
  bubble.innerText = text;

  const meta = document.createElement("div");
  meta.className = "meta";
  // Only show timestamp
  meta.innerHTML = "<span class='ts'> " + (ts ? fmtLocal(ts) : "") + "</span>";

  wrapper.appendChild(bubble);
  wrapper.appendChild(meta);
  row.appendChild(wrapper);
  cb.appendChild(row);
  cb.scrollTop = cb.scrollHeight;
}

function updateActiveChats() {
  const activeChatsDiv = document.getElementById("active-chats");
  activeChatsDiv.innerHTML = "";
  for (const peer in chatHistories) {
    const chatBtn = document.createElement("button");
    chatBtn.textContent = latestUsers[peer] ? latestUsers[peer].label : peer;
    chatBtn.style.width = "100%";
    chatBtn.style.marginBottom = "6px";
    chatBtn.onclick = () => switchToChat(peer);
    activeChatsDiv.appendChild(chatBtn);
  }
}

function switchToChat(peer) {
  currentPeer = peer;
  document.getElementById("current-peer").textContent = latestUsers[peer] ? latestUsers[peer].label : peer;
  clearChatbox();
  if (!defaultPassphrase) {
    setStatus("[Waiting for encryption key from server...]");
    try { ws && ws.send(JSON.stringify({ type: "get_passphrase" })); } catch(_) {}
    return;
  }
  if (chatHistories[peer]) { decryptAndDisplayChatHistory(peer); }
  updateActiveChats();
}

async function deriveKey(pass) {
  const enc = new TextEncoder();
  const keyMaterial = await crypto.subtle.importKey("raw", enc.encode(pass), "PBKDF2", false, ["deriveKey"]);
  return crypto.subtle.deriveKey(
    { name: "PBKDF2", salt: enc.encode("static-salt-demo"), iterations: 200000, hash: "SHA-256" },
    keyMaterial,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt","decrypt"]
  );
}

async function decrypt(key, payload) {
  try {
    const dec = new TextDecoder();
    const iv = Uint8Array.from(atob(payload.iv), c => c.charCodeAt(0));
    const ct = Uint8Array.from(atob(payload.ct), c => c.charCodeAt(0));
    const pt = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: iv, additionalData: new TextEncoder().encode(payload.aad || ""), tagLength:128 },
      key,
      ct
    );
    return dec.decode(pt);
  } catch(e) {
    console.error("decrypt error", e);
    return "[decryption failed]";
  }
}

async function encrypt(key, msg, aadJson) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const enc = new TextEncoder();
  const ct = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv: iv, additionalData: enc.encode(aadJson), tagLength:128 },
    key,
    enc.encode(msg)
  );
  return {
    iv: btoa(String.fromCharCode(...iv)),
    ct: btoa(String.fromCharCode(...new Uint8Array(ct))),
    aad: aadJson
  };
}

async function decryptAndDisplayChatHistory(peer) {
  clearChatbox();
  if (!defaultPassphrase) { setStatus("[Waiting for encryption key from server...]"); return; }
  const key = await deriveKey(defaultPassphrase);
  const msgs = chatHistories[peer] || [];
  for (const msg of msgs) {
    const decrypted = await decrypt(key, msg);
    const mine = (msg.sender_username === username);
    appendBubble({ from_label: msg.sender, sender_username: msg.sender_username, text: decrypted, ts: msg.timestamp, mine });
  }
}

// WebSocket helper
function attemptWebSocket(url, timeoutMs = 4000) {
  return new Promise((resolve, reject) => {
    let settled = false;
    const sock = new WebSocket(url);
    const timer = setTimeout(() => {
      if (!settled) { settled = true; try { sock.close(); } catch(_){}; reject(new Error("timeout")); }
    }, timeoutMs);

    sock.onopen = () => {
      if (settled) return;
      settled = true; clearTimeout(timer);
      setStatus("[connected]");
      resolve(sock);
    };
    sock.onerror = e => { if (settled) return; settled = true; clearTimeout(timer); reject(e); };
    sock.onclose = e => { if (!settled) { settled = true; clearTimeout(timer); reject(new Error("closed")); } };
  });
}

async function connectWithFallback(maxAttempts = 8) {
  let base = (wsBaseUrl || "").trim();
  if (!base) { base = "wss://chat-app-4b0u.onrender.com"; }
  base = base.replace(/\/$/, "");
  const url = base + "/ws/" + encodeURIComponent(username);

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const sock = await attemptWebSocket(url);
      return sock;
    } catch (error) {
      const delay = Math.min(500 * Math.pow(2, attempt - 1), 4000);
      setStatus(`Connecting... attempt ${attempt}/${maxAttempts}`);
      await new Promise(r => setTimeout(r, delay));
    }
  }
  setStatus("[ERROR] Connection attempt failed — is the server running?");
  return null;
}

// Main init
(async () => {
  ws = await connectWithFallback();
  if (!ws) return;

  ws.onmessage = async evt => {
    let obj;
    try { obj = JSON.parse(evt.data); } catch(_) { return; }

    if (obj.type === "passphrase") {
      defaultPassphrase = obj.passphrase;
      setStatus("[Received encryption key from server]");
      if (currentPeer) { try { await decryptAndDisplayChatHistory(currentPeer); } catch(_){} }
      return;
    }

    if (obj.type === "register_ok") {
      setStatus("[REGISTERED as " + obj.label + "]");
      if (!defaultPassphrase && obj.passphrase) { defaultPassphrase = obj.passphrase; setStatus("[Received encryption key from server]"); }
    }

    if (obj.type === "user_list") {
      latestUsers = {};
      for (let u of obj.users) {
        latestUsers[u.username] = { label: u.label, anonymous: u.anonymous };
      }
      const listDiv = document.getElementById("userlist");
      listDiv.innerHTML = "";
      obj.users.forEach(u => {
        if (u.username === username) return; // hide self from live users
        const span = document.createElement("div");
        span.className = "user-item";
        // Only show the visible username (label)
        span.innerText = u.label;
        span.onclick = () => {
          if (u.username !== username) {
            if (!chatHistories[u.username]) chatHistories[u.username] = [];
            switchToChat(u.username);
          }
        };
        listDiv.appendChild(span);
      });
      // Rebuild active chats with latest labels and keep selection
      updateActiveChats();
      if (currentPeer) {
        document.getElementById("current-peer").textContent = latestUsers[currentPeer] ? latestUsers[currentPeer].label : currentPeer;
      }
    }

    if (!obj.type || obj.type === "message") {
      if (obj.recipient === username) {
        if (!chatHistories[obj.sender_username]) chatHistories[obj.sender_username] = [];
        chatHistories[obj.sender_username].push(obj);
        if (currentPeer === obj.sender_username) {
          if (!defaultPassphrase) { setStatus("[Waiting for encryption key...]"); return; }
          const key = await deriveKey(defaultPassphrase);
          const decrypted = await decrypt(key, obj);
          appendBubble({ from_label: obj.sender, sender_username: obj.sender_username, text: decrypted, ts: obj.timestamp, mine:false });
        }
        updateActiveChats();
      }
    }

    if (obj.type === "chat_history") {
      // received initial chat_history structure: { chats: { otherUser: [msgs...] } }
      if (obj.chats) {
        for (const other in obj.chats) {
          chatHistories[other] = obj.chats[other];
        }
      }
    }
  };

  const reg = {
    type: "register",
    username: username,
    anonymous: anonymous,
    label: anonymous ? anon_label : (displayLabel || username)
  };

  ws.onopen = () => {
    try { ws.send(JSON.stringify(reg)); } catch(_) {}
    try { ws.send(JSON.stringify({ type: "get_passphrase" })); } catch(_) {}
  };

  // keep requesting passphrase periodically if missing
  const _passphraseTicker = setInterval(() => {
    if (defaultPassphrase) { clearInterval(_passphraseTicker); return; }
    if (ws && ws.readyState === 1) {
      try { ws.send(JSON.stringify({ type: "get_passphrase" })); } catch(_) {}
    }
  }, 1500);

  document.getElementById("send").onclick = async () => {
    if (!currentPeer) { setStatus("[select a user first]"); return; }
    if (!defaultPassphrase) { setStatus("[Waiting for encryption key from server...]"); return; }
    const out = document.getElementById("out").value;
    if (!out) return;
    const key = await deriveKey(defaultPassphrase);
    const aadJson = JSON.stringify({ sender: username, recipient: currentPeer });
    const enc = await encrypt(key, out, aadJson);
    // include timestamp
    const ts = new Date().toISOString();
    const msg = {
      type: "message",
      sender_username: username,
      recipient: currentPeer,
      sender: displayLabel || username,
      iv: enc.iv,
      ct: enc.ct,
      aad: aadJson,
      timestamp: ts
    };
    try { ws.send(JSON.stringify(msg)); } catch(e) { setStatus("[send failed]"); }
    if (!chatHistories[currentPeer]) chatHistories[currentPeer] = [];
    chatHistories[currentPeer].push(msg);
    appendBubble({ from_label: null, sender_username: username, text: out, ts: ts, mine:true });
    document.getElementById("out").value = "";
    updateActiveChats();
  };

  document.getElementById("out").addEventListener("keypress", e => {
    if (e.key === "Enter") {
      e.preventDefault();
      document.getElementById("send").click();
    }
  });
})();
</script>
"""

# Fill template placeholders
html = html_template.replace("{me_display}", display_label)
html = html.replace("__USERNAME__", json.dumps(username))
html = html.replace("__ANON__", json.dumps(bool(anonymous)))
html = html.replace("__ANON_LABEL__", json.dumps(anon_label))
html = html.replace("__WS_BASE__", json.dumps(ws_base_url))
html = html.replace("__DARK__", "true" if dark_mode else "false")
html = html.replace("__THEME__", "")
html = html.replace("__DISPLAY_LABEL__", json.dumps(display_label))

components.html(html, height=720)
