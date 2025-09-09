# client8_fixed.py
"""
Streamlit client for Secure Chat (drop-in replacement).
Tries WSS first; you can set Server Host to 'localhost' to match cert SAN.
Run: streamlit run client8_fixed.py
"""

import streamlit as st
import streamlit.components.v1 as components
import json
import secrets
import time

st.set_page_config(page_title="Secure Chat (Multiuser)", layout="wide")
st.title("Secure Chat — Multiuser (AES-GCM)")

default_username = f"User_{int(time.time()) % 10000}_{secrets.token_hex(2)}"

col1, col2 = st.columns([2, 1])
with col1:
    username = st.text_input("Username", value=default_username)
with col2:
    server_host = st.text_input("Server Host", value="localhost")
    server_port = st.number_input("Server Port", value=8765, min_value=1, max_value=65535)

passphrase = st.text_input("Passphrase (demo)", type="password")
st.markdown("---")

html = f"""
<div style="display:flex; gap:16px;">
  <div style="flex:1;">
    <div style="display:flex; gap:12px; align-items:center; margin-bottom:8px;">
      <div style="font-weight:bold;">Chat with: <span id="current-peer">Select a user</span></div>
      <div style="margin-left:auto;">
        <label><input type="checkbox" id="js-anon" /> Anonymous</label>
        <input id="js-label" placeholder="label (optional)" style="margin-left:8px; width:200px;" />
        <button id="update-alias" style="margin-left:6px;">Use alias</button>
      </div>
    </div>

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
const passphrase = {json.dumps(passphrase)};
const serverHost = {json.dumps(server_host)};
const serverPort = {json.dumps(server_port)};

let ws = null;
let chatHistories = {{}};   // peerUsername -> [ messages ]
let currentPeer = null;
let latestUsers = {{ }};

function appendMsg(text) {{
  const t = document.getElementById("msgs");
  t.value += text + "\\n";
  t.scrollTop = t.scrollHeight;
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

// UI functions
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
  for (const msg of chatHistories[peer]) {{
    const key = await deriveKey(passphrase || "");
    const decrypted = await decrypt(key, msg);
    const prefix = msg.sender_username === username ? "YOU" : msg.sender;
    appendMsg(prefix + ": " + decrypted);
  }}
}}

// attempt a WebSocket with timeout
function attemptWebSocket(url, timeoutMs = 4000) {{
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
      resolve(sock);
    }};
    sock.onerror = e => {{
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      reject(e);
    }};
    sock.onclose = () => {{
      if (!settled) {{
        settled = true;
        clearTimeout(timer);
        reject(new Error("closed"));
      }}
    }};
  }});
}}

// try wss first (use serverHost so SAN matches), then ws fallback
async function connectWithFallback() {{
  const endpoints = [
    {{ scheme: "wss", host: serverHost + ":" + serverPort }},
    {{ scheme: "ws",  host: serverHost + ":" + serverPort }},
    {{ scheme: "wss", host: "127.0.0.1:" + serverPort }},
    {{ scheme: "ws",  host: "127.0.0.1:" + serverPort }},
    {{ scheme: "wss", host: "localhost:" + serverPort }},
    {{ scheme: "ws",  host: "localhost:" + serverPort }}
  ];

  for (let ep of endpoints) {{
    const url = `${{ep.scheme}}://{{ep.host}}/ws/${{encodeURIComponent(username)}}`;
    try {{
      const sock = await attemptWebSocket(url);
      appendMsg("[connected to " + url + "]");
      return sock;
    }} catch(e) {{
      console.log("Connection failed to " + url + ": " + e);
    }}
  }}
  appendMsg("[ERROR] all connection attempts failed — is server running?");
  return null;
}}



(async () => {{
  ws = await connectWithFallback();
  if (!ws) return;

  ws.onmessage = async evt => {{
    let obj;
    try {{ obj = JSON.parse(evt.data); }} catch(_) {{ return; }}

    if (obj.type === "register_ok" || obj.type === "update_ok") {{
      appendMsg("[REGISTERED: " + (obj.label || "") + "]");
    }}

    if (obj.type === "user_list") {{
      latestUsers = {{}};
      const listDiv = document.getElementById("userlist");
      listDiv.innerHTML = "";
      for (let u of obj.users) {{
        latestUsers[u.username] = {{ label: u.label, anonymous: u.anonymous }};
        const span = document.createElement("div");
        span.innerText = (u.username === username ? "(you) " : "") + u.label;
        span.style.cursor = "pointer";
        span.onclick = () => {{
          if (u.username !== username) {{
            if (!chatHistories[u.username]) chatHistories[u.username] = [];
            switchToChat(u.username);
          }}
        }};
        listDiv.appendChild(span);
      }}
      if (currentPeer) {{
        document.getElementById("current-peer").textContent = latestUsers[currentPeer] ? latestUsers[currentPeer].label : currentPeer;
      }}
      updateActiveChats();
      return;
    }}

    if (obj.type === "chat_history") {{
      if (obj.chats) {{
        for (const other in obj.chats) {{
          chatHistories[other] = obj.chats[other];
        }}
      }} else if (obj.with_user && obj.messages) {{
        chatHistories[obj.with_user] = obj.messages;
      }}
      updateActiveChats();
      if (currentPeer && chatHistories[currentPeer]) {{
        decryptAndDisplayChatHistory(currentPeer);
      }}
      return;
    }}

    if (!obj.type || obj.type === "message") {{
      if (obj.recipient === username) {{
        if (!chatHistories[obj.sender_username]) chatHistories[obj.sender_username] = [];
        chatHistories[obj.sender_username].push(obj);
        if (currentPeer === obj.sender_username) {{
          const key = await deriveKey(passphrase || "");
          const decrypted = await decrypt(key, obj);
          appendMsg(obj.sender + ": " + decrypted);
        }}
        updateActiveChats();
      }}
    }}
  }};

  ws.onopen = () => {{
    const reg = {{
      type: "register",
      username: username,
      anonymous: false,
      label: username
    }};
    ws.send(JSON.stringify(reg));
  }};

  document.getElementById("send").onclick = async () => {{
    if (!currentPeer) {{
      appendMsg("[select a user first]");
      return;
    }}
    const out = document.getElementById("out").value;
    if (!out) return;
    const key = await deriveKey(passphrase || "");
    const aadJson = JSON.stringify({{sender: username, recipient: currentPeer}});
    const enc = await encrypt(key, out, aadJson);
    const msg = {{
      type: "message",
      sender_username: username,
      recipient: currentPeer,
      iv: enc.iv,
      ct: enc.ct,
      aad: aadJson,
      timestamp: Date.now()
    }};
    ws.send(JSON.stringify(msg));
    if (!chatHistories[currentPeer]) chatHistories[currentPeer] = [];
    chatHistories[currentPeer].push(msg);
    appendMsg("YOU: " + out);
    document.getElementById("out").value = "";
    updateActiveChats();
  }};

  document.getElementById("update-alias").onclick = () => {{
    const isAnon = document.getElementById("js-anon").checked;
    const newLabel = document.getElementById("js-label").value.trim();
    const payload = {{
      type: "update_label",
      anonymous: isAnon,
      label: newLabel
    }};
    ws.send(JSON.stringify(payload));
    appendMsg("[alias update sent]");
  }};

  document.getElementById("out").addEventListener("keypress", e => {{
    if (e.key === "Enter") {{
      e.preventDefault();
      document.getElementById("send").click();
    }}
  }});
}})();
</script>
"""

components.html(html, height=720)
