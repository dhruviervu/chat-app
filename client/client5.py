# client5_fixed.py
"""
Streamlit client that connects to the server above.
Auto-tries WSS to localhost:8765 first; if it fails, falls back to WS on 127.0.0.1.
Uses AES-GCM via WebCrypto in-browser (demo). Client expects user-list entries with 'label'.
Run: streamlit run client5_fixed.py [--server.sslCertFile=... --server.sslKeyFile=...]
"""

from cProfile import label
import streamlit as st
import streamlit.components.v1 as components
import json
import secrets

st.set_page_config(page_title="Secure Chat (Multiuser)", layout="wide")
st.title("Secure Chat — Multiuser (AES-GCM)")

col1, col2 = st.columns([2, 1])
with col1:
    username = st.text_input("Username", value="Alice")
with col2:
    anonymous = st.checkbox("Anonymous label", value=False)

if anonymous:
    anon_label = st.text_input("Anonymous label (optional)", value=f"Anon-{secrets.token_hex(3)}")
else:
    anon_label = username

passphrase = st.text_input("Passphrase (demo)", type="password")

st.markdown("---")
peer_fallback = st.text_input("Recipient fallback (or click a user)", value="Bob")
st.markdown("---")

html = f"""
<div style="display:flex; gap:16px;">
  <div style="flex:1;">
    <textarea id="msgs" rows="18" cols="80" readonly style="white-space:pre-wrap;"></textarea><br/>
    <input id="out" placeholder="Type your message" style="width:70%;" />
    <button id="send">Send</button>
    <div id="status" style="color:dimgray; margin-top:8px;"></div>
  </div>
  <div style="width:280px; border-left:1px solid #ddd; padding-left:12px;">
    <h4>Live users</h4>
    <div id="userlist" style="font-family:monospace; white-space:pre-wrap;"></div>
    <div style="margin-top:12px;">
      <div><strong>Selected recipient:</strong> <span id="selected">{peer_fallback}</span></div>
      <div style="margin-top:8px; color:#666; font-size:12px;">Click a user to chat 1:1.</div>
    </div>
  </div>
</div>

<script>
const username = {json.dumps(username)};
const anonymous = {json.dumps(bool(anonymous))};
const anon_label = {json.dumps(anon_label)};
const passphrase = {json.dumps(passphrase)};
const peer_fallback = {json.dumps(peer_fallback)};

function appendMsg(text) {{
  const t = document.getElementById("msgs");
  t.value += text + "\\n";
  t.scrollTop = t.scrollHeight;
}}
function setStatus(s) {{
  document.getElementById("status").textContent = s;
}}

// crypto helpers (AES-GCM)
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

// keep a mapping username -> {label, anonymous}
let latestUsers = {{}};
let selectedRecipient = peer_fallback;

// connection logic with fallback and helpful messages
async function connectWithFallback() {{
  // try wss://localhost:8765 first (matches CN=localhost in certs)
  const endpoints = [
    {{ scheme: "wss", host: "localhost:8765" }},   // prefer this (TLS)
    {{ scheme: "ws",  host: "127.0.0.1:8765" }}     // fallback (no TLS)
  ];

  for (let ep of endpoints) {{
    const url = `${{ep.scheme}}://${{ep.host}}/ws/${{encodeURIComponent(username)}}`;
    setStatus("[client] attempting " + url);
    appendMsg("[client] attempting " + url);
    try {{
      const ws = await attemptWebSocket(url);
      if (ws) {{
        setStatus("connected to " + url);
        appendMsg("[ws connected to " + url + "]");
        return ws;
      }}
    }} catch(e) {{
      console.warn("connect attempt failed to " + url, e);
      appendMsg("[connect attempt failed to " + url + " — see console]");
    }}
  }}
  // all attempts failed
  setStatus("all connection attempts failed");
  appendMsg("[ERROR] all connection attempts failed — is the server running?");
  return null;
}}

function attemptWebSocket(url, timeoutMs = 4000) {{
  return new Promise((resolve, reject) => {{
    let settled = false;
    let ws;
    try {{
      ws = new WebSocket(url);
    }} catch(e) {{
      reject(e);
      return;
    }}

    const timer = setTimeout(() => {{
      if (!settled) {{
        settled = true;
        try {{ ws.close(); }} catch(_){{}}
        reject(new Error("timeout"));
      }}
    }}, timeoutMs);

    ws.onopen = () => {{
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(ws);
    }};

    ws.onerror = (e) => {{
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      try {{ ws.close(); }} catch(_){{}}
      reject(e);
    }};

    ws.onclose = (e) => {{
      // if the socket closed before open, treat as failure
      if (!settled) {{
        settled = true;
        clearTimeout(timer);
        reject(new Error("closed"));
      }}
    }};
  }});
}}

(async () => {{
  const ws = await connectWithFallback();
  if (!ws) return;

  // ws event wiring
  ws.onmessage = async (evt) => {{
    let obj = null;
    try {{
      obj = JSON.parse(evt.data);
    }} catch(e) {{
      appendMsg("[non-json incoming] " + evt.data);
      return;
    }}

    if (!obj) return;

    if (obj.type === "register_failed") {{
      appendMsg("[REGISTER FAILED] " + (obj.reason || ""));
      setStatus("register_failed: " + (obj.reason || ""));
      return;
    }}

    if (obj.type === "register_ok") {{
      appendMsg("[REGISTERED as " + obj.label + "]");
      return;
    }}

    if (obj.type === "user_list") {{
      latestUsers = {{}};
      const users = obj.users || [];
      let text = "";
      for (let u of users) {{
        latestUsers[u.username] = {{label: u.label, anonymous: u.anonymous}};
        text += (u.username === username ? "(you) " : "") + u.label + "  [" + u.username + "]\\n";
      }}
      const listDiv = document.getElementById("userlist");
      listDiv.innerHTML = "";
      const lines = text.split("\\n").filter(l => l.trim().length > 0);
      lines.forEach(line => {{
        const m = line.match(/\\[(.*?)\\]$/);
        let uname = null;
        if (m) uname = m[1];
        const span = document.createElement("div");
        span.style.cursor = "pointer";
        span.style.padding = "4px 0";
        span.innerText = line;
        span.onclick = () => {{
          if (uname) {{
            selectedRecipient = uname;
            const lbl = latestUsers[uname] ? latestUsers[uname].label : uname;
            document.getElementById("selected").innerText = lbl;
            appendMsg("[selected recipient: " + lbl + "]");
          }}
        }};
        listDiv.appendChild(span);
      }});
      return;
    }}

    // chat message case (type === 'message' or no type)
    const payload = obj;
    if (payload.type && payload.type !== "message") return;

    if (payload.recipient && payload.recipient === username) {{
      const key = await deriveKey(passphrase || "");
      const pt = await decrypt(key, payload);
      if (payload.sender_username === username) {{
        appendMsg("YOU: " + pt);
      }} else {{
        appendMsg(payload.sender + ": " + pt);
      }}
    }}
  }};

  ws.onerror = (e) => {{
    appendMsg("[ws error — see console]");
    console.error("ws error", e);
    setStatus("ws error");
  }};

  ws.onclose = (e) => {{
    appendMsg("[ws closed]");
    setStatus("closed");
  }};

  // send registration immediately
  const reg = {{
    type: "register",
    username: username,
    anonymous: anonymous,
    label: anonymous ? anon_label : username
  }};
  try {{
    ws.send(JSON.stringify(reg));
    setStatus("sent register");
  }} catch(e) {{
    appendMsg("[send register failed]");
    console.error(e);
    setStatus("register send failed");
  }}

  // send button handler
  document.getElementById("send").onclick = async () => {{
    const out = document.getElementById("out").value;
    if (!out) return;
    const recipient = selectedRecipient || peer_fallback;
    if (!recipient) {{
      appendMsg("[choose recipient first]");
      return;
    }}
    const key = await deriveKey(passphrase || "");
    const aadJson = JSON.stringify({{sender: username, recipient: recipient}});
    const enc = await encrypt(key, out, aadJson);
    const msg = {{
      type: "message",
      sender_username: username,
      recipient: recipient,
      iv: enc.iv,
      ct: enc.ct,
      aad: aadJson
    }};
    try {{
      ws.send(JSON.stringify(msg));
      appendMsg("YOU: " + out);
      document.getElementById("out").value = "";
    }} catch(e) {{
      appendMsg("[send failed]");
      console.error(e);
      setStatus("send failed");
    }}
  }};
}})();
</script>
"""

components.html(html, height=700)
