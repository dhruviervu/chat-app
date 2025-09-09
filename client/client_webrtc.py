# client_webrtc.py
import streamlit as st
import streamlit.components.v1 as components
import json
import secrets
import time

st.set_page_config(page_title="WebRTC Chat", layout="wide")
st.title("🚀 WebRTC Chat")

default_username = f"user_{int(time.time()) % 10000}_{secrets.token_hex(2)}"
username = st.text_input("Your username", value=default_username)
server_host = st.text_input("Server host", value="127.0.0.1")
server_port = st.number_input("Server port", 8765)

st.markdown("---")

html = f"""
<textarea id="msgs" rows="15" cols="80" readonly></textarea><br/>
<input id="peer" placeholder="Peer username"/>
<br/>
<input id="out" placeholder="Type message" style="width:70%"/>
<button id="send">Send</button>

<script>
const username = {json.dumps(username)};
const serverHost = {json.dumps(server_host)};
const serverPort = {json.dumps(server_port)};

let ws = null;
let pc = null;
let dc = null;

function log(msg) {{
  const t = document.getElementById("msgs");
  t.value += msg + "\\n";
  t.scrollTop = t.scrollHeight;
}}

function connectWS() {{
  ws = new WebSocket("ws://" + serverHost + ":" + serverPort + "/ws/" + encodeURIComponent(username));
  ws.onopen = () => log("[ws connected]");
  ws.onmessage = async (evt) => {{
    let msg = JSON.parse(evt.data);
    if (msg.type === "offer") {{
      await handleOffer(msg);
    }} else if (msg.type === "answer") {{
      await handleAnswer(msg);
    }} else if (msg.type === "candidate") {{
      await handleCandidate(msg);
    }} else if (msg.type === "msg") {{
      log(msg.sender + ": " + msg.text);
    }}
  }};
}}

async function createPeer(recipient) {{
  pc = new RTCPeerConnection();
  dc = pc.createDataChannel("chat");
  dc.onopen = () => log("[datachannel open]");
  dc.onmessage = (e) => log(recipient + ": " + e.data);

  pc.onicecandidate = (e) => {{
    if (e.candidate) {{
      ws.send(JSON.stringify({{type:"candidate", recipient:recipient, candidate:e.candidate}}));
    }}
  }};
}}

async function startCall(recipient) {{
  await createPeer(recipient);
  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);
  ws.send(JSON.stringify({{type:"offer", recipient:recipient, sender:username, sdp:offer}}));
}}

async function handleOffer(msg) {{
  await createPeer(msg.sender);
  await pc.setRemoteDescription(new RTCSessionDescription(msg.sdp));
  const answer = await pc.createAnswer();
  await pc.setLocalDescription(answer);
  ws.send(JSON.stringify({{type:"answer", recipient:msg.sender, sender:username, sdp:answer}}));
}}

async function handleAnswer(msg) {{
  await pc.setRemoteDescription(new RTCSessionDescription(msg.sdp));
}}

async function handleCandidate(msg) {{
  try {{
    await pc.addIceCandidate(new RTCIceCandidate(msg.candidate));
  }} catch (e) {{
    console.error("candidate error", e);
  }}
}}

document.getElementById("send").onclick = () => {{
  const peer = document.getElementById("peer").value;
  const text = document.getElementById("out").value;
  if (!peer || !text) return;

  if (!dc || dc.readyState !== "open") {{
    startCall(peer);
    setTimeout(() => {{
      if (dc && dc.readyState === "open") {{
        dc.send(text);
        log("YOU: " + text);
      }} else {{
        ws.send(JSON.stringify({{type:"msg", sender:username, recipient:peer, text:text}}));
      }}
    }}, 1500);
  }} else {{
    dc.send(text);
    log("YOU: " + text);
  }}
  document.getElementById("out").value = "";
}};

connectWS();
</script>
"""

components.html(html, height=600)
