import streamlit as st
import streamlit.components.v1 as components
import json

st.set_page_config(page_title="Secure Chat (MVP)", layout="wide")
st.title("Secure Chat — Streamlit UI (AES-GCM)")

username = st.text_input("Username", "Alice")
peer = st.text_input("Recipient", "Bob")
passphrase = st.text_input("Passphrase (demo)", type="password")
st.markdown("**AES-GCM encryption in browser (demo).**")

html = f"""
<textarea id="msgs" rows="15" cols="90" readonly></textarea><br/>
<input id="out" placeholder="Type message" style="width:70%"/>
<button id="send">Send</button>

<script>
const username = {json.dumps(username)};
const peer = {json.dumps(peer)};
const passphrase = {json.dumps(passphrase)};

function appendMsg(text) {{
  const t = document.getElementById("msgs");
  t.value += text + "\\n";
  t.scrollTop = t.scrollHeight;
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

async function encrypt(key, msg) {{
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const enc = new TextEncoder();
  const ct = await crypto.subtle.encrypt(
    {{ name: "AES-GCM", iv: iv, additionalData: enc.encode(JSON.stringify({{sender:username,recipient:peer}})), tagLength:128 }},
    key,
    enc.encode(msg)
  );
  return {{
    iv: btoa(String.fromCharCode(...iv)),
    ct: btoa(String.fromCharCode(...new Uint8Array(ct)))
  }};
}}

async function decrypt(key, payload) {{
  try {{
    const dec = new TextDecoder();
    const iv = Uint8Array.from(atob(payload.iv), c=>c.charCodeAt(0));
    const ct = Uint8Array.from(atob(payload.ct), c=>c.charCodeAt(0));
    const pt = await crypto.subtle.decrypt(
      {{ name: "AES-GCM", iv: iv, additionalData: new TextEncoder().encode(payload.aad), tagLength:128 }},
      key,
      ct
    );
    return dec.decode(pt);
  }} catch(e) {{
    console.error("decrypt error", e);
    return "[decryption failed]";
  }}
}}

(async () => {{
  const ws = new WebSocket("wss://127.0.0.1:8765/ws/" + encodeURIComponent(username));
  appendMsg("[client] connecting to wss://127.0.0.1:8765/ws/" + username);

  ws.onopen = () => appendMsg("[ws connected]");
  ws.onerror = (e) => {{
    appendMsg("[ws error — see browser console for details]");
    console.error("WebSocket error:", e);
  }};
  ws.onclose = () => appendMsg("[ws closed]");

  ws.onmessage = async (evt) => {{
    let payload = null;
    try {{
        payload = JSON.parse(evt.data);
    }} catch(e) {{
        appendMsg("[non-json incoming] " + evt.data);
        return;
    }}

    if (payload.status === "sent") {{
        return; // ignore ACK
    }}

    const key = await deriveKey(passphrase || "");
    if (payload.recipient === username) {{
        const pt = await decrypt(key, payload);
        if (payload.sender === username) {{
            appendMsg("YOU: " + pt);
        }} else {{
            appendMsg(payload.sender + ": " + pt);
        }}
    }}
  }};

  document.getElementById("send").onclick = async () => {{
    const out = document.getElementById("out").value;
    if(!out) return;
    const key = await deriveKey(passphrase || "");
    const encData = await encrypt(key, out);
    const payload = {{
      sender: username,
      recipient: peer,
      iv: encData.iv,
      ct: encData.ct,
      aad: JSON.stringify({{sender:username,recipient:peer}})
    }};
    ws.send(JSON.stringify(payload));
    appendMsg("YOU: " + out);
    document.getElementById("out").value = "";
  }};
}})();
</script>
"""

components.html(html, height=520)
