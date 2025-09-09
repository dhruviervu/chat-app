import streamlit as st
import streamlit.components.v1 as components
import json
import secrets
import os

st.set_page_config(page_title="Secure Chat (Multiuser)", layout="wide")
st.title("Secure Chat — Multiuser (AES-GCM with Default Passphrase)")

col1, col2, col3 = st.columns([2, 1, 2])
with col1:
    username = st.text_input("Username", value="Alice")
with col2:
    anonymous = st.checkbox("Anonymous label", value=False)
with col3:
    ws_base_url = st.text_input("Server WebSocket base URL", value=os.getenv("WS_SERVER_URL", "ws://127.0.0.1:8765"))

if anonymous:
    anon_label = st.text_input("Anonymous label (optional)", value=f"Anon-{secrets.token_hex(3)}")
else:
    anon_label = username

st.info("🔒 Using server-provided strong passphrase for encryption")

st.markdown("---")

html = f"""
<div style="display:flex; gap:16px;">
  <div style="flex:1;">
    <div id="chat-header" style="font-weight:bold; margin-bottom:8px;">Chat with: <span id="current-peer">Select a user</span></div>
    <textarea id="msgs" rows="15" cols="80" readonly style="white-space:pre-wrap; width:100%;"></textarea><br/>
    <input id="out" placeholder="Type your message" style="width:70%;" />
    <button id="send">Send</button>
    <div id="status" style="color:dimgray; margin-top:8px;"></div>
  </div>
  <div style="width:280px; border-left:1px solid #ddd; padding-left:12px;">
    <h4>Live users</h4>
    <div id="userlist" style="font-family:monospace; white-space:pre-wrap; max-height:300px; overflow-y:auto;"></div>
    <div style="margin-top:12px;">
      <div><strong>Active chats:</strong></div>
      <div id="active-chats" style="margin-top:8px; max-height:200px; overflow-y:auto;"></div>
    </div>
  </div>
</div>

<script>
const username = {json.dumps(username)};
const anonymous = {json.dumps(bool(anonymous))};
const anon_label = {json.dumps(anon_label)};
const wsBaseUrl = {json.dumps(ws_base_url)};

let ws = null;
let chatHistories = {{}};
let currentPeer = null;
let latestUsers = {{}};
let defaultPassphrase = null;

function appendMsg(text) {{
  const t = document.getElementById("msgs");
  t.value += text + "\\n";
  t.scrollTop = t.scrollHeight;
}}

function setStatus(s) {{
  document.getElementById("status").textContent = s;
}}

function clearMessages() {{
  document.getElementById("msgs").value = "";
}}

async function deriveKey(pass) {{
  const enc = new TextEncoder();
  const keyMaterial = await crypto.subtle.importKey("raw", enc.encode(pass), "PBKDF2", false, ["deriveKey"]);
  return crypto.subtle.deriveKey(
    {{
      name: "PBKDF2",
      salt: enc.encode("static-salt-demo"),
      iterations: 200000,
      hash: "SHA-256"
    }},
    keyMaterial,
    {{ name: "AES-GCM", length: 256 }},
    false,
    ["encrypt","decrypt"]
  );
}}

async function encrypt(key, msg, aadJson) {{
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const enc = new TextEncoder();
  const ct = await crypto.subtle.encrypt(
    {{ name: "AES-GCM", iv: iv, additionalData: enc.encode(aadJson), tagLength:128 }},
    key,
    enc.encode(msg)
  );
  return {{
    iv: btoa(String.fromCharCode(...iv)),
    ct: btoa(String.fromCharCode(...new Uint8Array(ct))),
    aad: aadJson
  }};
}}

async function decrypt(key, payload) {{
  try {{
    const dec = new TextDecoder();
    const iv = Uint8Array.from(atob(payload.iv), c => c.charCodeAt(0));
    const ct = Uint8Array.from(atob(payload.ct), c => c.charCodeAt(0));
    const pt = await crypto.subtle.decrypt(
      {{ name: "AES-GCM", iv: iv, additionalData: new TextEncoder().encode(payload.aad || ""), tagLength:128 }},
      key,
      ct
    );
    return dec.decode(pt);
  }} catch(e) {{
    console.error("decrypt error", e);
    return "[decryption failed]";
  }}
}}

function updateActiveChats() {{
  const activeChatsDiv = document.getElementById("active-chats");
  activeChatsDiv.innerHTML = "";
  for (const peer in chatHistories) {{
    const chatBtn = document.createElement("button");
    chatBtn.textContent = latestUsers[peer] ? latestUsers[peer].label : peer;
    chatBtn.style.width = "100%";
    chatBtn.style.marginBottom = "4px";
    chatBtn.onclick = () => switchToChat(peer);
    activeChatsDiv.appendChild(chatBtn);
  }}
}}

function switchToChat(peer) {{
  currentPeer = peer;
  document.getElementById("current-peer").textContent = latestUsers[peer] ? latestUsers[peer].label : peer;
  clearMessages();
  if (chatHistories[peer]) {{
    decryptAndDisplayChatHistory(peer);
  }}
  updateActiveChats();
}}

async function decryptAndDisplayChatHistory(peer) {{
  clearMessages();
  if (!defaultPassphrase) {{
    appendMsg("[Waiting for encryption key from server...]");
    return;
  }}
  const key = await deriveKey(defaultPassphrase);
  for (const msg of chatHistories[peer]) {{
    const decrypted = await decrypt(key, msg);
    const prefix = msg.sender_username === username ? "YOU" : msg.sender;
    appendMsg(prefix + ": " + decrypted);
  }}
}}

async function attemptWebSocket(url, timeoutMs = 4000) {{
  return new Promise((resolve, reject) => {{
    let settled = false;
    const sock = new WebSocket(url);
    const timer = setTimeout(() => {{
      if (!settled) {{
        settled = true;
        try {{ sock.close(); }} catch(_){{}};
        reject(new Error("timeout"));
      }}
    }}, timeoutMs);

    sock.onopen = () => {{
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      appendMsg("[connected to " + url + "]");
      resolve(sock);
    }};

    sock.onerror = e => {{
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      reject(e);
    }};

    sock.onclose = e => {{
      if (!settled) {{
        settled = true;
        clearTimeout(timer);
        reject(new Error("closed"));
      }}
    }};
  }});
}}

async function connectWithFallback() {{
  const base = wsBaseUrl.replace(/\/$/, "");
  const url = base + "/ws/" + encodeURIComponent(username);

  try {{
    const sock = await attemptWebSocket(url);
    return sock;
  }} catch (error) {{
    appendMsg("[ERROR] Connection attempt failed — is the server running?");
    return null;
  }}
}}

(async () => {{
  ws = await connectWithFallback();
  if (!ws) return;

  ws.onmessage = async evt => {{
    let obj;
    try {{ obj = JSON.parse(evt.data); }} catch(_) {{ return; }}

    if (obj.type === "passphrase") {{
      defaultPassphrase = obj.passphrase;
      appendMsg("[Received encryption key from server]");
      return;
    }}

    if (obj.type === "register_ok") {{
      appendMsg("[REGISTERED as " + obj.label + "]");
    }}

    if (obj.type === "user_list") {{
      latestUsers = {{}};
      for (let u of obj.users) {{
        latestUsers[u.username] = {{ label: u.label, anonymous: u.anonymous }};
      }}
      const listDiv = document.getElementById("userlist");
      listDiv.innerHTML = "";
      obj.users.forEach(u => {{
        const span = document.createElement("div");
        span.innerText = (u.username === username ? "(you) " : "") + u.label + " [" + u.username + "]";
        span.style.cursor = "pointer";
        span.onclick = () => {{
          if (u.username !== username) {{
            if (!chatHistories[u.username]) chatHistories[u.username] = [];
            switchToChat(u.username);
          }}
        }};
        listDiv.appendChild(span);
      }});
    }}

    if (!obj.type || obj.type === "message") {{
      if (obj.recipient === username) {{
        if (!chatHistories[obj.sender_username]) chatHistories[obj.sender_username] = [];
        chatHistories[obj.sender_username].push(obj);
        if (currentPeer === obj.sender_username) {{
          if (!defaultPassphrase) {{
            appendMsg("[Waiting for encryption key...]");
            return;
          }}
          const key = await deriveKey(defaultPassphrase);
          const decrypted = await decrypt(key, obj);
          appendMsg(obj.sender + ": " + decrypted);
        }}
        updateActiveChats();
      }}
    }}
  }};

  const reg = {{
    type: "register",
    username: username,
    anonymous: anonymous,
    label: anonymous ? anon_label : username
  }};

  ws.onopen = () => ws.send(JSON.stringify(reg));

  document.getElementById("send").onclick = async () => {{
    if (!currentPeer) {{
      appendMsg("[select a user first]");
      return;
    }}
    if (!defaultPassphrase) {{
      appendMsg("[Waiting for encryption key from server...]");
      return;
    }}
    const out = document.getElementById("out").value;
    if (!out) return;
    const key = await deriveKey(defaultPassphrase);
    const aadJson = JSON.stringify({{sender: username, recipient: currentPeer}});
    const enc = await encrypt(key, out, aadJson);
    const msg = {{
      type: "message",
      sender_username: username,
      recipient: currentPeer,
      sender: username,
      iv: enc.iv,
      ct: enc.ct,
      aad: aadJson
    }};
    ws.send(JSON.stringify(msg));
    if (!chatHistories[currentPeer]) chatHistories[currentPeer] = [];
    chatHistories[currentPeer].push(msg);
    appendMsg("YOU: " + out);
    document.getElementById("out").value = "";
    updateActiveChats();
  }};

  document.getElementById("out").addEventListener("keypress", e => {{
    if (e.key === "Enter") document.getElementById("send").click();
  }});
}})();
</script>
"""

components.html(html, height=720)
