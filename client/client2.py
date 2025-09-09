import streamlit as st
import streamlit.components.v1 as components
import json

st.set_page_config(page_title="Secure Chat MVP", layout="wide")
st.title("Secure Chat — AES-GCM Demo")

username = st.text_input("Username", value="Alice")
peer = st.text_input("Recipient", value="Bob")
passphrase = st.text_input("Passphrase", type="password")
st.markdown("**AES-GCM encryption in browser only (demo)**")

html = f"""
<div>
  <textarea id="msgs" rows="15" cols="80" readonly></textarea><br/>
  <input id="out" placeholder="Type message" style="width:70%"/>
  <button id="send">Send</button>
</div>

<script>
const username = {json.dumps(username)};
const peer = {json.dumps(peer)};
const passphrase = {json.dumps(passphrase)};

function appendMsg(msg) {{
    const t = document.getElementById("msgs");
    t.value += msg + "\\n";
    t.scrollTop = t.scrollHeight;
}}

async function deriveKey(pass) {{
    const enc = new TextEncoder();
    const keyMaterial = await crypto.subtle.importKey(
        "raw", enc.encode(pass), "PBKDF2", false, ["deriveKey"]
    );
    return crypto.subtle.deriveKey(
        {{
            name: "PBKDF2",
            salt: enc.encode("static-salt"),
            iterations: 100000,
            hash: "SHA-256"
        }},
        keyMaterial,
        {{ name: "AES-GCM", length: 256 }},
        false,
        ["encrypt", "decrypt"]
    );
}}

async function encrypt(key, msg) {{
    const enc = new TextEncoder();
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const ct = await crypto.subtle.encrypt(
        {{ name: "AES-GCM", iv: iv, tagLength: 128 }},
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
        const iv = Uint8Array.from(atob(payload.iv), c => c.charCodeAt(0));
        const ct = Uint8Array.from(atob(payload.ct), c => c.charCodeAt(0));
        const pt = await crypto.subtle.decrypt(
            {{ name: "AES-GCM", iv: iv, tagLength: 128 }},
            key,
            ct
        );
        return dec.decode(pt);
    }} catch(e) {{
        return "[decryption failed]";
    }}
}}

(async () => {{
    const ws = new WebSocket("ws://127.0.0.1:8765/ws/" + username);

    ws.onopen = () => appendMsg("[ws connected]");
    ws.onclose = () => appendMsg("[ws closed]");
    ws.onerror = (err) => appendMsg("[ws error] " + err);

    ws.onmessage = async (evt) => {{
        const payload = JSON.parse(evt.data);
        const key = await deriveKey(passphrase || "");
        if(payload.recipient === username || !payload.recipient){{
            const pt = await decrypt(key, payload);
            appendMsg(payload.sender + ": " + pt);
        }} else {{
            appendMsg(payload.sender + " (encrypted for others)");
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
            ct: encData.ct
        }};
        ws.send(JSON.stringify(payload));
        appendMsg("YOU: " + out);
        document.getElementById("out").value = "";
    }};
}})();
</script>
"""

components.html(html, height=450)
