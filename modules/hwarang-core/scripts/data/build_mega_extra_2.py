"""화랑 AI 추가 학습 데이터 (채팅/컴포넌트 보강)"""
import json, os, logging, argparse
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
시니어 풀스택 개발자 수준의 코딩 어시스턴트입니다.
프로젝트 요청 시 폴더 구조와 각 파일의 전체 코드를 작성합니다.
실무에서 바로 사용할 수 있는 프로덕션 수준의 코드를 생성합니다.
설명은 한국어로, 코드는 완전한 형태로 작성합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    # ═══ 1. WebSocket 실시간 파일 공유 채팅 ═══
    m("WebSocket으로 실시간 파일 공유 채팅 만들어줘 전체 코드로",
'''실시간 파일 공유 채팅을 Socket.IO 바이너리 전송으로 만들어 드릴게요.

## 폴더 구조

```
file-chat/
├── server/
│   ├── package.json
│   ├── index.js
│   └── uploads/          # 업로드 파일 저장
├── client/
│   ├── index.html
│   ├── style.css
│   └── app.js
```

## server/package.json

```json
{
  "name": "file-chat-server",
  "version": "1.0.0",
  "scripts": { "start": "node index.js" },
  "dependencies": {
    "express": "^4.18.2",
    "socket.io": "^4.7.4",
    "multer": "^1.4.5-lts.1",
    "uuid": "^9.0.0"
  }
}
```

## server/index.js

```javascript
const express = require("express");
const http = require("http");
const { Server } = require("socket.io");
const multer = require("multer");
const path = require("path");
const fs = require("fs");
const { v4: uuidv4 } = require("uuid");

const app = express();
const server = http.createServer(app);
const io = new Server(server, { maxHttpBufferSize: 50 * 1024 * 1024 });

// 업로드 디렉토리 생성
const UPLOAD_DIR = path.join(__dirname, "uploads");
if (!fs.existsSync(UPLOAD_DIR)) fs.mkdirSync(UPLOAD_DIR, { recursive: true });

// 정적 파일 서빙
app.use(express.static(path.join(__dirname, "../client")));
app.use("/uploads", express.static(UPLOAD_DIR));

// 파일 타입별 아이콘 매핑
const FILE_ICONS = {
  image: "🖼️", video: "🎬", audio: "🎵",
  pdf: "📄", zip: "📦", code: "💻", doc: "📝", default: "📎"
};

function getFileCategory(mime) {
  if (!mime) return "default";
  if (mime.startsWith("image/")) return "image";
  if (mime.startsWith("video/")) return "video";
  if (mime.startsWith("audio/")) return "audio";
  if (mime.includes("pdf")) return "pdf";
  if (mime.includes("zip") || mime.includes("tar") || mime.includes("rar")) return "zip";
  if (mime.includes("javascript") || mime.includes("json") || mime.includes("html")) return "code";
  if (mime.includes("word") || mime.includes("document")) return "doc";
  return "default";
}

const users = new Map();

io.on("connection", (socket) => {
  console.log(`연결: ${socket.id}`);

  socket.on("join", (username) => {
    users.set(socket.id, { username, joinedAt: Date.now() });
    io.emit("system", { text: `${username} 님이 입장했습니다.`, users: [...users.values()] });
  });

  // 텍스트 메시지
  socket.on("message", (data) => {
    const user = users.get(socket.id);
    if (!user) return;
    io.emit("message", {
      id: uuidv4(), sender: user.username,
      text: data.text, timestamp: Date.now(), type: "text"
    });
  });

  // 바이너리 파일 수신
  socket.on("file-upload", (fileData, callback) => {
    const user = users.get(socket.id);
    if (!user) return callback({ error: "인증 필요" });

    const { name, mime, buffer } = fileData;
    const ext = path.extname(name);
    const savedName = `${uuidv4()}${ext}`;
    const filePath = path.join(UPLOAD_DIR, savedName);

    // 파일 저장
    fs.writeFile(filePath, Buffer.from(buffer), (err) => {
      if (err) return callback({ error: "저장 실패" });

      const category = getFileCategory(mime);
      const fileMsg = {
        id: uuidv4(), sender: user.username,
        type: "file", timestamp: Date.now(),
        file: {
          name, mime, category,
          icon: FILE_ICONS[category],
          size: buffer.byteLength,
          url: `/uploads/${savedName}`,
          isImage: mime && mime.startsWith("image/")
        }
      };
      io.emit("message", fileMsg);
      callback({ success: true, url: fileMsg.file.url });
    });
  });

  socket.on("disconnect", () => {
    const user = users.get(socket.id);
    users.delete(socket.id);
    if (user) {
      io.emit("system", { text: `${user.username} 님이 퇴장했습니다.`, users: [...users.values()] });
    }
  });
});

server.listen(3000, () => console.log("서버 실행: http://localhost:3000"));
```

## client/index.html

```html
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>실시간 파일 공유 채팅</title>
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <div id="app">
    <div id="login-screen">
      <h1>📂 파일 공유 채팅</h1>
      <input id="username-input" placeholder="닉네임 입력" maxlength="20" />
      <button id="join-btn">입장</button>
    </div>
    <div id="chat-screen" class="hidden">
      <header>
        <h2>📂 파일 공유 채팅</h2>
        <span id="user-count">0명 접속</span>
      </header>
      <div id="messages"></div>
      <div id="upload-progress" class="hidden">
        <div id="progress-bar"><div id="progress-fill"></div></div>
        <span id="progress-text">0%</span>
      </div>
      <div id="input-area">
        <label id="file-label" title="파일 첨부">📎
          <input type="file" id="file-input" multiple hidden />
        </label>
        <input id="msg-input" placeholder="메시지 입력..." />
        <button id="send-btn">전송</button>
      </div>
    </div>
  </div>
  <script src="/socket.io/socket.io.js"></script>
  <script src="app.js"></script>
</body>
</html>
```

## client/style.css

```css
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: "Apple SD Gothic Neo", sans-serif; background: #0f172a; color: #e2e8f0; height: 100vh; }
#app { max-width: 600px; margin: 0 auto; height: 100vh; display: flex; flex-direction: column; }
#login-screen { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; flex: 1; }
#login-screen h1 { font-size: 1.8rem; margin-bottom: 10px; }
#login-screen input { padding: 10px 16px; border-radius: 8px; border: 1px solid #334155; background: #1e293b; color: #fff; width: 240px; }
#login-screen button { padding: 10px 32px; border-radius: 8px; border: none; background: #3b82f6; color: #fff; cursor: pointer; font-weight: 600; }
.hidden { display: none !important; }
header { padding: 14px 16px; background: #1e293b; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; }
#messages { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 8px; }
.msg { padding: 8px 12px; border-radius: 10px; max-width: 85%; }
.msg.mine { align-self: flex-end; background: #1d4ed8; }
.msg.other { align-self: flex-start; background: #334155; }
.msg .sender { font-size: 0.75rem; color: #94a3b8; margin-bottom: 2px; }
.msg .text { word-break: break-word; }
.msg .file-card { background: #1e293b; border-radius: 8px; padding: 10px; margin-top: 4px; }
.msg .file-card img { max-width: 100%; border-radius: 6px; margin-top: 6px; }
.msg .file-card a { color: #60a5fa; text-decoration: none; }
.msg .file-icon { font-size: 1.5rem; margin-right: 6px; }
.msg .file-info { display: flex; align-items: center; }
.msg .file-size { font-size: 0.7rem; color: #64748b; margin-left: 8px; }
.system-msg { text-align: center; color: #64748b; font-size: 0.8rem; padding: 4px; }
#upload-progress { padding: 6px 16px; }
#progress-bar { height: 4px; background: #334155; border-radius: 2px; overflow: hidden; }
#progress-fill { height: 100%; background: #3b82f6; width: 0; transition: width 0.2s; }
#progress-text { font-size: 0.75rem; color: #94a3b8; }
#input-area { display: flex; gap: 8px; padding: 10px 12px; background: #1e293b; border-top: 1px solid #334155; }
#file-label { font-size: 1.4rem; cursor: pointer; display: flex; align-items: center; }
#msg-input { flex: 1; padding: 8px 12px; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: #fff; }
#send-btn { padding: 8px 16px; border-radius: 8px; border: none; background: #3b82f6; color: #fff; cursor: pointer; }
```

## client/app.js

```javascript
const socket = io();
let myName = "";

const $ = (sel) => document.querySelector(sel);
const loginScreen = $("#login-screen");
const chatScreen = $("#chat-screen");
const messages = $("#messages");
const msgInput = $("#msg-input");

// 로그인
$("#join-btn").addEventListener("click", () => {
  const name = $("#username-input").value.trim();
  if (!name) return;
  myName = name;
  socket.emit("join", myName);
  loginScreen.classList.add("hidden");
  chatScreen.classList.remove("hidden");
  msgInput.focus();
});

// 파일 크기 포맷
function formatSize(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

// 메시지 전송
$("#send-btn").addEventListener("click", sendText);
msgInput.addEventListener("keydown", (e) => { if (e.key === "Enter") sendText(); });

function sendText() {
  const text = msgInput.value.trim();
  if (!text) return;
  socket.emit("message", { text });
  msgInput.value = "";
}

// 파일 업로드
$("#file-input").addEventListener("change", (e) => {
  const files = Array.from(e.target.files);
  files.forEach(uploadFile);
  e.target.value = "";
});

function uploadFile(file) {
  if (file.size > 50 * 1024 * 1024) {
    alert("50MB 이하 파일만 전송 가능합니다.");
    return;
  }
  const progressEl = $("#upload-progress");
  const progressFill = $("#progress-fill");
  const progressText = $("#progress-text");
  progressEl.classList.remove("hidden");

  const reader = new FileReader();
  reader.onprogress = (ev) => {
    if (ev.lengthComputable) {
      const pct = Math.round((ev.loaded / ev.total) * 100);
      progressFill.style.width = pct + "%";
      progressText.textContent = pct + "%";
    }
  };
  reader.onload = () => {
    socket.emit("file-upload", {
      name: file.name, mime: file.type, buffer: reader.result
    }, (res) => {
      progressEl.classList.add("hidden");
      progressFill.style.width = "0";
      if (res.error) alert("업로드 실패: " + res.error);
    });
  };
  reader.readAsArrayBuffer(file);
}

// 메시지 수신
socket.on("message", (data) => {
  const isMine = data.sender === myName;
  const div = document.createElement("div");
  div.className = `msg ${isMine ? "mine" : "other"}`;

  let inner = `<div class="sender">${data.sender}</div>`;
  if (data.type === "text") {
    inner += `<div class="text">${escapeHtml(data.text)}</div>`;
  } else if (data.type === "file") {
    const f = data.file;
    inner += `<div class="file-card">`;
    inner += `<div class="file-info"><span class="file-icon">${f.icon}</span>`;
    inner += `<a href="${f.url}" download="${f.name}">${f.name}</a>`;
    inner += `<span class="file-size">${formatSize(f.size)}</span></div>`;
    if (f.isImage) inner += `<img src="${f.url}" alt="${f.name}" />`;
    inner += `</div>`;
  }
  div.innerHTML = inner;
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
});

socket.on("system", (data) => {
  const div = document.createElement("div");
  div.className = "system-msg";
  div.textContent = data.text;
  messages.appendChild(div);
  $("#user-count").textContent = data.users.length + "명 접속";
});

function escapeHtml(str) {
  const d = document.createElement("div");
  d.textContent = str;
  return d.innerHTML;
}
```

파일 업로드 시 바이너리를 Socket.IO로 직접 전송하고, 서버가 저장 후 URL을 브로드캐스트합니다. 이미지면 인라인 미리보기, 그 외 파일은 아이콘 + 다운로드 링크로 표시됩니다.'''),

    # ═══ 2. Socket.IO 이모지 + 리액션 시스템 ═══
    m("Socket.IO로 채팅 이모지 + 리액션 시스템 만들어줘 전체 코드로",
'''이모지 피커와 메시지 리액션이 포함된 채팅을 만들어 드릴게요.

## 폴더 구조

```
emoji-chat/
├── server/
│   ├── package.json
│   └── index.js
├── client/
│   ├── index.html
│   ├── style.css
│   └── app.js
```

## server/package.json

```json
{
  "name": "emoji-chat",
  "version": "1.0.0",
  "scripts": { "start": "node index.js" },
  "dependencies": {
    "express": "^4.18.2",
    "socket.io": "^4.7.4"
  }
}
```

## server/index.js

```javascript
const express = require("express");
const http = require("http");
const { Server } = require("socket.io");
const path = require("path");

const app = express();
const server = http.createServer(app);
const io = new Server(server);

app.use(express.static(path.join(__dirname, "../client")));

const users = new Map();
const messageStore = new Map(); // msgId -> { ...msg, reactions: { emoji: Set<userId> } }
let msgCounter = 0;

io.on("connection", (socket) => {
  socket.on("join", (username) => {
    users.set(socket.id, username);
    io.emit("system", `${username} 님이 입장했습니다.`);
    // 기존 메시지 + 리액션 동기화
    const history = [...messageStore.values()].map(serializeMsg);
    socket.emit("history", history);
  });

  socket.on("message", (text) => {
    const sender = users.get(socket.id);
    if (!sender || !text.trim()) return;
    const id = `msg-${++msgCounter}`;
    const msg = { id, sender, text: text.trim(), timestamp: Date.now(), reactions: {} };
    messageStore.set(id, msg);
    io.emit("message", serializeMsg(msg));
  });

  // 리액션 토글
  socket.on("toggle-reaction", ({ msgId, emoji }) => {
    const msg = messageStore.get(msgId);
    const userId = socket.id;
    if (!msg) return;

    if (!msg.reactions[emoji]) msg.reactions[emoji] = new Set();
    const set = msg.reactions[emoji];

    if (set.has(userId)) {
      set.delete(userId);
      if (set.size === 0) delete msg.reactions[emoji];
    } else {
      set.add(userId);
    }
    // 전체에 리액션 상태 브로드캐스트
    io.emit("reaction-update", { msgId, reactions: serializeReactions(msg.reactions) });
  });

  socket.on("disconnect", () => {
    const username = users.get(socket.id);
    users.delete(socket.id);
    if (username) io.emit("system", `${username} 님이 퇴장했습니다.`);
  });
});

function serializeReactions(reactions) {
  const result = {};
  for (const [emoji, userSet] of Object.entries(reactions)) {
    result[emoji] = [...userSet];
  }
  return result;
}

function serializeMsg(msg) {
  return { ...msg, reactions: serializeReactions(msg.reactions) };
}

server.listen(3000, () => console.log("서버: http://localhost:3000"));
```

## client/index.html

```html
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>이모지 리액션 채팅</title>
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <div id="app">
    <div id="login"><h1>😊 이모지 채팅</h1>
      <input id="name-input" placeholder="닉네임" /><button id="join-btn">입장</button>
    </div>
    <div id="chat" class="hidden">
      <header><h2>😊 이모지 채팅</h2></header>
      <div id="messages"></div>
      <div id="emoji-picker" class="hidden"></div>
      <div id="input-bar">
        <button id="emoji-btn">😊</button>
        <input id="msg-input" placeholder="메시지..." />
        <button id="send-btn">전송</button>
      </div>
    </div>
  </div>
  <script src="/socket.io/socket.io.js"></script>
  <script src="app.js"></script>
</body>
</html>
```

## client/style.css

```css
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: "Apple SD Gothic Neo", sans-serif; background: #0f172a; color: #e2e8f0; height: 100vh; }
#app { max-width: 600px; margin: 0 auto; height: 100vh; display: flex; flex-direction: column; }
#login { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; flex: 1; }
#login h1 { font-size: 2rem; }
#login input { padding: 10px 16px; border-radius: 8px; border: 1px solid #334155; background: #1e293b; color: #fff; width: 220px; }
#login button { padding: 10px 28px; border-radius: 8px; border: none; background: #8b5cf6; color: #fff; cursor: pointer; }
.hidden { display: none !important; }
header { padding: 14px 16px; background: #1e293b; border-bottom: 1px solid #334155; }
#messages { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 10px; }
.msg-wrap { max-width: 80%; }
.msg-wrap.mine { align-self: flex-end; }
.msg-wrap.other { align-self: flex-start; }
.msg-bubble { padding: 8px 14px; border-radius: 12px; position: relative; }
.mine .msg-bubble { background: #6d28d9; }
.other .msg-bubble { background: #334155; }
.sender-name { font-size: 0.7rem; color: #94a3b8; margin-bottom: 2px; }
.reactions-bar { display: flex; gap: 4px; flex-wrap: wrap; margin-top: 4px; }
.reaction-chip { display: flex; align-items: center; gap: 2px; padding: 2px 8px; border-radius: 12px; background: #1e293b; border: 1px solid #334155; cursor: pointer; font-size: 0.85rem; }
.reaction-chip.active { border-color: #8b5cf6; background: #2e1065; }
.reaction-chip .count { font-size: 0.75rem; color: #94a3b8; }
.add-reaction-btn { cursor: pointer; padding: 2px 6px; border-radius: 12px; background: #1e293b; border: 1px solid #334155; font-size: 0.85rem; }
.reaction-picker { position: absolute; background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 6px; display: flex; gap: 4px; flex-wrap: wrap; width: 180px; z-index: 10; }
.reaction-picker span { cursor: pointer; font-size: 1.2rem; padding: 2px; border-radius: 4px; }
.reaction-picker span:hover { background: #334155; }
#emoji-picker { background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 10px; margin: 0 12px; max-height: 200px; overflow-y: auto; }
.emoji-category { margin-bottom: 8px; }
.emoji-category-title { font-size: 0.7rem; color: #64748b; margin-bottom: 4px; text-transform: uppercase; }
.emoji-grid { display: flex; flex-wrap: wrap; gap: 4px; }
.emoji-grid span { cursor: pointer; font-size: 1.3rem; padding: 3px; border-radius: 4px; }
.emoji-grid span:hover { background: #334155; }
#input-bar { display: flex; gap: 8px; padding: 10px 12px; background: #1e293b; border-top: 1px solid #334155; }
#emoji-btn { font-size: 1.3rem; background: none; border: none; cursor: pointer; }
#msg-input { flex: 1; padding: 8px 12px; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: #fff; }
#send-btn { padding: 8px 16px; border-radius: 8px; border: none; background: #8b5cf6; color: #fff; cursor: pointer; }
.system-msg { text-align: center; color: #64748b; font-size: 0.8rem; }
```

## client/app.js

```javascript
const socket = io();
let myName = "";
const $ = (s) => document.querySelector(s);

// 이모지 데이터 (카테고리별)
const EMOJI_DATA = {
  "스마일": ["😀","😃","😄","😁","😆","😅","🤣","😂","🙂","😊","😇","😍","🤩","😘","😋","😛","😜","🤗","🤔","😐","😑","😶","🙄","😏","😬","🤥","😌","😔","😴","🤢","😷","🤒"],
  "손/몸": ["👍","👎","👏","🙌","🤝","✌️","🤞","🤟","🤘","👌","🙏","💪","👈","👉","👆","👇","✋","🤚","🖐️","🖖"],
  "하트": ["❤️","🧡","💛","💚","💙","💜","🖤","🤍","💔","❣️","💕","💞","💓","💗","💖","💘","💝"],
  "사물": ["🔥","✨","🎉","🎊","💯","💢","💬","👀","🚀","⭐","🌟","💡","🎯","🏆","📌","✅","❌","⚠️","💊","🔔"]
};

// 메시지 리액션용 이모지 (빠른 선택)
const REACTION_EMOJIS = ["👍","❤️","😂","😮","😢","🔥","👏","🎉","🤔","👀"];

// 로그인
$("#join-btn").addEventListener("click", join);
$("#name-input").addEventListener("keydown", (e) => { if (e.key === "Enter") join(); });
function join() {
  const name = $("#name-input").value.trim();
  if (!name) return;
  myName = name;
  socket.emit("join", myName);
  $("#login").classList.add("hidden");
  $("#chat").classList.remove("hidden");
  buildEmojiPicker();
}

// 이모지 피커 생성
function buildEmojiPicker() {
  const picker = $("#emoji-picker");
  picker.innerHTML = "";
  for (const [category, emojis] of Object.entries(EMOJI_DATA)) {
    const sec = document.createElement("div");
    sec.className = "emoji-category";
    sec.innerHTML = `<div class="emoji-category-title">${category}</div><div class="emoji-grid">${
      emojis.map((e) => `<span data-emoji="${e}">${e}</span>`).join("")
    }</div>`;
    picker.appendChild(sec);
  }
  picker.addEventListener("click", (e) => {
    const emoji = e.target.dataset.emoji;
    if (emoji) {
      const input = $("#msg-input");
      input.value += emoji;
      input.focus();
    }
  });
}

// 이모지 피커 토글
$("#emoji-btn").addEventListener("click", () => {
  $("#emoji-picker").classList.toggle("hidden");
});

// 전송
function sendMsg() {
  const text = $("#msg-input").value.trim();
  if (!text) return;
  socket.emit("message", text);
  $("#msg-input").value = "";
  $("#emoji-picker").classList.add("hidden");
}
$("#send-btn").addEventListener("click", sendMsg);
$("#msg-input").addEventListener("keydown", (e) => { if (e.key === "Enter") sendMsg(); });

// 메시지 렌더
function renderMsg(data) {
  const isMine = data.sender === myName;
  const wrap = document.createElement("div");
  wrap.className = `msg-wrap ${isMine ? "mine" : "other"}`;
  wrap.dataset.msgId = data.id;

  wrap.innerHTML = `
    <div class="sender-name">${data.sender}</div>
    <div class="msg-bubble">${escapeHtml(data.text)}</div>
    <div class="reactions-bar">${renderReactions(data.id, data.reactions)}</div>
  `;
  $("#messages").appendChild(wrap);
  $("#messages").scrollTop = $("#messages").scrollHeight;
}

function renderReactions(msgId, reactions) {
  let html = "";
  for (const [emoji, userIds] of Object.entries(reactions)) {
    const active = userIds.includes(socket.id) ? "active" : "";
    html += `<span class="reaction-chip ${active}" data-emoji="${emoji}" data-msg="${msgId}">
      ${emoji} <span class="count">${userIds.length}</span></span>`;
  }
  html += `<span class="add-reaction-btn" data-msg="${msgId}">+</span>`;
  return html;
}

// 리액션 클릭 위임
document.addEventListener("click", (e) => {
  // 기존 리액션 토글
  const chip = e.target.closest(".reaction-chip");
  if (chip) {
    socket.emit("toggle-reaction", { msgId: chip.dataset.msg, emoji: chip.dataset.emoji });
    return;
  }
  // + 버튼 → 리액션 피커
  const addBtn = e.target.closest(".add-reaction-btn");
  if (addBtn) {
    showReactionPicker(addBtn, addBtn.dataset.msg);
    return;
  }
  // 리액션 피커 내 선택
  const rp = e.target.closest(".reaction-picker span");
  if (rp) {
    socket.emit("toggle-reaction", { msgId: rp.dataset.msg, emoji: rp.dataset.emoji });
    document.querySelectorAll(".reaction-picker").forEach((el) => el.remove());
    return;
  }
  // 외부 클릭 시 피커 닫기
  document.querySelectorAll(".reaction-picker").forEach((el) => el.remove());
});

function showReactionPicker(anchor, msgId) {
  document.querySelectorAll(".reaction-picker").forEach((el) => el.remove());
  const picker = document.createElement("div");
  picker.className = "reaction-picker";
  picker.innerHTML = REACTION_EMOJIS.map((e) =>
    `<span data-emoji="${e}" data-msg="${msgId}">${e}</span>`
  ).join("");
  anchor.parentElement.appendChild(picker);
}

// 리액션 업데이트 수신
socket.on("reaction-update", ({ msgId, reactions }) => {
  const wrap = document.querySelector(`[data-msg-id="${msgId}"]`);
  if (!wrap) return;
  const bar = wrap.querySelector(".reactions-bar");
  bar.innerHTML = renderReactions(msgId, reactions);
});

socket.on("message", renderMsg);
socket.on("history", (msgs) => msgs.forEach(renderMsg));
socket.on("system", (text) => {
  const div = document.createElement("div");
  div.className = "system-msg";
  div.textContent = text;
  $("#messages").appendChild(div);
});

function escapeHtml(s) { const d = document.createElement("div"); d.textContent = s; return d.innerHTML; }
```

카테고리별 이모지 피커, 메시지별 리액션 토글(동일 이모지 다시 누르면 취소), 리액션 수 카운트가 모두 실시간 동기화됩니다.'''),

    # ═══ 3. WebSocket 실시간 위치 공유 ═══
    m("WebSocket으로 실시간 위치 공유 시스템 만들어줘 전체 코드로",
'''실시간 위치 공유 시스템을 만들어 드릴게요. GPS 좌표를 그리드 맵에 표시합니다.

## 폴더 구조

```
location-share/
├── server/
│   ├── package.json
│   └── index.js
├── client/
│   ├── index.html
│   ├── style.css
│   └── app.js
```

## server/package.json

```json
{
  "name": "location-share",
  "version": "1.0.0",
  "scripts": { "start": "node index.js" },
  "dependencies": {
    "express": "^4.18.2",
    "socket.io": "^4.7.4"
  }
}
```

## server/index.js

```javascript
const express = require("express");
const http = require("http");
const { Server } = require("socket.io");
const path = require("path");

const app = express();
const server = http.createServer(app);
const io = new Server(server);

app.use(express.static(path.join(__dirname, "../client")));

// 유저별 위치 및 이동 기록
const users = new Map(); // socketId -> { name, lat, lng, color, trail: [{lat,lng,ts}] }

const COLORS = ["#ef4444","#3b82f6","#22c55e","#f59e0b","#8b5cf6","#ec4899","#14b8a6","#f97316"];
let colorIdx = 0;

// 두 좌표 간 거리 (Haversine, km)
function haversine(lat1, lng1, lat2, lng2) {
  const R = 6371;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLng = (lng2 - lng1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
    Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

io.on("connection", (socket) => {
  socket.on("join", (name) => {
    const color = COLORS[colorIdx++ % COLORS.length];
    users.set(socket.id, { name, lat: 0, lng: 0, color, trail: [] });
    io.emit("user-list", serializeUsers());
    io.emit("system", `${name} 님이 위치 공유를 시작했습니다.`);
  });

  socket.on("update-location", ({ lat, lng }) => {
    const user = users.get(socket.id);
    if (!user) return;
    user.lat = lat;
    user.lng = lng;
    user.trail.push({ lat, lng, ts: Date.now() });
    // 최근 100개만 유지
    if (user.trail.length > 100) user.trail = user.trail.slice(-100);

    // 모든 유저 간 거리 계산
    const distances = [];
    const allUsers = [...users.entries()];
    for (let i = 0; i < allUsers.length; i++) {
      for (let j = i + 1; j < allUsers.length; j++) {
        const [, u1] = allUsers[i];
        const [, u2] = allUsers[j];
        if (u1.lat && u2.lat) {
          distances.push({
            from: u1.name, to: u2.name,
            km: haversine(u1.lat, u1.lng, u2.lat, u2.lng).toFixed(2)
          });
        }
      }
    }

    io.emit("locations", { users: serializeUsers(), distances });
  });

  socket.on("disconnect", () => {
    const user = users.get(socket.id);
    users.delete(socket.id);
    if (user) {
      io.emit("system", `${user.name} 님이 나갔습니다.`);
      io.emit("user-list", serializeUsers());
    }
  });
});

function serializeUsers() {
  return [...users.entries()].map(([id, u]) => ({
    id, name: u.name, lat: u.lat, lng: u.lng, color: u.color,
    trail: u.trail.slice(-50)
  }));
}

server.listen(3000, () => console.log("서버: http://localhost:3000"));
```

## client/index.html

```html
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>실시간 위치 공유</title>
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <div id="app">
    <div id="login">
      <h1>📍 실시간 위치 공유</h1>
      <input id="name-input" placeholder="이름 입력" />
      <button id="join-btn">시작</button>
    </div>
    <div id="main" class="hidden">
      <header>
        <h2>📍 위치 공유</h2>
        <span id="my-coords">좌표 가져오는 중...</span>
      </header>
      <div id="map-container">
        <canvas id="map-canvas"></canvas>
      </div>
      <div id="sidebar">
        <h3>접속 유저</h3>
        <ul id="user-list"></ul>
        <h3>거리 정보</h3>
        <ul id="distance-list"></ul>
      </div>
      <div id="log"></div>
    </div>
  </div>
  <script src="/socket.io/socket.io.js"></script>
  <script src="app.js"></script>
</body>
</html>
```

## client/style.css

```css
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: "Apple SD Gothic Neo", sans-serif; background: #0f172a; color: #e2e8f0; height: 100vh; }
#app { height: 100vh; display: flex; flex-direction: column; }
#login { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; flex: 1; }
#login h1 { font-size: 1.8rem; }
#login input { padding: 10px 16px; border-radius: 8px; border: 1px solid #334155; background: #1e293b; color: #fff; width: 220px; }
#login button { padding: 10px 28px; border-radius: 8px; border: none; background: #22c55e; color: #fff; cursor: pointer; font-weight: 600; }
.hidden { display: none !important; }
header { padding: 12px 16px; background: #1e293b; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; }
#my-coords { font-size: 0.8rem; color: #94a3b8; }
#main { flex: 1; display: grid; grid-template-columns: 1fr 240px; grid-template-rows: auto 1fr auto; }
header { grid-column: 1 / -1; }
#map-container { background: #1e293b; position: relative; overflow: hidden; }
#map-canvas { width: 100%; height: 100%; }
#sidebar { background: #1e293b; border-left: 1px solid #334155; padding: 12px; overflow-y: auto; }
#sidebar h3 { font-size: 0.85rem; color: #64748b; margin: 10px 0 6px; }
#sidebar ul { list-style: none; }
#sidebar li { font-size: 0.85rem; padding: 4px 0; display: flex; align-items: center; gap: 6px; }
.user-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
#log { grid-column: 1 / -1; padding: 8px 16px; background: #0f172a; border-top: 1px solid #334155; font-size: 0.8rem; color: #64748b; max-height: 60px; overflow-y: auto; }
```

## client/app.js

```javascript
const socket = io();
let myName = "";
const $ = (s) => document.querySelector(s);

// 로그인
$("#join-btn").addEventListener("click", () => {
  myName = $("#name-input").value.trim();
  if (!myName) return;
  socket.emit("join", myName);
  $("#login").classList.add("hidden");
  $("#main").classList.remove("hidden");
  initMap();
  startGPS();
});

// GPS 추적
function startGPS() {
  if (!navigator.geolocation) {
    $("#my-coords").textContent = "GPS 미지원 브라우저";
    // 테스트 용도: 랜덤 위치 시뮬레이션
    simulateLocation();
    return;
  }
  navigator.geolocation.watchPosition(
    (pos) => {
      const { latitude: lat, longitude: lng } = pos.coords;
      $("#my-coords").textContent = `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
      socket.emit("update-location", { lat, lng });
    },
    () => {
      $("#my-coords").textContent = "GPS 권한 거부 - 시뮬레이션 모드";
      simulateLocation();
    },
    { enableHighAccuracy: true, maximumAge: 3000 }
  );
}

// GPS 불가 시 시뮬레이션
function simulateLocation() {
  let lat = 37.5665 + (Math.random() - 0.5) * 0.02;
  let lng = 126.978 + (Math.random() - 0.5) * 0.02;
  setInterval(() => {
    lat += (Math.random() - 0.5) * 0.001;
    lng += (Math.random() - 0.5) * 0.001;
    $("#my-coords").textContent = `${lat.toFixed(5)}, ${lng.toFixed(5)} (시뮬레이션)`;
    socket.emit("update-location", { lat, lng });
  }, 2000);
}

// 캔버스 맵
const canvas = $("#map-canvas");
const ctx = canvas.getContext("2d");
let currentUsers = [];

function initMap() {
  resizeCanvas();
  window.addEventListener("resize", resizeCanvas);
  requestAnimationFrame(drawLoop);
}

function resizeCanvas() {
  const container = $("#map-container");
  canvas.width = container.clientWidth;
  canvas.height = container.clientHeight;
}

function drawLoop() {
  drawMap();
  requestAnimationFrame(drawLoop);
}

function drawMap() {
  const W = canvas.width;
  const H = canvas.height;
  ctx.fillStyle = "#1e293b";
  ctx.fillRect(0, 0, W, H);

  // 그리드
  ctx.strokeStyle = "#334155";
  ctx.lineWidth = 0.5;
  for (let x = 0; x < W; x += 40) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke(); }
  for (let y = 0; y < H; y += 40) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke(); }

  if (currentUsers.length === 0) return;

  // 위경도 범위 계산
  let minLat = Infinity, maxLat = -Infinity, minLng = Infinity, maxLng = -Infinity;
  for (const u of currentUsers) {
    if (u.lat === 0 && u.lng === 0) continue;
    minLat = Math.min(minLat, u.lat); maxLat = Math.max(maxLat, u.lat);
    minLng = Math.min(minLng, u.lng); maxLng = Math.max(maxLng, u.lng);
    for (const t of u.trail) {
      minLat = Math.min(minLat, t.lat); maxLat = Math.max(maxLat, t.lat);
      minLng = Math.min(minLng, t.lng); maxLng = Math.max(maxLng, t.lng);
    }
  }

  const pad = 0.002;
  minLat -= pad; maxLat += pad; minLng -= pad; maxLng += pad;
  const latRange = maxLat - minLat || 0.01;
  const lngRange = maxLng - minLng || 0.01;
  const margin = 40;

  function toXY(lat, lng) {
    return {
      x: margin + ((lng - minLng) / lngRange) * (W - margin * 2),
      y: margin + ((maxLat - lat) / latRange) * (H - margin * 2)
    };
  }

  // 이동 경로 (trail)
  for (const u of currentUsers) {
    if (u.trail.length < 2) continue;
    ctx.beginPath();
    ctx.strokeStyle = u.color + "60";
    ctx.lineWidth = 2;
    const first = toXY(u.trail[0].lat, u.trail[0].lng);
    ctx.moveTo(first.x, first.y);
    for (let i = 1; i < u.trail.length; i++) {
      const p = toXY(u.trail[i].lat, u.trail[i].lng);
      ctx.lineTo(p.x, p.y);
    }
    ctx.stroke();
  }

  // 유저 마커
  for (const u of currentUsers) {
    if (u.lat === 0 && u.lng === 0) continue;
    const { x, y } = toXY(u.lat, u.lng);
    // 외곽 글로우
    ctx.beginPath();
    ctx.arc(x, y, 12, 0, Math.PI * 2);
    ctx.fillStyle = u.color + "30";
    ctx.fill();
    // 내부 원
    ctx.beginPath();
    ctx.arc(x, y, 6, 0, Math.PI * 2);
    ctx.fillStyle = u.color;
    ctx.fill();
    // 이름
    ctx.fillStyle = "#e2e8f0";
    ctx.font = "11px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(u.name, x, y - 16);
  }
}

// 소켓 이벤트
socket.on("locations", ({ users, distances }) => {
  currentUsers = users;
  // 유저 목록
  const ul = $("#user-list");
  ul.innerHTML = users.map((u) =>
    `<li><span class="user-dot" style="background:${u.color}"></span>${u.name} (${u.lat.toFixed(4)}, ${u.lng.toFixed(4)})</li>`
  ).join("");
  // 거리 목록
  const dl = $("#distance-list");
  dl.innerHTML = distances.map((d) =>
    `<li>${d.from} ↔ ${d.to}: ${d.km} km</li>`
  ).join("");
});

socket.on("user-list", (users) => {
  currentUsers = users;
  const ul = $("#user-list");
  ul.innerHTML = users.map((u) =>
    `<li><span class="user-dot" style="background:${u.color}"></span>${u.name}</li>`
  ).join("");
});

socket.on("system", (text) => {
  const log = $("#log");
  log.textContent = text;
});
```

GPS가 지원되면 실제 좌표를, 불가 시 서울 근처 시뮬레이션 좌표를 사용합니다. 캔버스 위에 그리드 맵을 그리고, 유저 마커와 이동 경로(trail)를 실시간 렌더링합니다.'''),

    # ═══ 4. Socket.IO 실시간 코드 공유/라이브 코딩 ═══
    m("Socket.IO로 실시간 코드 공유/라이브 코딩 만들어줘 전체 코드로",
'''실시간 코드 공유 에디터를 만들어 드릴게요. 코드 동기화, 커서 위치 공유, 구문 강조를 지원합니다.

## 폴더 구조

```
live-code/
├── server/
│   ├── package.json
│   └── index.js
├── client/
│   ├── index.html
│   ├── style.css
│   └── app.js
```

## server/package.json

```json
{
  "name": "live-code",
  "version": "1.0.0",
  "scripts": { "start": "node index.js" },
  "dependencies": {
    "express": "^4.18.2",
    "socket.io": "^4.7.4"
  }
}
```

## server/index.js

```javascript
const express = require("express");
const http = require("http");
const { Server } = require("socket.io");
const path = require("path");

const app = express();
const server = http.createServer(app);
const io = new Server(server);

app.use(express.static(path.join(__dirname, "../client")));

// 방별 코드 상태
const rooms = new Map(); // roomId -> { code, language, users: Map<socketId, { name, color, cursor }> }
const COLORS = ["#ef4444","#3b82f6","#22c55e","#f59e0b","#8b5cf6","#ec4899","#14b8a6","#f97316"];
let colorIdx = 0;

function getOrCreateRoom(roomId) {
  if (!rooms.has(roomId)) {
    rooms.set(roomId, {
      code: '// 여기에 코드를 작성하세요\\nconsole.log("Hello, World!");\\n',
      language: "javascript",
      users: new Map()
    });
  }
  return rooms.get(roomId);
}

io.on("connection", (socket) => {
  let currentRoom = null;

  socket.on("join-room", ({ roomId, name }) => {
    currentRoom = roomId;
    socket.join(roomId);
    const room = getOrCreateRoom(roomId);
    const color = COLORS[colorIdx++ % COLORS.length];
    room.users.set(socket.id, { name, color, cursor: { line: 0, col: 0 } });

    // 현재 상태 전송
    socket.emit("room-state", {
      code: room.code,
      language: room.language,
      users: serializeUsers(room)
    });

    // 다른 유저에게 알림
    socket.to(roomId).emit("user-joined", {
      id: socket.id, name, color,
      users: serializeUsers(room)
    });
  });

  // 코드 변경
  socket.on("code-change", ({ code }) => {
    if (!currentRoom) return;
    const room = rooms.get(currentRoom);
    if (!room) return;
    room.code = code;
    socket.to(currentRoom).emit("code-update", { code, from: socket.id });
  });

  // 언어 변경
  socket.on("language-change", (language) => {
    if (!currentRoom) return;
    const room = rooms.get(currentRoom);
    if (!room) return;
    room.language = language;
    io.to(currentRoom).emit("language-update", language);
  });

  // 커서 위치
  socket.on("cursor-move", (cursor) => {
    if (!currentRoom) return;
    const room = rooms.get(currentRoom);
    if (!room) return;
    const user = room.users.get(socket.id);
    if (user) user.cursor = cursor;
    socket.to(currentRoom).emit("cursor-update", {
      id: socket.id, cursor, name: user?.name, color: user?.color
    });
  });

  socket.on("disconnect", () => {
    if (!currentRoom) return;
    const room = rooms.get(currentRoom);
    if (!room) return;
    const user = room.users.get(socket.id);
    room.users.delete(socket.id);
    if (user) {
      io.to(currentRoom).emit("user-left", {
        id: socket.id, name: user.name,
        users: serializeUsers(room)
      });
    }
    if (room.users.size === 0) rooms.delete(currentRoom);
  });
});

function serializeUsers(room) {
  return [...room.users.entries()].map(([id, u]) => ({ id, ...u }));
}

server.listen(3000, () => console.log("서버: http://localhost:3000"));
```

## client/index.html

```html
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>라이브 코딩</title>
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <div id="app">
    <div id="login">
      <h1>💻 라이브 코딩</h1>
      <input id="name-input" placeholder="이름" />
      <input id="room-input" placeholder="방 이름 (기본: main)" value="main" />
      <button id="join-btn">입장</button>
    </div>
    <div id="editor-screen" class="hidden">
      <header>
        <div class="header-left">
          <h2>💻 라이브 코딩</h2>
          <select id="lang-select">
            <option value="javascript">JavaScript</option>
            <option value="python">Python</option>
            <option value="html">HTML</option>
            <option value="css">CSS</option>
            <option value="java">Java</option>
            <option value="cpp">C++</option>
          </select>
        </div>
        <div id="user-avatars"></div>
      </header>
      <div id="editor-container">
        <div id="line-numbers"></div>
        <div id="code-layer">
          <pre id="highlighted-code"></pre>
          <textarea id="code-input" spellcheck="false"></textarea>
        </div>
        <div id="cursors-layer"></div>
      </div>
      <footer>
        <span id="cursor-pos">줄 1, 열 1</span>
        <span id="lang-display">JavaScript</span>
      </footer>
    </div>
  </div>
  <script src="/socket.io/socket.io.js"></script>
  <script src="app.js"></script>
</body>
</html>
```

## client/style.css

```css
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: "Apple SD Gothic Neo", sans-serif; background: #1e1e2e; color: #cdd6f4; height: 100vh; }
#app { height: 100vh; display: flex; flex-direction: column; }
#login { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; flex: 1; }
#login h1 { font-size: 2rem; margin-bottom: 10px; }
#login input { padding: 10px 16px; border-radius: 8px; border: 1px solid #45475a; background: #313244; color: #cdd6f4; width: 240px; }
#login button { padding: 10px 28px; border-radius: 8px; border: none; background: #89b4fa; color: #1e1e2e; cursor: pointer; font-weight: 600; }
.hidden { display: none !important; }
header { padding: 10px 16px; background: #181825; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #313244; }
.header-left { display: flex; align-items: center; gap: 12px; }
#lang-select { padding: 4px 8px; border-radius: 6px; border: 1px solid #45475a; background: #313244; color: #cdd6f4; }
#user-avatars { display: flex; gap: 6px; }
.avatar { width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 0.7rem; color: #fff; font-weight: 600; }
#editor-container { flex: 1; display: flex; position: relative; overflow: auto; background: #1e1e2e; }
#line-numbers { width: 50px; background: #181825; padding: 12px 8px; text-align: right; font-family: "Fira Code", monospace; font-size: 13px; color: #585b70; line-height: 1.5; user-select: none; flex-shrink: 0; }
#code-layer { flex: 1; position: relative; }
#highlighted-code { position: absolute; top: 0; left: 0; width: 100%; padding: 12px; font-family: "Fira Code", monospace; font-size: 13px; line-height: 1.5; pointer-events: none; white-space: pre-wrap; word-wrap: break-word; margin: 0; color: #cdd6f4; }
#code-input { position: absolute; top: 0; left: 0; width: 100%; height: 100%; padding: 12px; font-family: "Fira Code", monospace; font-size: 13px; line-height: 1.5; background: transparent; color: transparent; caret-color: #f5e0dc; border: none; outline: none; resize: none; white-space: pre-wrap; word-wrap: break-word; }
#cursors-layer { position: absolute; top: 0; left: 50px; pointer-events: none; }
.remote-cursor { position: absolute; width: 2px; height: 18px; animation: blink 1s infinite; }
.remote-cursor-label { position: absolute; top: -18px; left: 0; font-size: 10px; padding: 1px 4px; border-radius: 3px; white-space: nowrap; color: #fff; }
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
footer { padding: 6px 16px; background: #181825; display: flex; justify-content: space-between; font-size: 0.8rem; color: #585b70; border-top: 1px solid #313244; }
/* 구문 강조 */
.kw { color: #cba6f7; } .str { color: #a6e3a1; } .num { color: #fab387; }
.cmt { color: #585b70; font-style: italic; } .fn { color: #89b4fa; } .op { color: #f38ba8; }
.tag { color: #f38ba8; } .attr { color: #fab387; } .val { color: #a6e3a1; }
```

## client/app.js

```javascript
const socket = io();
const $ = (s) => document.querySelector(s);
let myName = "";
let ignoreChange = false;

// 간단한 구문 강조 (정규식 기반)
const RULES = {
  javascript: [
    [/(\/\/.*)/g, "cmt"],
    [/(\/\*[\s\S]*?\*\/)/g, "cmt"],
    [/\b(const|let|var|function|return|if|else|for|while|class|import|export|from|default|new|this|async|await|try|catch|throw|switch|case|break|continue|typeof|instanceof)\b/g, "kw"],
    [/("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`)/g, "str"],
    [/\b(\d+\.?\d*)\b/g, "num"],
    [/\b([a-zA-Z_]\w*)\s*(?=\()/g, "fn"],
    [/([\+\-\*\/\=\!\<\>\&\|\?]+)/g, "op"]
  ],
  python: [
    [/(#.*)/g, "cmt"],
    [/\b(def|class|import|from|return|if|elif|else|for|while|try|except|finally|with|as|yield|lambda|pass|break|continue|and|or|not|in|is|None|True|False|self)\b/g, "kw"],
    [/(\"\"\"[\\s\\S]*?\"\"\"|'[^']*'|"(?:[^\\"\\\\]|\\\\.)*")/g, "str"],
    [/\b(\d+\.?\d*)\b/g, "num"],
    [/\b([a-zA-Z_]\w*)\s*(?=\()/g, "fn"]
  ],
  html: [
    [/(<!--[\s\S]*?-->)/g, "cmt"],
    [/(<\/?[a-zA-Z][a-zA-Z0-9]*)/g, "tag"],
    [/\b([a-zA-Z-]+)(=)/g, "attr"],
    [/("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g, "val"]
  ],
  css: [
    [/(\/\*[\s\S]*?\*\/)/g, "cmt"],
    [/([.#]?[a-zA-Z][\w-]*)\s*(?=\{)/g, "fn"],
    [/\b([a-zA-Z-]+)\s*(?=:)/g, "attr"],
    [/("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g, "str"],
    [/\b(\d+\.?\d*(px|em|rem|%|vh|vw)?)\b/g, "num"]
  ]
};

function highlight(code, lang) {
  let escaped = code.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const rules = RULES[lang] || RULES.javascript;
  for (const [regex, cls] of rules) {
    escaped = escaped.replace(regex, (m) => `<span class="${cls}">${m}</span>`);
  }
  return escaped;
}

// 줄 번호 업데이트
function updateLineNumbers(code) {
  const lines = code.split("\\n").length;
  const nums = Array.from({ length: lines }, (_, i) => i + 1).join("\\n");
  $("#line-numbers").textContent = nums;
}

// 로그인
$("#join-btn").addEventListener("click", () => {
  myName = $("#name-input").value.trim();
  const room = $("#room-input").value.trim() || "main";
  if (!myName) return;
  socket.emit("join-room", { roomId: room, name: myName });
  $("#login").classList.add("hidden");
  $("#editor-screen").classList.remove("hidden");
});

// 코드 입력
const codeInput = $("#code-input");
const highlighted = $("#highlighted-code");

codeInput.addEventListener("input", () => {
  if (ignoreChange) return;
  const code = codeInput.value;
  const lang = $("#lang-select").value;
  highlighted.innerHTML = highlight(code, lang);
  updateLineNumbers(code);
  socket.emit("code-change", { code });
});

// 커서 위치 추적
codeInput.addEventListener("keyup", reportCursor);
codeInput.addEventListener("click", reportCursor);

function reportCursor() {
  const val = codeInput.value;
  const pos = codeInput.selectionStart;
  const lines = val.substring(0, pos).split("\\n");
  const line = lines.length;
  const col = lines[lines.length - 1].length + 1;
  $("#cursor-pos").textContent = `줄 ${line}, 열 ${col}`;
  socket.emit("cursor-move", { line, col });
}

// 언어 선택
$("#lang-select").addEventListener("change", (e) => {
  const lang = e.target.value;
  socket.emit("language-change", lang);
  highlighted.innerHTML = highlight(codeInput.value, lang);
  $("#lang-display").textContent = e.target.options[e.target.selectedIndex].text;
});

// 소켓 이벤트
socket.on("room-state", ({ code, language, users }) => {
  codeInput.value = code;
  highlighted.innerHTML = highlight(code, language);
  updateLineNumbers(code);
  $("#lang-select").value = language;
  renderUsers(users);
});

socket.on("code-update", ({ code }) => {
  ignoreChange = true;
  const pos = codeInput.selectionStart;
  codeInput.value = code;
  codeInput.selectionStart = codeInput.selectionEnd = pos;
  const lang = $("#lang-select").value;
  highlighted.innerHTML = highlight(code, lang);
  updateLineNumbers(code);
  ignoreChange = false;
});

socket.on("language-update", (lang) => {
  $("#lang-select").value = lang;
  highlighted.innerHTML = highlight(codeInput.value, lang);
});

socket.on("cursor-update", ({ id, cursor, name, color }) => {
  renderRemoteCursor(id, cursor, name, color);
});

socket.on("user-joined", ({ users }) => renderUsers(users));
socket.on("user-left", ({ users }) => renderUsers(users));

function renderUsers(users) {
  const container = $("#user-avatars");
  container.innerHTML = users.map((u) =>
    `<div class="avatar" style="background:${u.color}" title="${u.name}">${u.name[0]}</div>`
  ).join("");
}

// 원격 커서 렌더
const remoteCursors = {};
function renderRemoteCursor(id, cursor, name, color) {
  let el = remoteCursors[id];
  if (!el) {
    el = document.createElement("div");
    el.className = "remote-cursor";
    el.innerHTML = `<div class="remote-cursor-label" style="background:${color}">${name}</div>`;
    el.style.background = color;
    $("#cursors-layer").appendChild(el);
    remoteCursors[id] = el;
  }
  const charW = 7.8;
  const lineH = 19.5;
  el.style.left = ((cursor.col - 1) * charW + 12) + "px";
  el.style.top = ((cursor.line - 1) * lineH + 12) + "px";
}

socket.on("user-left", ({ id }) => {
  if (remoteCursors[id]) {
    remoteCursors[id].remove();
    delete remoteCursors[id];
  }
});
```

코드 에디터에서 여러 사용자가 동시에 편집하면 실시간 동기화되고, 각 유저의 커서가 색상별로 표시됩니다. 정규식 기반 구문 강조로 JavaScript, Python, HTML, CSS를 지원합니다.'''),

    # ═══ 5. WebSocket 게임 로비 + 매칭 시스템 ═══
    m("WebSocket으로 실시간 게임 로비 + 매칭 시스템 만들어줘 전체 코드로",
'''게임 로비, ELO 매칭, 방 생성, 레디 체크를 포함한 시스템을 만들어 드릴게요.

## 폴더 구조

```
game-lobby/
├── server/
│   ├── package.json
│   └── index.js
├── client/
│   ├── index.html
│   ├── style.css
│   └── app.js
```

## server/package.json

```json
{
  "name": "game-lobby",
  "version": "1.0.0",
  "scripts": { "start": "node index.js" },
  "dependencies": {
    "express": "^4.18.2",
    "socket.io": "^4.7.4"
  }
}
```

## server/index.js

```javascript
const express = require("express");
const http = require("http");
const { Server } = require("socket.io");
const path = require("path");

const app = express();
const server = http.createServer(app);
const io = new Server(server);

app.use(express.static(path.join(__dirname, "../client")));

// 데이터 구조
const players = new Map();     // socketId -> { name, elo, status, roomId }
const rooms = new Map();       // roomId -> { id, name, host, maxPlayers, mode, players: Map, status, countdown }
const matchQueue = [];         // 매칭 대기열: [{ socketId, elo, joinedAt }]
let roomCounter = 0;

const MODES = ["1v1", "2v2", "FFA-4"];
const MODE_SIZES = { "1v1": 2, "2v2": 4, "FFA-4": 4 };

io.on("connection", (socket) => {
  // 로그인
  socket.on("login", (name) => {
    const elo = 1000 + Math.floor(Math.random() * 500);
    players.set(socket.id, { name, elo, status: "lobby", roomId: null });
    socket.emit("logged-in", { name, elo });
    broadcastLobby();
  });

  // 방 생성
  socket.on("create-room", ({ name, mode }) => {
    const player = players.get(socket.id);
    if (!player || player.roomId) return;
    const roomId = `room-${++roomCounter}`;
    const maxPlayers = MODE_SIZES[mode] || 2;
    const room = {
      id: roomId, name, host: socket.id, maxPlayers, mode,
      players: new Map([[socket.id, { name: player.name, elo: player.elo, ready: false }]]),
      status: "waiting", countdown: null
    };
    rooms.set(roomId, room);
    player.roomId = roomId;
    player.status = "in-room";
    socket.join(roomId);
    socket.emit("joined-room", serializeRoom(room));
    broadcastLobby();
  });

  // 방 참가
  socket.on("join-room", (roomId) => {
    const player = players.get(socket.id);
    const room = rooms.get(roomId);
    if (!player || !room || player.roomId) return;
    if (room.players.size >= room.maxPlayers || room.status !== "waiting") {
      return socket.emit("error", "참가 불가");
    }
    room.players.set(socket.id, { name: player.name, elo: player.elo, ready: false });
    player.roomId = roomId;
    player.status = "in-room";
    socket.join(roomId);
    io.to(roomId).emit("room-update", serializeRoom(room));
    broadcastLobby();
  });

  // 레디 토글
  socket.on("toggle-ready", () => {
    const player = players.get(socket.id);
    if (!player || !player.roomId) return;
    const room = rooms.get(player.roomId);
    if (!room) return;
    const rp = room.players.get(socket.id);
    rp.ready = !rp.ready;

    // 전원 레디 확인
    const allReady = [...room.players.values()].every((p) => p.ready);
    const enoughPlayers = room.players.size >= 2;

    if (allReady && enoughPlayers && !room.countdown) {
      // 카운트다운 시작
      room.countdown = 5;
      room.status = "starting";
      const interval = setInterval(() => {
        io.to(room.id).emit("countdown", room.countdown);
        room.countdown--;
        if (room.countdown < 0) {
          clearInterval(interval);
          room.status = "playing";
          io.to(room.id).emit("game-start", { mode: room.mode });
        }
      }, 1000);
    } else if (!allReady && room.countdown) {
      room.countdown = null;
      room.status = "waiting";
    }

    io.to(player.roomId).emit("room-update", serializeRoom(room));
  });

  // 방 나가기
  socket.on("leave-room", () => leaveRoom(socket));

  // 매칭 대기열 참가
  socket.on("join-queue", () => {
    const player = players.get(socket.id);
    if (!player || player.status !== "lobby") return;
    player.status = "queuing";
    matchQueue.push({ socketId: socket.id, elo: player.elo, joinedAt: Date.now() });
    socket.emit("queue-joined");
    broadcastLobby();
    tryMatch();
  });

  // 매칭 취소
  socket.on("leave-queue", () => {
    const player = players.get(socket.id);
    if (!player) return;
    const idx = matchQueue.findIndex((q) => q.socketId === socket.id);
    if (idx >= 0) matchQueue.splice(idx, 1);
    player.status = "lobby";
    socket.emit("queue-left");
    broadcastLobby();
  });

  socket.on("disconnect", () => {
    leaveRoom(socket);
    const idx = matchQueue.findIndex((q) => q.socketId === socket.id);
    if (idx >= 0) matchQueue.splice(idx, 1);
    players.delete(socket.id);
    broadcastLobby();
  });
});

// ELO 기반 매칭
function tryMatch() {
  if (matchQueue.length < 2) return;
  // ELO 차이가 200 이하인 두 명 매칭
  matchQueue.sort((a, b) => a.elo - b.elo);
  for (let i = 0; i < matchQueue.length - 1; i++) {
    const a = matchQueue[i];
    const b = matchQueue[i + 1];
    const eloDiff = Math.abs(a.elo - b.elo);
    const waitTime = Date.now() - Math.min(a.joinedAt, b.joinedAt);
    // 시간이 지날수록 ELO 허용 범위 확대
    const threshold = 200 + Math.floor(waitTime / 5000) * 50;

    if (eloDiff <= threshold) {
      matchQueue.splice(i, 2);
      createMatchRoom(a, b);
      return;
    }
  }
}

function createMatchRoom(a, b) {
  const pA = players.get(a.socketId);
  const pB = players.get(b.socketId);
  if (!pA || !pB) return;

  const roomId = `match-${++roomCounter}`;
  const room = {
    id: roomId, name: `매칭: ${pA.name} vs ${pB.name}`, host: a.socketId,
    maxPlayers: 2, mode: "1v1",
    players: new Map([
      [a.socketId, { name: pA.name, elo: pA.elo, ready: false }],
      [b.socketId, { name: pB.name, elo: pB.elo, ready: false }]
    ]),
    status: "waiting", countdown: null
  };
  rooms.set(roomId, room);

  [a.socketId, b.socketId].forEach((sid) => {
    const p = players.get(sid);
    p.roomId = roomId;
    p.status = "in-room";
    const s = io.sockets.sockets.get(sid);
    if (s) {
      s.join(roomId);
      s.emit("matched", serializeRoom(room));
    }
  });
  broadcastLobby();
}

function leaveRoom(socket) {
  const player = players.get(socket.id);
  if (!player || !player.roomId) return;
  const room = rooms.get(player.roomId);
  if (!room) return;
  room.players.delete(socket.id);
  socket.leave(room.id);
  player.roomId = null;
  player.status = "lobby";

  if (room.players.size === 0) {
    rooms.delete(room.id);
  } else {
    if (room.host === socket.id) room.host = [...room.players.keys()][0];
    io.to(room.id).emit("room-update", serializeRoom(room));
  }
  socket.emit("left-room");
  broadcastLobby();
}

function serializeRoom(room) {
  return {
    ...room,
    players: [...room.players.entries()].map(([id, p]) => ({ id, ...p, isHost: id === room.host }))
  };
}

function broadcastLobby() {
  const roomList = [...rooms.values()].map(serializeRoom);
  const playerList = [...players.values()].map((p) => ({ name: p.name, elo: p.elo, status: p.status }));
  const queueCount = matchQueue.length;
  io.emit("lobby-update", { rooms: roomList, players: playerList, queueCount });
}

// 주기적 매칭 시도
setInterval(tryMatch, 3000);

server.listen(3000, () => console.log("서버: http://localhost:3000"));
```

## client/index.html

```html
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>게임 로비</title>
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <div id="app">
    <div id="login"><h1>🎮 게임 로비</h1>
      <input id="name-input" placeholder="닉네임" />
      <button id="login-btn">입장</button>
    </div>
    <div id="lobby" class="hidden">
      <header><h2>🎮 게임 로비</h2><span id="my-info"></span></header>
      <div id="lobby-content">
        <div id="room-list-section">
          <div class="section-header"><h3>방 목록</h3>
            <button id="create-room-btn">+ 방 만들기</button>
            <button id="queue-btn">빠른 매칭</button>
          </div>
          <div id="room-list"></div>
        </div>
        <div id="online-section">
          <h3>접속 중 (<span id="player-count">0</span>)</h3>
          <ul id="player-list"></ul>
          <div id="queue-info" class="hidden">매칭 대기 중... <button id="cancel-queue">취소</button></div>
        </div>
      </div>
    </div>
    <div id="room" class="hidden">
      <header><h2 id="room-title">방</h2><button id="leave-btn">나가기</button></header>
      <div id="room-players"></div>
      <div id="room-actions">
        <button id="ready-btn">준비</button>
      </div>
      <div id="countdown-display" class="hidden"></div>
    </div>
    <div id="create-modal" class="hidden">
      <div class="modal-content">
        <h3>방 만들기</h3>
        <input id="room-name-input" placeholder="방 이름" />
        <select id="mode-select">
          <option value="1v1">1v1</option>
          <option value="2v2">2v2</option>
          <option value="FFA-4">FFA 4인</option>
        </select>
        <div class="modal-btns">
          <button id="confirm-create">생성</button>
          <button id="cancel-create">취소</button>
        </div>
      </div>
    </div>
  </div>
  <script src="/socket.io/socket.io.js"></script>
  <script src="app.js"></script>
</body>
</html>
```

## client/style.css

```css
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: "Apple SD Gothic Neo", sans-serif; background: #0c0a1a; color: #e2e8f0; height: 100vh; }
#app { max-width: 800px; margin: 0 auto; height: 100vh; display: flex; flex-direction: column; }
#login { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; flex: 1; }
#login h1 { font-size: 2rem; }
#login input { padding: 10px 16px; border-radius: 8px; border: 1px solid #2d2b55; background: #1a1830; color: #fff; width: 220px; }
#login button { padding: 10px 28px; border-radius: 8px; border: none; background: #7c3aed; color: #fff; cursor: pointer; }
.hidden { display: none !important; }
header { padding: 12px 16px; background: #1a1830; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #2d2b55; }
#lobby-content { flex: 1; display: grid; grid-template-columns: 1fr 220px; overflow: hidden; }
#room-list-section { padding: 12px; overflow-y: auto; }
.section-header { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.section-header h3 { flex: 1; }
.section-header button { padding: 6px 12px; border-radius: 6px; border: none; cursor: pointer; font-size: 0.85rem; }
#create-room-btn { background: #7c3aed; color: #fff; }
#queue-btn { background: #059669; color: #fff; }
.room-card { background: #1a1830; border: 1px solid #2d2b55; border-radius: 10px; padding: 12px; margin-bottom: 8px; cursor: pointer; transition: border-color 0.2s; }
.room-card:hover { border-color: #7c3aed; }
.room-card .room-header { display: flex; justify-content: space-between; margin-bottom: 6px; }
.room-card .room-name { font-weight: 600; }
.room-card .room-mode { font-size: 0.8rem; padding: 2px 8px; border-radius: 4px; background: #2d2b55; }
.room-card .room-players-count { font-size: 0.85rem; color: #94a3b8; }
.room-status { font-size: 0.75rem; padding: 2px 6px; border-radius: 4px; }
.room-status.waiting { background: #166534; color: #4ade80; }
.room-status.starting { background: #92400e; color: #fbbf24; }
#online-section { padding: 12px; border-left: 1px solid #2d2b55; overflow-y: auto; }
#online-section h3 { margin-bottom: 8px; font-size: 0.9rem; color: #94a3b8; }
#player-list { list-style: none; }
#player-list li { font-size: 0.85rem; padding: 4px 0; display: flex; justify-content: space-between; }
.elo-badge { font-size: 0.75rem; color: #fbbf24; }
#queue-info { margin-top: 12px; padding: 10px; background: #064e3b; border-radius: 8px; text-align: center; font-size: 0.85rem; }
#cancel-queue { margin-top: 6px; padding: 4px 12px; border-radius: 6px; border: none; background: #dc2626; color: #fff; cursor: pointer; }
#room { flex: 1; display: flex; flex-direction: column; }
#room-players { flex: 1; padding: 20px; display: flex; flex-wrap: wrap; gap: 16px; justify-content: center; align-content: center; }
.player-card { width: 160px; padding: 20px; background: #1a1830; border: 2px solid #2d2b55; border-radius: 12px; text-align: center; }
.player-card.ready { border-color: #22c55e; }
.player-card.host { border-color: #fbbf24; }
.player-card .player-name { font-size: 1.1rem; font-weight: 600; margin-bottom: 4px; }
.player-card .player-elo { font-size: 0.8rem; color: #fbbf24; }
.player-card .player-status { font-size: 0.85rem; margin-top: 6px; }
#room-actions { padding: 16px; text-align: center; }
#ready-btn { padding: 12px 48px; border-radius: 10px; border: none; font-size: 1.1rem; font-weight: 600; cursor: pointer; background: #22c55e; color: #fff; }
#leave-btn { padding: 6px 14px; border-radius: 6px; border: none; background: #dc2626; color: #fff; cursor: pointer; }
#countdown-display { position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 6rem; font-weight: 700; color: #fbbf24; text-shadow: 0 0 40px #fbbf2480; z-index: 100; }
#create-modal { position: fixed; inset: 0; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center; z-index: 50; }
.modal-content { background: #1a1830; border: 1px solid #2d2b55; border-radius: 12px; padding: 24px; width: 300px; }
.modal-content h3 { margin-bottom: 12px; }
.modal-content input, .modal-content select { width: 100%; padding: 8px 12px; margin-bottom: 10px; border-radius: 6px; border: 1px solid #2d2b55; background: #0c0a1a; color: #fff; }
.modal-btns { display: flex; gap: 8px; }
.modal-btns button { flex: 1; padding: 8px; border-radius: 6px; border: none; cursor: pointer; font-weight: 600; }
#confirm-create { background: #7c3aed; color: #fff; }
#cancel-create { background: #334155; color: #fff; }
```

## client/app.js

```javascript
const socket = io();
const $ = (s) => document.querySelector(s);
let myName = "", myElo = 0, inQueue = false;

// 로그인
$("#login-btn").addEventListener("click", () => {
  myName = $("#name-input").value.trim();
  if (!myName) return;
  socket.emit("login", myName);
});

socket.on("logged-in", ({ name, elo }) => {
  myName = name; myElo = elo;
  $("#my-info").textContent = `${name} (ELO: ${elo})`;
  $("#login").classList.add("hidden");
  $("#lobby").classList.remove("hidden");
});

// 방 생성 모달
$("#create-room-btn").addEventListener("click", () => $("#create-modal").classList.remove("hidden"));
$("#cancel-create").addEventListener("click", () => $("#create-modal").classList.add("hidden"));
$("#confirm-create").addEventListener("click", () => {
  const name = $("#room-name-input").value.trim() || `${myName}의 방`;
  const mode = $("#mode-select").value;
  socket.emit("create-room", { name, mode });
  $("#create-modal").classList.add("hidden");
});

// 빠른 매칭
$("#queue-btn").addEventListener("click", () => {
  socket.emit("join-queue");
  inQueue = true;
});
$("#cancel-queue").addEventListener("click", () => {
  socket.emit("leave-queue");
  inQueue = false;
});

socket.on("queue-joined", () => {
  inQueue = true;
  $("#queue-info").classList.remove("hidden");
});
socket.on("queue-left", () => {
  inQueue = false;
  $("#queue-info").classList.add("hidden");
});

// 로비 업데이트
socket.on("lobby-update", ({ rooms, players, queueCount }) => {
  // 방 목록
  const rl = $("#room-list");
  if (rooms.length === 0) {
    rl.innerHTML = '<div style="color:#64748b;text-align:center;padding:20px">방이 없습니다. 새 방을 만들거나 빠른 매칭을 시작하세요.</div>';
  } else {
    rl.innerHTML = rooms.map((r) => `
      <div class="room-card" data-room="${r.id}">
        <div class="room-header">
          <span class="room-name">${r.name}</span>
          <span class="room-mode">${r.mode}</span>
        </div>
        <div class="room-players-count">${r.players.length}/${r.maxPlayers}명</div>
        <span class="room-status ${r.status}">${r.status === "waiting" ? "대기중" : "시작중"}</span>
      </div>
    `).join("");
    document.querySelectorAll(".room-card").forEach((card) => {
      card.addEventListener("click", () => socket.emit("join-room", card.dataset.room));
    });
  }
  // 플레이어 목록
  $("#player-count").textContent = players.length;
  $("#player-list").innerHTML = players.map((p) =>
    `<li>${p.name} <span class="elo-badge">${p.elo}</span></li>`
  ).join("");
});

// 방 입장/업데이트
function showRoom(room) {
  $("#lobby").classList.add("hidden");
  $("#room").classList.remove("hidden");
  $("#room-title").textContent = `${room.name} (${room.mode})`;
  renderRoomPlayers(room.players);
}

function renderRoomPlayers(players) {
  $("#room-players").innerHTML = players.map((p) => `
    <div class="player-card ${p.ready ? "ready" : ""} ${p.isHost ? "host" : ""}">
      <div class="player-name">${p.name}</div>
      <div class="player-elo">ELO ${p.elo}</div>
      <div class="player-status">${p.isHost ? "👑 방장" : ""} ${p.ready ? "✅ 준비됨" : "⏳ 대기"}</div>
    </div>
  `).join("");
}

socket.on("joined-room", showRoom);
socket.on("matched", showRoom);
socket.on("room-update", (room) => renderRoomPlayers(room.players));

// 레디
$("#ready-btn").addEventListener("click", () => socket.emit("toggle-ready"));

// 카운트다운
socket.on("countdown", (n) => {
  const el = $("#countdown-display");
  el.classList.remove("hidden");
  el.textContent = n;
});

socket.on("game-start", ({ mode }) => {
  $("#countdown-display").textContent = "START!";
  setTimeout(() => {
    $("#countdown-display").classList.add("hidden");
    alert(`게임 시작! 모드: ${mode}`);
  }, 1500);
});

// 방 나가기
$("#leave-btn").addEventListener("click", () => socket.emit("leave-room"));
socket.on("left-room", () => {
  $("#room").classList.add("hidden");
  $("#lobby").classList.remove("hidden");
});

socket.on("error", (msg) => alert(msg));
```

ELO 기반 매칭은 대기 시간이 길어질수록 허용 ELO 범위를 확대합니다. 전원 준비 시 5초 카운트다운 후 게임이 시작됩니다.'''),

    # ═══ 6. React Dropdown + Popover + Tooltip ═══
    m("React로 Dropdown + Popover + Tooltip 컴포넌트 만들어줘 전체 코드로",
'''Dropdown, Popover, Tooltip 컴포넌트를 Portal 렌더링과 키보드 내비게이션 포함해서 만들어 드릴게요.

## 폴더 구조

```
ui-overlays/
├── src/
│   ├── App.tsx
│   ├── main.tsx
│   ├── index.css
│   ├── components/
│   │   ├── Portal.tsx
│   │   ├── Dropdown.tsx
│   │   ├── Popover.tsx
│   │   └── Tooltip.tsx
├── index.html
├── package.json
```

## package.json

```json
{
  "name": "ui-overlays",
  "private": true,
  "scripts": { "dev": "vite", "build": "vite build" },
  "dependencies": { "react": "^18.2.0", "react-dom": "^18.2.0" },
  "devDependencies": { "@types/react": "^18.2.0", "typescript": "^5.3.0", "vite": "^5.0.0", "@vitejs/plugin-react": "^4.2.0" }
}
```

## index.html

```html
<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" /><title>UI Overlays</title></head>
<body><div id="root"></div><script type="module" src="/src/main.tsx"></script></body>
</html>
```

## src/main.tsx

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode><App /></React.StrictMode>
);
```

## src/components/Portal.tsx

```tsx
import { useEffect, useRef, ReactNode } from "react";
import { createPortal } from "react-dom";

interface PortalProps { children: ReactNode; }

export default function Portal({ children }: PortalProps) {
  const elRef = useRef<HTMLDivElement | null>(null);
  if (!elRef.current) {
    elRef.current = document.createElement("div");
    elRef.current.className = "portal-root";
  }

  useEffect(() => {
    const el = elRef.current!;
    document.body.appendChild(el);
    return () => { document.body.removeChild(el); };
  }, []);

  return createPortal(children, elRef.current);
}
```

## src/components/Dropdown.tsx

```tsx
import { useState, useRef, useEffect, useCallback, KeyboardEvent, ReactNode } from "react";
import Portal from "./Portal";

interface DropdownItem {
  label: string;
  value: string;
  icon?: string;
  disabled?: boolean;
}

interface DropdownProps {
  items: DropdownItem[];
  placeholder?: string;
  value?: string;
  onChange?: (value: string) => void;
}

export default function Dropdown({ items, placeholder = "선택하세요", value, onChange }: DropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [focusIdx, setFocusIdx] = useState(-1);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ top: 0, left: 0, width: 0 });

  const selected = items.find((i) => i.value === value);

  const openMenu = useCallback(() => {
    if (!triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    setPos({ top: rect.bottom + 4, left: rect.left, width: rect.width });
    setIsOpen(true);
    setFocusIdx(-1);
  }, []);

  const closeMenu = useCallback(() => {
    setIsOpen(false);
    setFocusIdx(-1);
  }, []);

  const selectItem = useCallback((item: DropdownItem) => {
    if (item.disabled) return;
    onChange?.(item.value);
    closeMenu();
    triggerRef.current?.focus();
  }, [onChange, closeMenu]);

  // 외부 클릭 감지
  useEffect(() => {
    if (!isOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node) &&
          triggerRef.current && !triggerRef.current.contains(e.target as Node)) {
        closeMenu();
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [isOpen, closeMenu]);

  // 키보드 내비게이션
  const handleKeyDown = (e: KeyboardEvent) => {
    const enabledItems = items.filter((i) => !i.disabled);
    switch (e.key) {
      case "Enter": case " ":
        e.preventDefault();
        if (!isOpen) { openMenu(); }
        else if (focusIdx >= 0) { selectItem(items[focusIdx]); }
        break;
      case "ArrowDown":
        e.preventDefault();
        if (!isOpen) { openMenu(); break; }
        setFocusIdx((prev) => {
          let next = prev + 1;
          while (next < items.length && items[next].disabled) next++;
          return next < items.length ? next : prev;
        });
        break;
      case "ArrowUp":
        e.preventDefault();
        setFocusIdx((prev) => {
          let next = prev - 1;
          while (next >= 0 && items[next].disabled) next--;
          return next >= 0 ? next : prev;
        });
        break;
      case "Escape":
        closeMenu();
        triggerRef.current?.focus();
        break;
    }
  };

  return (
    <div className="dropdown-wrapper" onKeyDown={handleKeyDown}>
      <button ref={triggerRef} className="dropdown-trigger" onClick={() => isOpen ? closeMenu() : openMenu()}
        aria-haspopup="listbox" aria-expanded={isOpen}>
        <span>{selected ? `${selected.icon || ""} ${selected.label}` : placeholder}</span>
        <span className={`dropdown-arrow ${isOpen ? "open" : ""}`}>&#9662;</span>
      </button>
      {isOpen && (
        <Portal>
          <div ref={menuRef} className="dropdown-menu" role="listbox"
            style={{ top: pos.top, left: pos.left, minWidth: pos.width }}>
            {items.map((item, idx) => (
              <div key={item.value} role="option" aria-selected={item.value === value}
                className={`dropdown-item ${item.disabled ? "disabled" : ""} ${idx === focusIdx ? "focused" : ""} ${item.value === value ? "selected" : ""}`}
                onClick={() => selectItem(item)}
                onMouseEnter={() => !item.disabled && setFocusIdx(idx)}>
                {item.icon && <span className="item-icon">{item.icon}</span>}
                {item.label}
              </div>
            ))}
          </div>
        </Portal>
      )}
    </div>
  );
}
```

## src/components/Popover.tsx

```tsx
import { useState, useRef, useEffect, useCallback, ReactNode } from "react";
import Portal from "./Portal";

interface PopoverProps {
  trigger: ReactNode;
  children: ReactNode;
  placement?: "top" | "bottom" | "left" | "right";
}

export default function Popover({ trigger, children, placement = "bottom" }: PopoverProps) {
  const [isOpen, setIsOpen] = useState(false);
  const triggerRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ top: 0, left: 0 });

  const calcPosition = useCallback(() => {
    if (!triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    const gap = 8;
    let top = 0, left = 0;
    switch (placement) {
      case "bottom": top = rect.bottom + gap; left = rect.left + rect.width / 2; break;
      case "top": top = rect.top - gap; left = rect.left + rect.width / 2; break;
      case "left": top = rect.top + rect.height / 2; left = rect.left - gap; break;
      case "right": top = rect.top + rect.height / 2; left = rect.right + gap; break;
    }
    setPos({ top, left });
  }, [placement]);

  const toggle = () => {
    if (!isOpen) calcPosition();
    setIsOpen(!isOpen);
  };

  // 외부 클릭 닫기
  useEffect(() => {
    if (!isOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (contentRef.current && !contentRef.current.contains(e.target as Node) &&
          triggerRef.current && !triggerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [isOpen]);

  const transformOrigin = {
    bottom: "top center", top: "bottom center",
    left: "center right", right: "center left"
  }[placement];

  const translate = {
    bottom: "translate(-50%, 0)", top: "translate(-50%, -100%)",
    left: "translate(-100%, -50%)", right: "translate(0, -50%)"
  }[placement];

  return (
    <>
      <div ref={triggerRef} className="popover-trigger" onClick={toggle}>{trigger}</div>
      {isOpen && (
        <Portal>
          <div ref={contentRef} className="popover-content"
            style={{ top: pos.top, left: pos.left, transform: translate, transformOrigin }}>
            <div className={`popover-arrow popover-arrow-${placement}`} />
            {children}
          </div>
        </Portal>
      )}
    </>
  );
}
```

## src/components/Tooltip.tsx

```tsx
import { useState, useRef, useCallback, ReactNode } from "react";
import Portal from "./Portal";

interface TooltipProps {
  content: string;
  children: ReactNode;
  placement?: "top" | "bottom" | "left" | "right";
  delay?: number;
}

export default function Tooltip({ content, children, placement = "top", delay = 200 }: TooltipProps) {
  const [visible, setVisible] = useState(false);
  const [pos, setPos] = useState({ top: 0, left: 0 });
  const triggerRef = useRef<HTMLDivElement>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout>>();

  const show = useCallback(() => {
    timerRef.current = setTimeout(() => {
      if (!triggerRef.current) return;
      const rect = triggerRef.current.getBoundingClientRect();
      const gap = 8;
      let top = 0, left = 0;
      switch (placement) {
        case "top": top = rect.top - gap; left = rect.left + rect.width / 2; break;
        case "bottom": top = rect.bottom + gap; left = rect.left + rect.width / 2; break;
        case "left": top = rect.top + rect.height / 2; left = rect.left - gap; break;
        case "right": top = rect.top + rect.height / 2; left = rect.right + gap; break;
      }
      setPos({ top, left });
      setVisible(true);
    }, delay);
  }, [placement, delay]);

  const hide = useCallback(() => {
    clearTimeout(timerRef.current);
    setVisible(false);
  }, []);

  const translate = {
    top: "translate(-50%, -100%)", bottom: "translate(-50%, 0)",
    left: "translate(-100%, -50%)", right: "translate(0, -50%)"
  }[placement];

  return (
    <>
      <div ref={triggerRef} className="tooltip-trigger"
        onMouseEnter={show} onMouseLeave={hide} onFocus={show} onBlur={hide}>
        {children}
      </div>
      {visible && (
        <Portal>
          <div className={`tooltip tooltip-${placement}`}
            style={{ top: pos.top, left: pos.left, transform: translate }} role="tooltip">
            {content}
          </div>
        </Portal>
      )}
    </>
  );
}
```

## src/App.tsx

```tsx
import { useState } from "react";
import Dropdown from "./components/Dropdown";
import Popover from "./components/Popover";
import Tooltip from "./components/Tooltip";

const FRUIT_ITEMS = [
  { label: "사과", value: "apple", icon: "🍎" },
  { label: "바나나", value: "banana", icon: "🍌" },
  { label: "포도", value: "grape", icon: "🍇" },
  { label: "수박 (품절)", value: "watermelon", icon: "🍉", disabled: true },
  { label: "딸기", value: "strawberry", icon: "🍓" },
  { label: "체리", value: "cherry", icon: "🍒" },
];

export default function App() {
  const [fruit, setFruit] = useState("");

  return (
    <div className="demo-page">
      <h1>UI Overlay 컴포넌트</h1>

      <section>
        <h2>Dropdown</h2>
        <p>키보드(화살표/Enter/Esc) + 마우스 모두 지원</p>
        <Dropdown items={FRUIT_ITEMS} value={fruit} onChange={setFruit} placeholder="과일 선택" />
        {fruit && <p style={{ marginTop: 8 }}>선택: {fruit}</p>}
      </section>

      <section>
        <h2>Popover</h2>
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
          {(["top", "bottom", "left", "right"] as const).map((p) => (
            <Popover key={p} placement={p} trigger={<button className="demo-btn">Popover ({p})</button>}>
              <div style={{ padding: 12, minWidth: 160 }}>
                <strong>알림</strong>
                <p style={{ marginTop: 6, fontSize: 14, color: "#94a3b8" }}>
                  이것은 {p} 방향 Popover입니다. 외부를 클릭하면 닫힙니다.
                </p>
              </div>
            </Popover>
          ))}
        </div>
      </section>

      <section>
        <h2>Tooltip</h2>
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
          {(["top", "bottom", "left", "right"] as const).map((p) => (
            <Tooltip key={p} content={`${p} 방향 툴팁`} placement={p}>
              <button className="demo-btn">Hover me ({p})</button>
            </Tooltip>
          ))}
        </div>
      </section>
    </div>
  );
}
```

## src/index.css

```css
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: "Apple SD Gothic Neo", sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; padding: 40px; }
.demo-page { max-width: 700px; margin: 0 auto; }
.demo-page h1 { font-size: 1.8rem; margin-bottom: 32px; }
.demo-page section { margin-bottom: 40px; }
.demo-page h2 { font-size: 1.2rem; margin-bottom: 8px; color: #94a3b8; }
.demo-page p { font-size: 0.9rem; color: #64748b; margin-bottom: 12px; }
.demo-btn { padding: 8px 16px; border-radius: 8px; border: 1px solid #334155; background: #1e293b; color: #e2e8f0; cursor: pointer; }
.demo-btn:hover { border-color: #60a5fa; }

/* Dropdown */
.dropdown-wrapper { display: inline-block; position: relative; }
.dropdown-trigger { padding: 8px 14px; border-radius: 8px; border: 1px solid #334155; background: #1e293b; color: #e2e8f0; cursor: pointer; min-width: 180px; display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.dropdown-arrow { transition: transform 0.2s; }
.dropdown-arrow.open { transform: rotate(180deg); }
.dropdown-menu { position: fixed; background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 4px; box-shadow: 0 8px 24px rgba(0,0,0,0.4); z-index: 9999; }
.dropdown-item { padding: 8px 12px; border-radius: 6px; cursor: pointer; display: flex; align-items: center; gap: 6px; font-size: 0.9rem; }
.dropdown-item:hover, .dropdown-item.focused { background: #334155; }
.dropdown-item.selected { color: #60a5fa; }
.dropdown-item.disabled { opacity: 0.4; cursor: not-allowed; }
.item-icon { font-size: 1.1rem; }

/* Popover */
.popover-trigger { display: inline-block; }
.popover-content { position: fixed; background: #1e293b; border: 1px solid #334155; border-radius: 10px; box-shadow: 0 8px 24px rgba(0,0,0,0.4); z-index: 9999; animation: popIn 0.15s ease-out; }
@keyframes popIn { from { opacity: 0; transform: translate(-50%, 4px); } to { opacity: 1; } }

/* Tooltip */
.tooltip-trigger { display: inline-block; }
.tooltip { position: fixed; background: #334155; color: #e2e8f0; padding: 6px 12px; border-radius: 6px; font-size: 0.8rem; white-space: nowrap; z-index: 9999; pointer-events: none; animation: fadeIn 0.15s; }
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
```

Portal을 통해 body에 직접 렌더링하므로 overflow: hidden 문제가 없고, Dropdown은 키보드 ArrowUp/Down/Enter/Esc를 모두 지원합니다.'''),

    # ═══ 7. React 이미지 갤러리 + 라이트박스 ═══
    m("React로 이미지 갤러리 + 라이트박스 컴포넌트 만들어줘 전체 코드로",
'''Masonry 그리드 갤러리와 라이트박스(확대/축소, 키보드, 슬라이드쇼)를 만들어 드릴게요.

## 폴더 구조

```
image-gallery/
├── src/
│   ├── App.tsx
│   ├── main.tsx
│   ├── index.css
│   ├── components/
│   │   ├── Gallery.tsx
│   │   └── Lightbox.tsx
├── index.html
├── package.json
```

## package.json

```json
{
  "name": "image-gallery",
  "private": true,
  "scripts": { "dev": "vite", "build": "vite build" },
  "dependencies": { "react": "^18.2.0", "react-dom": "^18.2.0" },
  "devDependencies": { "@types/react": "^18.2.0", "typescript": "^5.3.0", "vite": "^5.0.0", "@vitejs/plugin-react": "^4.2.0" }
}
```

## index.html

```html
<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" /><title>이미지 갤러리</title></head>
<body><div id="root"></div><script type="module" src="/src/main.tsx"></script></body>
</html>
```

## src/main.tsx

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode><App /></React.StrictMode>
);
```

## src/components/Gallery.tsx

```tsx
import { useState, useRef, useEffect } from "react";

interface GalleryImage {
  src: string;
  alt: string;
  width: number;
  height: number;
}

interface GalleryProps {
  images: GalleryImage[];
  columns?: number;
  gap?: number;
  onImageClick?: (index: number) => void;
}

export default function Gallery({ images, columns = 3, gap = 8, onImageClick }: GalleryProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [colWidth, setColWidth] = useState(0);

  useEffect(() => {
    const updateWidth = () => {
      if (containerRef.current) {
        const totalGap = gap * (columns - 1);
        setColWidth((containerRef.current.clientWidth - totalGap) / columns);
      }
    };
    updateWidth();
    window.addEventListener("resize", updateWidth);
    return () => window.removeEventListener("resize", updateWidth);
  }, [columns, gap]);

  // Masonry 레이아웃 계산
  const colHeights = Array(columns).fill(0);
  const positioned = images.map((img, idx) => {
    const shortestCol = colHeights.indexOf(Math.min(...colHeights));
    const aspectRatio = img.height / img.width;
    const itemHeight = colWidth * aspectRatio;
    const x = shortestCol * (colWidth + gap);
    const y = colHeights[shortestCol];
    colHeights[shortestCol] += itemHeight + gap;
    return { ...img, idx, x, y, w: colWidth, h: itemHeight };
  });

  const totalHeight = Math.max(...colHeights);

  return (
    <div ref={containerRef} className="gallery-container" style={{ position: "relative", height: totalHeight }}>
      {positioned.map((item) => (
        <div key={item.idx} className="gallery-item"
          style={{ position: "absolute", left: item.x, top: item.y, width: item.w, height: item.h }}
          onClick={() => onImageClick?.(item.idx)}>
          <img src={item.src} alt={item.alt} loading="lazy"
            style={{ width: "100%", height: "100%", objectFit: "cover", borderRadius: 8, cursor: "pointer" }} />
          <div className="gallery-overlay">
            <span>{item.alt}</span>
          </div>
        </div>
      ))}
    </div>
  );
}
```

## src/components/Lightbox.tsx

```tsx
import { useState, useEffect, useCallback, useRef } from "react";

interface LightboxImage { src: string; alt: string; }

interface LightboxProps {
  images: LightboxImage[];
  startIndex: number;
  onClose: () => void;
}

export default function Lightbox({ images, startIndex, onClose }: LightboxProps) {
  const [current, setCurrent] = useState(startIndex);
  const [zoom, setZoom] = useState(1);
  const [playing, setPlaying] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval>>();

  const goNext = useCallback(() => {
    setCurrent((prev) => (prev + 1) % images.length);
    setZoom(1);
  }, [images.length]);

  const goPrev = useCallback(() => {
    setCurrent((prev) => (prev - 1 + images.length) % images.length);
    setZoom(1);
  }, [images.length]);

  const zoomIn = () => setZoom((z) => Math.min(z + 0.5, 4));
  const zoomOut = () => setZoom((z) => Math.max(z - 0.5, 0.5));

  // 키보드 이벤트
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      switch (e.key) {
        case "ArrowRight": goNext(); break;
        case "ArrowLeft": goPrev(); break;
        case "Escape": onClose(); break;
        case "+": case "=": zoomIn(); break;
        case "-": zoomOut(); break;
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [goNext, goPrev, onClose]);

  // 슬라이드쇼
  useEffect(() => {
    if (playing) {
      timerRef.current = setInterval(goNext, 3000);
    } else {
      clearInterval(timerRef.current);
    }
    return () => clearInterval(timerRef.current);
  }, [playing, goNext]);

  const img = images[current];

  return (
    <div className="lightbox-backdrop" onClick={onClose}>
      <div className="lightbox-content" onClick={(e) => e.stopPropagation()}>
        {/* 상단 컨트롤 */}
        <div className="lightbox-toolbar">
          <span className="lightbox-counter">{current + 1} / {images.length}</span>
          <div className="lightbox-controls">
            <button onClick={zoomOut} title="축소 (-)">-</button>
            <span className="zoom-level">{Math.round(zoom * 100)}%</span>
            <button onClick={zoomIn} title="확대 (+)">+</button>
            <button onClick={() => setPlaying(!playing)} title="슬라이드쇼">
              {playing ? "⏸" : "▶"}
            </button>
            <button onClick={onClose} title="닫기 (Esc)">✕</button>
          </div>
        </div>

        {/* 이미지 */}
        <div className="lightbox-image-wrap">
          <button className="lightbox-nav lightbox-prev" onClick={goPrev}>&#10094;</button>
          <div className="lightbox-image-container" style={{ overflow: zoom > 1 ? "auto" : "hidden" }}>
            <img src={img.src} alt={img.alt}
              style={{ transform: `scale(${zoom})`, transformOrigin: "center center", transition: "transform 0.2s", maxWidth: "90vw", maxHeight: "80vh" }} />
          </div>
          <button className="lightbox-nav lightbox-next" onClick={goNext}>&#10095;</button>
        </div>

        {/* 캡션 */}
        <div className="lightbox-caption">{img.alt}</div>

        {/* 썸네일 스트립 */}
        <div className="lightbox-thumbs">
          {images.map((im, idx) => (
            <img key={idx} src={im.src} alt={im.alt}
              className={`lightbox-thumb ${idx === current ? "active" : ""}`}
              onClick={() => { setCurrent(idx); setZoom(1); }} />
          ))}
        </div>
      </div>
    </div>
  );
}
```

## src/App.tsx

```tsx
import { useState } from "react";
import Gallery from "./components/Gallery";
import Lightbox from "./components/Lightbox";

// 샘플 이미지 (picsum)
const IMAGES = Array.from({ length: 12 }, (_, i) => ({
  src: `https://picsum.photos/seed/${i + 1}/${300 + (i % 3) * 100}/${400 + (i % 4) * 80}`,
  alt: `사진 ${i + 1}`,
  width: 300 + (i % 3) * 100,
  height: 400 + (i % 4) * 80,
}));

export default function App() {
  const [lightboxIdx, setLightboxIdx] = useState<number | null>(null);

  return (
    <div className="app-container">
      <h1>이미지 갤러리</h1>
      <p>이미지를 클릭하면 라이트박스가 열립니다. 키보드: 좌우 화살표, +/- 확대축소, Esc 닫기</p>
      <Gallery images={IMAGES} columns={3} gap={10} onImageClick={setLightboxIdx} />
      {lightboxIdx !== null && (
        <Lightbox images={IMAGES} startIndex={lightboxIdx} onClose={() => setLightboxIdx(null)} />
      )}
    </div>
  );
}
```

## src/index.css

```css
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: "Apple SD Gothic Neo", sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; }
.app-container { max-width: 900px; margin: 0 auto; padding: 32px 16px; }
.app-container h1 { font-size: 1.8rem; margin-bottom: 8px; }
.app-container > p { font-size: 0.85rem; color: #64748b; margin-bottom: 20px; }

/* Gallery */
.gallery-item { overflow: hidden; }
.gallery-item:hover img { transform: scale(1.05); }
.gallery-item img { transition: transform 0.3s; }
.gallery-overlay { position: absolute; bottom: 0; left: 0; right: 0; padding: 8px 12px; background: linear-gradient(transparent, rgba(0,0,0,0.7)); border-radius: 0 0 8px 8px; font-size: 0.8rem; opacity: 0; transition: opacity 0.3s; }
.gallery-item:hover .gallery-overlay { opacity: 1; }

/* Lightbox */
.lightbox-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,0.92); z-index: 10000; display: flex; align-items: center; justify-content: center; }
.lightbox-content { width: 100%; height: 100%; display: flex; flex-direction: column; }
.lightbox-toolbar { display: flex; justify-content: space-between; align-items: center; padding: 12px 20px; }
.lightbox-counter { font-size: 0.9rem; color: #94a3b8; }
.lightbox-controls { display: flex; gap: 8px; align-items: center; }
.lightbox-controls button { padding: 6px 12px; border-radius: 6px; border: none; background: #334155; color: #e2e8f0; cursor: pointer; font-size: 1rem; }
.lightbox-controls button:hover { background: #475569; }
.zoom-level { font-size: 0.8rem; color: #94a3b8; min-width: 40px; text-align: center; }
.lightbox-image-wrap { flex: 1; display: flex; align-items: center; justify-content: center; position: relative; min-height: 0; }
.lightbox-image-container { display: flex; align-items: center; justify-content: center; }
.lightbox-nav { position: absolute; top: 50%; transform: translateY(-50%); padding: 16px 12px; background: rgba(0,0,0,0.5); border: none; color: #fff; font-size: 1.5rem; cursor: pointer; border-radius: 4px; z-index: 2; }
.lightbox-prev { left: 16px; }
.lightbox-next { right: 16px; }
.lightbox-nav:hover { background: rgba(255,255,255,0.15); }
.lightbox-caption { text-align: center; padding: 8px; font-size: 0.9rem; color: #94a3b8; }
.lightbox-thumbs { display: flex; gap: 6px; justify-content: center; padding: 10px; overflow-x: auto; }
.lightbox-thumb { width: 50px; height: 50px; object-fit: cover; border-radius: 4px; cursor: pointer; opacity: 0.5; transition: opacity 0.2s; border: 2px solid transparent; }
.lightbox-thumb.active { opacity: 1; border-color: #60a5fa; }
.lightbox-thumb:hover { opacity: 0.8; }
```

Masonry 그리드가 이미지 비율에 맞게 배치하고, 라이트박스에서 확대/축소, 키보드 내비게이션, 3초 간격 슬라이드쇼를 지원합니다.'''),

    # ═══ 8. React 무한 스크롤 + 가상 리스트 ═══
    m("React로 무한 스크롤 + 가상 리스트 컴포넌트 만들어줘 전체 코드로",
'''IntersectionObserver 기반 무한 스크롤과 가상 리스트(visible item만 렌더)를 만들어 드릴게요.

## 폴더 구조

```
virtual-scroll/
├── src/
│   ├── App.tsx
│   ├── main.tsx
│   ├── index.css
│   ├── components/
│   │   ├── InfiniteScroll.tsx
│   │   ├── VirtualList.tsx
│   │   ├── SkeletonLoader.tsx
│   │   └── ScrollToTop.tsx
├── index.html
├── package.json
```

## package.json

```json
{
  "name": "virtual-scroll",
  "private": true,
  "scripts": { "dev": "vite", "build": "vite build" },
  "dependencies": { "react": "^18.2.0", "react-dom": "^18.2.0" },
  "devDependencies": { "@types/react": "^18.2.0", "typescript": "^5.3.0", "vite": "^5.0.0", "@vitejs/plugin-react": "^4.2.0" }
}
```

## index.html

```html
<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" /><title>무한 스크롤</title></head>
<body><div id="root"></div><script type="module" src="/src/main.tsx"></script></body>
</html>
```

## src/main.tsx

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode><App /></React.StrictMode>
);
```

## src/components/VirtualList.tsx

```tsx
import { useState, useRef, useEffect, useCallback, ReactNode } from "react";

interface VirtualListProps<T> {
  items: T[];
  itemHeight: number;
  overscan?: number;
  renderItem: (item: T, index: number) => ReactNode;
  containerHeight: number;
}

export default function VirtualList<T>({ items, itemHeight, overscan = 5, renderItem, containerHeight }: VirtualListProps<T>) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);

  const totalHeight = items.length * itemHeight;
  const startIdx = Math.max(0, Math.floor(scrollTop / itemHeight) - overscan);
  const endIdx = Math.min(items.length, Math.ceil((scrollTop + containerHeight) / itemHeight) + overscan);
  const visibleItems = items.slice(startIdx, endIdx);
  const offsetY = startIdx * itemHeight;

  const handleScroll = useCallback(() => {
    if (containerRef.current) {
      setScrollTop(containerRef.current.scrollTop);
    }
  }, []);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    el.addEventListener("scroll", handleScroll, { passive: true });
    return () => el.removeEventListener("scroll", handleScroll);
  }, [handleScroll]);

  return (
    <div ref={containerRef} className="virtual-list-container" style={{ height: containerHeight, overflow: "auto" }}>
      <div style={{ height: totalHeight, position: "relative" }}>
        <div style={{ position: "absolute", top: offsetY, left: 0, right: 0 }}>
          {visibleItems.map((item, i) => (
            <div key={startIdx + i} style={{ height: itemHeight }}>
              {renderItem(item, startIdx + i)}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
```

## src/components/InfiniteScroll.tsx

```tsx
import { useRef, useEffect, useCallback, ReactNode } from "react";

interface InfiniteScrollProps {
  children: ReactNode;
  onLoadMore: () => void;
  hasMore: boolean;
  loading: boolean;
  loader?: ReactNode;
  threshold?: number;
}

export default function InfiniteScroll({ children, onLoadMore, hasMore, loading, loader, threshold = 0.8 }: InfiniteScrollProps) {
  const sentinelRef = useRef<HTMLDivElement>(null);
  const observerRef = useRef<IntersectionObserver | null>(null);

  const handleIntersect = useCallback((entries: IntersectionObserverEntry[]) => {
    if (entries[0].isIntersecting && hasMore && !loading) {
      onLoadMore();
    }
  }, [hasMore, loading, onLoadMore]);

  useEffect(() => {
    if (observerRef.current) observerRef.current.disconnect();

    observerRef.current = new IntersectionObserver(handleIntersect, {
      root: null,
      rootMargin: "200px",
      threshold: 0
    });

    if (sentinelRef.current) {
      observerRef.current.observe(sentinelRef.current);
    }

    return () => observerRef.current?.disconnect();
  }, [handleIntersect]);

  return (
    <div className="infinite-scroll-container">
      {children}
      {loading && (loader || <div className="infinite-loader">로딩 중...</div>)}
      {hasMore && <div ref={sentinelRef} className="scroll-sentinel" />}
      {!hasMore && <div className="end-message">모든 데이터를 불러왔습니다.</div>}
    </div>
  );
}
```

## src/components/SkeletonLoader.tsx

```tsx
interface SkeletonProps {
  count?: number;
  height?: number;
}

export default function SkeletonLoader({ count = 5, height = 80 }: SkeletonProps) {
  return (
    <div className="skeleton-group">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="skeleton-item" style={{ height }}>
          <div className="skeleton-avatar" />
          <div className="skeleton-text">
            <div className="skeleton-line" style={{ width: "60%" }} />
            <div className="skeleton-line" style={{ width: "80%" }} />
            <div className="skeleton-line" style={{ width: "40%" }} />
          </div>
        </div>
      ))}
    </div>
  );
}
```

## src/components/ScrollToTop.tsx

```tsx
import { useState, useEffect } from "react";

interface ScrollToTopProps {
  threshold?: number;
}

export default function ScrollToTop({ threshold = 400 }: ScrollToTopProps) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const handleScroll = () => setVisible(window.scrollY > threshold);
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, [threshold]);

  const scrollToTop = () => window.scrollTo({ top: 0, behavior: "smooth" });

  if (!visible) return null;

  return (
    <button className="scroll-to-top" onClick={scrollToTop} aria-label="맨 위로">
      &#9650;
    </button>
  );
}
```

## src/App.tsx

```tsx
import { useState, useCallback } from "react";
import InfiniteScroll from "./components/InfiniteScroll";
import VirtualList from "./components/VirtualList";
import SkeletonLoader from "./components/SkeletonLoader";
import ScrollToTop from "./components/ScrollToTop";

interface Post { id: number; title: string; body: string; author: string; date: string; }

// 가짜 데이터 생성
function generatePosts(start: number, count: number): Post[] {
  return Array.from({ length: count }, (_, i) => ({
    id: start + i,
    title: `게시글 #${start + i} - ${["React 팁", "TypeScript 가이드", "Next.js 튜토리얼", "성능 최적화", "디자인 패턴"][i % 5]}`,
    body: `이것은 ${start + i}번째 게시글의 본문입니다. 무한 스크롤로 로딩된 콘텐츠입니다.`,
    author: ["김개발", "이디자인", "박백엔드", "최풀스택", "정주니어"][i % 5],
    date: new Date(Date.now() - (start + i) * 3600000).toLocaleDateString("ko-KR")
  }));
}

// 10,000개 가상 리스트용 데이터
const VIRTUAL_DATA = Array.from({ length: 10000 }, (_, i) => ({
  id: i, label: `아이템 ${i + 1}`, value: Math.round(Math.random() * 1000)
}));

export default function App() {
  const [mode, setMode] = useState<"infinite" | "virtual">("infinite");
  const [posts, setPosts] = useState<Post[]>(generatePosts(1, 20));
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);

  const loadMore = useCallback(() => {
    setLoading(true);
    // 네트워크 지연 시뮬레이션
    setTimeout(() => {
      const newPosts = generatePosts(posts.length + 1, 20);
      setPosts((prev) => [...prev, ...newPosts]);
      if (posts.length + 20 >= 200) setHasMore(false); // 200개에서 멈춤
      setLoading(false);
    }, 1000);
  }, [posts.length]);

  return (
    <div className="app">
      <header className="app-header">
        <h1>무한 스크롤 + 가상 리스트</h1>
        <div className="mode-toggle">
          <button className={mode === "infinite" ? "active" : ""} onClick={() => setMode("infinite")}>무한 스크롤</button>
          <button className={mode === "virtual" ? "active" : ""} onClick={() => setMode("virtual")}>가상 리스트 (10,000개)</button>
        </div>
      </header>

      {mode === "infinite" ? (
        <InfiniteScroll onLoadMore={loadMore} hasMore={hasMore} loading={loading}
          loader={<SkeletonLoader count={3} height={100} />}>
          <div className="post-list">
            {posts.map((post) => (
              <article key={post.id} className="post-card">
                <div className="post-header">
                  <span className="post-author">{post.author}</span>
                  <span className="post-date">{post.date}</span>
                </div>
                <h3>{post.title}</h3>
                <p>{post.body}</p>
              </article>
            ))}
          </div>
        </InfiniteScroll>
      ) : (
        <div className="virtual-section">
          <p>10,000개 아이템 중 보이는 것만 렌더링합니다.</p>
          <VirtualList
            items={VIRTUAL_DATA}
            itemHeight={50}
            containerHeight={600}
            renderItem={(item, idx) => (
              <div className={`virtual-item ${idx % 2 === 0 ? "even" : "odd"}`}>
                <span className="v-id">#{item.id + 1}</span>
                <span className="v-label">{item.label}</span>
                <span className="v-value">{item.value}점</span>
              </div>
            )}
          />
        </div>
      )}

      <ScrollToTop threshold={300} />
    </div>
  );
}
```

## src/index.css

```css
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: "Apple SD Gothic Neo", sans-serif; background: #0f172a; color: #e2e8f0; }
.app { max-width: 700px; margin: 0 auto; padding: 20px; }
.app-header { margin-bottom: 20px; }
.app-header h1 { font-size: 1.6rem; margin-bottom: 12px; }
.mode-toggle { display: flex; gap: 8px; }
.mode-toggle button { padding: 8px 16px; border-radius: 8px; border: 1px solid #334155; background: #1e293b; color: #94a3b8; cursor: pointer; }
.mode-toggle button.active { background: #3b82f6; color: #fff; border-color: #3b82f6; }

/* 포스트 카드 */
.post-list { display: flex; flex-direction: column; gap: 12px; }
.post-card { background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 16px; }
.post-header { display: flex; justify-content: space-between; margin-bottom: 6px; }
.post-author { font-size: 0.85rem; color: #60a5fa; }
.post-date { font-size: 0.8rem; color: #64748b; }
.post-card h3 { font-size: 1rem; margin-bottom: 6px; }
.post-card p { font-size: 0.85rem; color: #94a3b8; }

/* 스켈레톤 */
.skeleton-group { display: flex; flex-direction: column; gap: 12px; padding: 12px 0; }
.skeleton-item { display: flex; gap: 12px; background: #1e293b; border-radius: 10px; padding: 16px; }
.skeleton-avatar { width: 48px; height: 48px; border-radius: 50%; background: #334155; animation: pulse 1.5s infinite; flex-shrink: 0; }
.skeleton-text { flex: 1; display: flex; flex-direction: column; gap: 8px; }
.skeleton-line { height: 12px; border-radius: 4px; background: #334155; animation: pulse 1.5s infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }

/* 무한 스크롤 */
.infinite-loader { text-align: center; padding: 20px; color: #64748b; }
.end-message { text-align: center; padding: 20px; color: #64748b; font-size: 0.9rem; }
.scroll-sentinel { height: 1px; }

/* 가상 리스트 */
.virtual-section p { font-size: 0.85rem; color: #64748b; margin-bottom: 12px; }
.virtual-list-container { border: 1px solid #334155; border-radius: 8px; }
.virtual-item { display: flex; align-items: center; gap: 12px; padding: 0 16px; height: 100%; }
.virtual-item.even { background: #1e293b; }
.virtual-item.odd { background: #1a2332; }
.v-id { font-size: 0.8rem; color: #64748b; min-width: 60px; }
.v-label { flex: 1; font-size: 0.9rem; }
.v-value { font-size: 0.85rem; color: #fbbf24; }

/* Scroll to top */
.scroll-to-top { position: fixed; bottom: 24px; right: 24px; width: 44px; height: 44px; border-radius: 50%; border: none; background: #3b82f6; color: #fff; font-size: 1.2rem; cursor: pointer; box-shadow: 0 4px 12px rgba(59,130,246,0.4); transition: transform 0.2s; z-index: 100; }
.scroll-to-top:hover { transform: scale(1.1); }
```

무한 스크롤은 IntersectionObserver로 감지하고, 가상 리스트는 10,000개 중 보이는 영역만 DOM에 렌더링하여 성능을 유지합니다.'''),

    # ═══ 9. React SVG 차트 (Line/Bar/Pie) ═══
    m("React로 SVG 차트 컴포넌트(Line/Bar/Pie) 만들어줘 전체 코드로",
'''SVG 기반 Line, Bar, Pie(Donut) 차트를 만들어 드릴게요. 반응형 컨테이너와 툴팁, 애니메이션을 지원합니다.

## 폴더 구조

```
svg-charts/
├── src/
│   ├── App.tsx
│   ├── main.tsx
│   ├── index.css
│   ├── components/
│   │   ├── ChartContainer.tsx
│   │   ├── LineChart.tsx
│   │   ├── BarChart.tsx
│   │   └── PieChart.tsx
├── index.html
├── package.json
```

## package.json

```json
{
  "name": "svg-charts",
  "private": true,
  "scripts": { "dev": "vite", "build": "vite build" },
  "dependencies": { "react": "^18.2.0", "react-dom": "^18.2.0" },
  "devDependencies": { "@types/react": "^18.2.0", "typescript": "^5.3.0", "vite": "^5.0.0", "@vitejs/plugin-react": "^4.2.0" }
}
```

## index.html

```html
<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" /><title>SVG 차트</title></head>
<body><div id="root"></div><script type="module" src="/src/main.tsx"></script></body>
</html>
```

## src/main.tsx

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode><App /></React.StrictMode>
);
```

## src/components/ChartContainer.tsx

```tsx
import { useRef, useState, useEffect, ReactNode } from "react";

interface ChartContainerProps {
  children: (width: number, height: number) => ReactNode;
  aspectRatio?: number;
}

export default function ChartContainer({ children, aspectRatio = 0.5 }: ChartContainerProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const { width } = entries[0].contentRect;
      setSize({ width, height: width * aspectRatio });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [aspectRatio]);

  return (
    <div ref={ref} className="chart-container">
      {size.width > 0 && children(size.width, size.height)}
    </div>
  );
}
```

## src/components/LineChart.tsx

```tsx
import { useState, useMemo } from "react";

interface DataPoint { label: string; value: number; }
interface LineChartProps { data: DataPoint[]; color?: string; title?: string; }

export default function LineChart({ data, color = "#3b82f6", title }: LineChartProps) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const padding = { top: 30, right: 20, bottom: 40, left: 50 };

  return (
    <ChartContainer aspectRatio={0.5}>
      {(width, height) => {
        const chartW = width - padding.left - padding.right;
        const chartH = height - padding.top - padding.bottom;
        const maxVal = Math.max(...data.map((d) => d.value));
        const minVal = Math.min(...data.map((d) => d.value));
        const range = maxVal - minVal || 1;

        const points = data.map((d, i) => ({
          x: padding.left + (i / (data.length - 1)) * chartW,
          y: padding.top + chartH - ((d.value - minVal) / range) * chartH,
          ...d
        }));

        const pathD = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");
        const areaD = `${pathD} L ${points[points.length - 1].x} ${padding.top + chartH} L ${points[0].x} ${padding.top + chartH} Z`;

        // Y축 눈금
        const yTicks = 5;
        const yTickVals = Array.from({ length: yTicks + 1 }, (_, i) => minVal + (range / yTicks) * i);

        return (
          <svg width={width} height={height} className="line-chart">
            {title && <text x={width / 2} y={16} textAnchor="middle" className="chart-title">{title}</text>}
            {/* 격자 */}
            {yTickVals.map((v, i) => {
              const y = padding.top + chartH - ((v - minVal) / range) * chartH;
              return (
                <g key={i}>
                  <line x1={padding.left} y1={y} x2={width - padding.right} y2={y} stroke="#334155" strokeDasharray="4" />
                  <text x={padding.left - 8} y={y + 4} textAnchor="end" className="axis-label">{Math.round(v)}</text>
                </g>
              );
            })}
            {/* X축 라벨 */}
            {points.map((p, i) => (
              i % Math.ceil(data.length / 8) === 0 && (
                <text key={i} x={p.x} y={height - 8} textAnchor="middle" className="axis-label">{p.label}</text>
              )
            ))}
            {/* 영역 */}
            <path d={areaD} fill={`${color}20`}>
              <animate attributeName="opacity" from="0" to="1" dur="0.8s" fill="freeze" />
            </path>
            {/* 선 */}
            <path d={pathD} fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <animate attributeName="stroke-dashoffset" from="2000" to="0" dur="1.2s" fill="freeze" />
              <animate attributeName="stroke-dasharray" from="2000" to="2000" dur="0.01s" fill="freeze" />
            </path>
            {/* 점 + 툴팁 */}
            {points.map((p, i) => (
              <g key={i} onMouseEnter={() => setHoverIdx(i)} onMouseLeave={() => setHoverIdx(null)}>
                <circle cx={p.x} cy={p.y} r={hoverIdx === i ? 6 : 3.5} fill={color} stroke="#0f172a" strokeWidth="2"
                  style={{ transition: "r 0.15s" }} />
                {hoverIdx === i && (
                  <g>
                    <rect x={p.x - 40} y={p.y - 36} width={80} height={28} rx={6} fill="#1e293b" stroke="#334155" />
                    <text x={p.x} y={p.y - 18} textAnchor="middle" className="tooltip-text">{p.label}: {p.value}</text>
                  </g>
                )}
              </g>
            ))}
          </svg>
        );
      }}
    </ChartContainer>
  );
}

// 인라인 ChartContainer (독립 사용 가능)
function ChartContainer({ children, aspectRatio = 0.5 }: { children: (w: number, h: number) => React.ReactNode; aspectRatio?: number }) {
  const ref = React.useRef<HTMLDivElement>(null);
  const [size, setSize] = React.useState({ width: 0, height: 0 });
  React.useEffect(() => {
    const el = ref.current; if (!el) return;
    const obs = new ResizeObserver((e) => { const { width } = e[0].contentRect; setSize({ width, height: width * aspectRatio }); });
    obs.observe(el); return () => obs.disconnect();
  }, [aspectRatio]);
  return <div ref={ref} className="chart-container">{size.width > 0 && children(size.width, size.height)}</div>;
}
import React from "react";
```

## src/components/BarChart.tsx

```tsx
import React, { useState } from "react";

interface BarData { label: string; value: number; color?: string; }
interface BarChartProps { data: BarData[]; title?: string; }

const DEFAULT_COLORS = ["#3b82f6","#ef4444","#22c55e","#f59e0b","#8b5cf6","#ec4899","#14b8a6","#f97316"];

export default function BarChart({ data, title }: BarChartProps) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const ref = React.useRef<HTMLDivElement>(null);
  const [size, setSize] = React.useState({ width: 0, height: 0 });

  React.useEffect(() => {
    const el = ref.current; if (!el) return;
    const obs = new ResizeObserver((e) => { const { width } = e[0].contentRect; setSize({ width, height: width * 0.5 }); });
    obs.observe(el); return () => obs.disconnect();
  }, []);

  const padding = { top: 30, right: 20, bottom: 50, left: 50 };
  const { width, height } = size;
  const chartW = width - padding.left - padding.right;
  const chartH = height - padding.top - padding.bottom;
  const maxVal = Math.max(...data.map((d) => d.value));
  const barWidth = Math.min(60, (chartW / data.length) * 0.6);
  const gap = (chartW - barWidth * data.length) / (data.length + 1);

  const yTicks = 5;
  const yTickVals = Array.from({ length: yTicks + 1 }, (_, i) => Math.round((maxVal / yTicks) * i));

  return (
    <div ref={ref} className="chart-container">
      {width > 0 && (
        <svg width={width} height={height}>
          {title && <text x={width / 2} y={16} textAnchor="middle" className="chart-title">{title}</text>}
          {/* Y축 */}
          {yTickVals.map((v, i) => {
            const y = padding.top + chartH - (v / maxVal) * chartH;
            return (
              <g key={i}>
                <line x1={padding.left} y1={y} x2={width - padding.right} y2={y} stroke="#334155" strokeDasharray="4" />
                <text x={padding.left - 8} y={y + 4} textAnchor="end" className="axis-label">{v}</text>
              </g>
            );
          })}
          {/* 바 */}
          {data.map((d, i) => {
            const barH = (d.value / maxVal) * chartH;
            const x = padding.left + gap + i * (barWidth + gap);
            const y = padding.top + chartH - barH;
            const barColor = d.color || DEFAULT_COLORS[i % DEFAULT_COLORS.length];
            const isHovered = hoverIdx === i;
            return (
              <g key={i} onMouseEnter={() => setHoverIdx(i)} onMouseLeave={() => setHoverIdx(null)}>
                <rect x={x} y={y} width={barWidth} height={barH} rx={4}
                  fill={barColor} opacity={isHovered ? 1 : 0.85}
                  style={{ transition: "opacity 0.2s" }}>
                  <animate attributeName="height" from="0" to={barH} dur="0.6s" fill="freeze" />
                  <animate attributeName="y" from={padding.top + chartH} to={y} dur="0.6s" fill="freeze" />
                </rect>
                {/* X축 라벨 */}
                <text x={x + barWidth / 2} y={height - 12} textAnchor="middle" className="axis-label">{d.label}</text>
                {/* 호버 툴팁 */}
                {isHovered && (
                  <g>
                    <rect x={x + barWidth / 2 - 35} y={y - 32} width={70} height={26} rx={6} fill="#1e293b" stroke="#334155" />
                    <text x={x + barWidth / 2} y={y - 15} textAnchor="middle" className="tooltip-text">{d.value}</text>
                  </g>
                )}
              </g>
            );
          })}
        </svg>
      )}
    </div>
  );
}
```

## src/components/PieChart.tsx

```tsx
import React, { useState } from "react";

interface PieData { label: string; value: number; color?: string; }
interface PieChartProps { data: PieData[]; title?: string; donut?: boolean; }

const COLORS = ["#3b82f6","#ef4444","#22c55e","#f59e0b","#8b5cf6","#ec4899","#14b8a6","#f97316"];

function polarToCartesian(cx: number, cy: number, r: number, angle: number) {
  const rad = ((angle - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function arcPath(cx: number, cy: number, r: number, startAngle: number, endAngle: number) {
  const start = polarToCartesian(cx, cy, r, endAngle);
  const end = polarToCartesian(cx, cy, r, startAngle);
  const large = endAngle - startAngle > 180 ? 1 : 0;
  return `M ${start.x} ${start.y} A ${r} ${r} 0 ${large} 0 ${end.x} ${end.y}`;
}

export default function PieChart({ data, title, donut = false }: PieChartProps) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const ref = React.useRef<HTMLDivElement>(null);
  const [width, setWidth] = React.useState(0);

  React.useEffect(() => {
    const el = ref.current; if (!el) return;
    const obs = new ResizeObserver((e) => setWidth(e[0].contentRect.width));
    obs.observe(el); return () => obs.disconnect();
  }, []);

  const size = Math.min(width, 400);
  const cx = size / 2;
  const cy = size / 2 + (title ? 15 : 0);
  const outerR = size * 0.38;
  const innerR = donut ? outerR * 0.55 : 0;
  const total = data.reduce((s, d) => s + d.value, 0);

  let cumAngle = 0;
  const segments = data.map((d, i) => {
    const angle = (d.value / total) * 360;
    const startAngle = cumAngle;
    cumAngle += angle;
    const midAngle = startAngle + angle / 2;
    const mid = polarToCartesian(cx, cy, outerR * 0.7, midAngle);
    const labelPos = polarToCartesian(cx, cy, outerR + 20, midAngle);
    return { ...d, startAngle, endAngle: cumAngle, midAngle, mid, labelPos, color: d.color || COLORS[i % COLORS.length], pct: ((d.value / total) * 100).toFixed(1) };
  });

  return (
    <div ref={ref} className="chart-container">
      {width > 0 && (
        <svg width={size} height={size + (title ? 30 : 0)} style={{ margin: "0 auto", display: "block" }}>
          {title && <text x={size / 2} y={18} textAnchor="middle" className="chart-title">{title}</text>}
          {segments.map((seg, i) => {
            const isHovered = hoverIdx === i;
            const hoverOffset = isHovered ? 6 : 0;
            const midRad = ((seg.midAngle - 90) * Math.PI) / 180;
            const dx = Math.cos(midRad) * hoverOffset;
            const dy = Math.sin(midRad) * hoverOffset;

            // 외부 아크
            const outerArc = arcPath(cx + dx, cy + dy, outerR, seg.startAngle, seg.endAngle);
            const outerEnd = polarToCartesian(cx + dx, cy + dy, outerR, seg.startAngle);

            let pathD = outerArc;
            if (donut) {
              const innerArc = arcPath(cx + dx, cy + dy, innerR, seg.startAngle, seg.endAngle);
              const innerStart = polarToCartesian(cx + dx, cy + dy, innerR, seg.endAngle);
              pathD = `${outerArc} L ${outerEnd.x} ${outerEnd.y}`;
              // 풀 세그먼트 그리기
              const os = polarToCartesian(cx + dx, cy + dy, outerR, seg.endAngle);
              const oe = polarToCartesian(cx + dx, cy + dy, outerR, seg.startAngle);
              const ie = polarToCartesian(cx + dx, cy + dy, innerR, seg.startAngle);
              const is2 = polarToCartesian(cx + dx, cy + dy, innerR, seg.endAngle);
              const large = seg.endAngle - seg.startAngle > 180 ? 1 : 0;
              pathD = `M ${os.x} ${os.y} A ${outerR} ${outerR} 0 ${large} 0 ${oe.x} ${oe.y} L ${ie.x} ${ie.y} A ${innerR} ${innerR} 0 ${large} 1 ${is2.x} ${is2.y} Z`;
            } else {
              pathD = outerArc + ` L ${cx + dx} ${cy + dy} Z`;
            }

            return (
              <g key={i} onMouseEnter={() => setHoverIdx(i)} onMouseLeave={() => setHoverIdx(null)}
                style={{ transition: "transform 0.2s", cursor: "pointer" }}>
                <path d={pathD} fill={seg.color} stroke="#0f172a" strokeWidth="2"
                  opacity={hoverIdx !== null && hoverIdx !== i ? 0.5 : 1} />
                {/* 퍼센트 라벨 */}
                {parseFloat(seg.pct) > 5 && (
                  <text x={seg.mid.x + dx} y={seg.mid.y + dy} textAnchor="middle" className="pie-label">{seg.pct}%</text>
                )}
                {/* 호버 툴팁 */}
                {isHovered && (
                  <g>
                    <rect x={seg.labelPos.x - 50 + dx} y={seg.labelPos.y - 12 + dy} width={100} height={24} rx={6}
                      fill="#1e293b" stroke="#334155" />
                    <text x={seg.labelPos.x + dx} y={seg.labelPos.y + 4 + dy} textAnchor="middle" className="tooltip-text">
                      {seg.label}: {seg.value}
                    </text>
                  </g>
                )}
              </g>
            );
          })}
          {/* 도넛 중앙 텍스트 */}
          {donut && (
            <text x={cx} y={cy + 6} textAnchor="middle" className="donut-center">
              {hoverIdx !== null ? segments[hoverIdx].pct + "%" : "Total"}
            </text>
          )}
        </svg>
      )}
      {/* 범례 */}
      <div className="chart-legend">
        {segments.map((seg, i) => (
          <div key={i} className="legend-item" onMouseEnter={() => setHoverIdx(i)} onMouseLeave={() => setHoverIdx(null)}>
            <span className="legend-dot" style={{ background: seg.color }} />
            <span>{seg.label}</span>
            <span className="legend-value">{seg.value} ({seg.pct}%)</span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

## src/App.tsx

```tsx
import LineChart from "./components/LineChart";
import BarChart from "./components/BarChart";
import PieChart from "./components/PieChart";

const LINE_DATA = [
  { label: "1월", value: 120 }, { label: "2월", value: 180 }, { label: "3월", value: 150 },
  { label: "4월", value: 280 }, { label: "5월", value: 220 }, { label: "6월", value: 340 },
  { label: "7월", value: 310 }, { label: "8월", value: 420 }, { label: "9월", value: 380 },
  { label: "10월", value: 450 }, { label: "11월", value: 500 }, { label: "12월", value: 480 },
];

const BAR_DATA = [
  { label: "React", value: 420 }, { label: "Vue", value: 280 }, { label: "Angular", value: 180 },
  { label: "Svelte", value: 140 }, { label: "Next.js", value: 350 }, { label: "Nuxt", value: 120 },
];

const PIE_DATA = [
  { label: "JavaScript", value: 35 }, { label: "Python", value: 28 }, { label: "TypeScript", value: 18 },
  { label: "Java", value: 12 }, { label: "Go", value: 7 },
];

export default function App() {
  return (
    <div className="charts-page">
      <h1>SVG 차트 컴포넌트</h1>
      <section>
        <LineChart data={LINE_DATA} title="월별 사용자 수" color="#3b82f6" />
      </section>
      <section>
        <BarChart data={BAR_DATA} title="프레임워크 인기도" />
      </section>
      <div className="pie-row">
        <section>
          <PieChart data={PIE_DATA} title="언어 점유율 (Pie)" />
        </section>
        <section>
          <PieChart data={PIE_DATA} title="언어 점유율 (Donut)" donut />
        </section>
      </div>
    </div>
  );
}
```

## src/index.css

```css
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: "Apple SD Gothic Neo", sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; }
.charts-page { max-width: 800px; margin: 0 auto; padding: 32px 16px; }
.charts-page h1 { font-size: 1.8rem; margin-bottom: 24px; }
.charts-page section { margin-bottom: 32px; }
.chart-container { width: 100%; }
.chart-title { fill: #e2e8f0; font-size: 14px; font-weight: 600; }
.axis-label { fill: #64748b; font-size: 11px; }
.tooltip-text { fill: #e2e8f0; font-size: 12px; }
.pie-label { fill: #fff; font-size: 11px; font-weight: 600; }
.donut-center { fill: #e2e8f0; font-size: 16px; font-weight: 600; }
.pie-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.chart-legend { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; padding: 12px 0; }
.legend-item { display: flex; align-items: center; gap: 6px; font-size: 0.8rem; cursor: pointer; }
.legend-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.legend-value { color: #64748b; }
```

ResizeObserver로 반응형 크기 조절, SVG animate로 선/바 등장 애니메이션, 마우스 호버 툴팁을 지원합니다.'''),

    # ═══ 10. React Stepper + Wizard 폼 ═══
    m("React로 Stepper + Wizard 폼 컴포넌트 만들어줘 전체 코드로",
'''멀티 스텝 위자드 폼을 만들어 드릴게요. 번호 표시 스테퍼, 진행바, 단계별 유효성 검증, 최종 확인 단계를 포함합니다.

## 폴더 구조

```
stepper-wizard/
├── src/
│   ├── App.tsx
│   ├── main.tsx
│   ├── index.css
│   ├── components/
│   │   ├── Stepper.tsx
│   │   ├── WizardForm.tsx
│   │   └── steps/
│   │       ├── StepPersonal.tsx
│   │       ├── StepContact.tsx
│   │       ├── StepPreferences.tsx
│   │       └── StepReview.tsx
├── index.html
├── package.json
```

## package.json

```json
{
  "name": "stepper-wizard",
  "private": true,
  "scripts": { "dev": "vite", "build": "vite build" },
  "dependencies": { "react": "^18.2.0", "react-dom": "^18.2.0" },
  "devDependencies": { "@types/react": "^18.2.0", "typescript": "^5.3.0", "vite": "^5.0.0", "@vitejs/plugin-react": "^4.2.0" }
}
```

## index.html

```html
<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" /><title>Stepper Wizard</title></head>
<body><div id="root"></div><script type="module" src="/src/main.tsx"></script></body>
</html>
```

## src/main.tsx

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode><App /></React.StrictMode>
);
```

## src/components/Stepper.tsx

```tsx
interface StepInfo { label: string; description?: string; }

interface StepperProps {
  steps: StepInfo[];
  currentStep: number;
  completedSteps: Set<number>;
}

export default function Stepper({ steps, currentStep, completedSteps }: StepperProps) {
  const progress = ((currentStep) / (steps.length - 1)) * 100;

  return (
    <div className="stepper">
      {/* 프로그레스 바 */}
      <div className="stepper-progress-bg">
        <div className="stepper-progress-fill" style={{ width: `${progress}%` }} />
      </div>

      <div className="stepper-steps">
        {steps.map((step, idx) => {
          const isActive = idx === currentStep;
          const isCompleted = completedSteps.has(idx);
          const isPast = idx < currentStep;
          let status = "upcoming";
          if (isActive) status = "active";
          else if (isCompleted || isPast) status = "completed";

          return (
            <div key={idx} className={`stepper-step ${status}`}>
              <div className="step-circle">
                {status === "completed" ? (
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M3 8l3 3 7-7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                ) : (
                  <span>{idx + 1}</span>
                )}
              </div>
              <div className="step-info">
                <span className="step-label">{step.label}</span>
                {step.description && <span className="step-desc">{step.description}</span>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

## src/components/steps/StepPersonal.tsx

```tsx
interface StepPersonalProps {
  data: { name: string; age: string; gender: string };
  onChange: (field: string, value: string) => void;
  errors: Record<string, string>;
}

export default function StepPersonal({ data, onChange, errors }: StepPersonalProps) {
  return (
    <div className="step-content">
      <h2>개인 정보</h2>
      <p className="step-subtitle">기본 정보를 입력해 주세요.</p>

      <div className="form-group">
        <label>이름 *</label>
        <input type="text" value={data.name} onChange={(e) => onChange("name", e.target.value)}
          placeholder="홍길동" className={errors.name ? "error" : ""} />
        {errors.name && <span className="error-msg">{errors.name}</span>}
      </div>

      <div className="form-group">
        <label>나이 *</label>
        <input type="number" value={data.age} onChange={(e) => onChange("age", e.target.value)}
          placeholder="25" className={errors.age ? "error" : ""} />
        {errors.age && <span className="error-msg">{errors.age}</span>}
      </div>

      <div className="form-group">
        <label>성별</label>
        <div className="radio-group">
          {[["male", "남성"], ["female", "여성"], ["other", "기타"]].map(([val, label]) => (
            <label key={val} className="radio-label">
              <input type="radio" name="gender" value={val} checked={data.gender === val}
                onChange={(e) => onChange("gender", e.target.value)} />
              {label}
            </label>
          ))}
        </div>
      </div>
    </div>
  );
}
```

## src/components/steps/StepContact.tsx

```tsx
interface StepContactProps {
  data: { email: string; phone: string; address: string };
  onChange: (field: string, value: string) => void;
  errors: Record<string, string>;
}

export default function StepContact({ data, onChange, errors }: StepContactProps) {
  return (
    <div className="step-content">
      <h2>연락처</h2>
      <p className="step-subtitle">연락 가능한 정보를 입력해 주세요.</p>

      <div className="form-group">
        <label>이메일 *</label>
        <input type="email" value={data.email} onChange={(e) => onChange("email", e.target.value)}
          placeholder="user@example.com" className={errors.email ? "error" : ""} />
        {errors.email && <span className="error-msg">{errors.email}</span>}
      </div>

      <div className="form-group">
        <label>전화번호 *</label>
        <input type="tel" value={data.phone} onChange={(e) => onChange("phone", e.target.value)}
          placeholder="010-1234-5678" className={errors.phone ? "error" : ""} />
        {errors.phone && <span className="error-msg">{errors.phone}</span>}
      </div>

      <div className="form-group">
        <label>주소</label>
        <input type="text" value={data.address} onChange={(e) => onChange("address", e.target.value)}
          placeholder="서울시 강남구..." />
      </div>
    </div>
  );
}
```

## src/components/steps/StepPreferences.tsx

```tsx
interface StepPreferencesProps {
  data: { interests: string[]; newsletter: boolean; theme: string };
  onChange: (field: string, value: any) => void;
  errors: Record<string, string>;
}

const INTEREST_OPTIONS = ["프론트엔드", "백엔드", "모바일", "AI/ML", "DevOps", "디자인", "보안", "데이터"];

export default function StepPreferences({ data, onChange, errors }: StepPreferencesProps) {
  const toggleInterest = (item: string) => {
    const next = data.interests.includes(item)
      ? data.interests.filter((i) => i !== item)
      : [...data.interests, item];
    onChange("interests", next);
  };

  return (
    <div className="step-content">
      <h2>관심 분야</h2>
      <p className="step-subtitle">관심 분야를 선택해 주세요.</p>

      <div className="form-group">
        <label>관심 분야 * (최소 1개)</label>
        <div className="chip-group">
          {INTEREST_OPTIONS.map((item) => (
            <button key={item} type="button"
              className={`chip ${data.interests.includes(item) ? "active" : ""}`}
              onClick={() => toggleInterest(item)}>
              {item}
            </button>
          ))}
        </div>
        {errors.interests && <span className="error-msg">{errors.interests}</span>}
      </div>

      <div className="form-group">
        <label>테마</label>
        <select value={data.theme} onChange={(e) => onChange("theme", e.target.value)}>
          <option value="dark">다크</option>
          <option value="light">라이트</option>
          <option value="system">시스템 설정</option>
        </select>
      </div>

      <div className="form-group">
        <label className="checkbox-label">
          <input type="checkbox" checked={data.newsletter}
            onChange={(e) => onChange("newsletter", e.target.checked)} />
          뉴스레터 구독
        </label>
      </div>
    </div>
  );
}
```

## src/components/steps/StepReview.tsx

```tsx
interface StepReviewProps {
  formData: {
    name: string; age: string; gender: string;
    email: string; phone: string; address: string;
    interests: string[]; newsletter: boolean; theme: string;
  };
}

export default function StepReview({ formData }: StepReviewProps) {
  const genderMap: Record<string, string> = { male: "남성", female: "여성", other: "기타" };
  const themeMap: Record<string, string> = { dark: "다크", light: "라이트", system: "시스템" };

  return (
    <div className="step-content">
      <h2>최종 확인</h2>
      <p className="step-subtitle">입력한 정보를 확인해 주세요.</p>

      <div className="review-section">
        <h3>개인 정보</h3>
        <div className="review-grid">
          <div className="review-item"><span className="review-label">이름</span><span>{formData.name}</span></div>
          <div className="review-item"><span className="review-label">나이</span><span>{formData.age}세</span></div>
          <div className="review-item"><span className="review-label">성별</span><span>{genderMap[formData.gender] || "-"}</span></div>
        </div>
      </div>

      <div className="review-section">
        <h3>연락처</h3>
        <div className="review-grid">
          <div className="review-item"><span className="review-label">이메일</span><span>{formData.email}</span></div>
          <div className="review-item"><span className="review-label">전화번호</span><span>{formData.phone}</span></div>
          <div className="review-item"><span className="review-label">주소</span><span>{formData.address || "-"}</span></div>
        </div>
      </div>

      <div className="review-section">
        <h3>관심 분야</h3>
        <div className="review-chips">
          {formData.interests.map((i) => <span key={i} className="review-chip">{i}</span>)}
        </div>
        <div className="review-grid" style={{ marginTop: 8 }}>
          <div className="review-item"><span className="review-label">테마</span><span>{themeMap[formData.theme]}</span></div>
          <div className="review-item"><span className="review-label">뉴스레터</span><span>{formData.newsletter ? "구독" : "미구독"}</span></div>
        </div>
      </div>
    </div>
  );
}
```

## src/components/WizardForm.tsx

```tsx
import { useState, useCallback } from "react";
import Stepper from "./Stepper";
import StepPersonal from "./steps/StepPersonal";
import StepContact from "./steps/StepContact";
import StepPreferences from "./steps/StepPreferences";
import StepReview from "./steps/StepReview";

const STEPS = [
  { label: "개인 정보", description: "이름, 나이" },
  { label: "연락처", description: "이메일, 전화번호" },
  { label: "관심 분야", description: "선호 설정" },
  { label: "확인", description: "최종 검토" },
];

interface FormData {
  name: string; age: string; gender: string;
  email: string; phone: string; address: string;
  interests: string[]; newsletter: boolean; theme: string;
}

const INITIAL: FormData = {
  name: "", age: "", gender: "",
  email: "", phone: "", address: "",
  interests: [], newsletter: false, theme: "dark",
};

export default function WizardForm() {
  const [step, setStep] = useState(0);
  const [formData, setFormData] = useState<FormData>(INITIAL);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [completed, setCompleted] = useState<Set<number>>(new Set());
  const [submitted, setSubmitted] = useState(false);

  const updateField = useCallback((field: string, value: any) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
    setErrors((prev) => { const next = { ...prev }; delete next[field]; return next; });
  }, []);

  // 단계별 유효성 검증
  const validate = (stepIdx: number): boolean => {
    const errs: Record<string, string> = {};
    switch (stepIdx) {
      case 0:
        if (!formData.name.trim()) errs.name = "이름을 입력해 주세요.";
        if (!formData.age || Number(formData.age) < 1) errs.age = "올바른 나이를 입력해 주세요.";
        break;
      case 1:
        if (!formData.email.trim()) errs.email = "이메일을 입력해 주세요.";
        else if (!/^[^@]+@[^@]+\.[^@]+$/.test(formData.email)) errs.email = "올바른 이메일 형식을 입력해 주세요.";
        if (!formData.phone.trim()) errs.phone = "전화번호를 입력해 주세요.";
        break;
      case 2:
        if (formData.interests.length === 0) errs.interests = "최소 1개 이상 선택해 주세요.";
        break;
    }
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const goNext = () => {
    if (!validate(step)) return;
    setCompleted((prev) => new Set([...prev, step]));
    setStep((s) => Math.min(s + 1, STEPS.length - 1));
  };

  const goBack = () => setStep((s) => Math.max(s - 1, 0));

  const handleSubmit = () => {
    console.log("제출 데이터:", formData);
    setSubmitted(true);
  };

  if (submitted) {
    return (
      <div className="wizard-card">
        <div className="submit-success">
          <div className="success-icon">✓</div>
          <h2>제출 완료!</h2>
          <p>{formData.name}님, 등록이 완료되었습니다.</p>
          <button className="btn-primary" onClick={() => { setSubmitted(false); setStep(0); setFormData(INITIAL); setCompleted(new Set()); }}>
            처음으로
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="wizard-card">
      <Stepper steps={STEPS} currentStep={step} completedSteps={completed} />

      <div className="wizard-body">
        {step === 0 && <StepPersonal data={formData} onChange={updateField} errors={errors} />}
        {step === 1 && <StepContact data={formData} onChange={updateField} errors={errors} />}
        {step === 2 && <StepPreferences data={formData} onChange={updateField} errors={errors} />}
        {step === 3 && <StepReview formData={formData} />}
      </div>

      <div className="wizard-footer">
        {step > 0 && <button className="btn-secondary" onClick={goBack}>이전</button>}
        <div style={{ flex: 1 }} />
        {step < STEPS.length - 1 ? (
          <button className="btn-primary" onClick={goNext}>다음</button>
        ) : (
          <button className="btn-submit" onClick={handleSubmit}>제출하기</button>
        )}
      </div>
    </div>
  );
}
```

## src/App.tsx

```tsx
import WizardForm from "./components/WizardForm";

export default function App() {
  return (
    <div className="app-page">
      <h1>Stepper Wizard 폼</h1>
      <WizardForm />
    </div>
  );
}
```

## src/index.css

```css
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: "Apple SD Gothic Neo", sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; padding: 32px 16px; }
.app-page { max-width: 640px; margin: 0 auto; }
.app-page h1 { font-size: 1.6rem; margin-bottom: 20px; text-align: center; }

/* Wizard Card */
.wizard-card { background: #1e293b; border: 1px solid #334155; border-radius: 16px; overflow: hidden; }

/* Stepper */
.stepper { padding: 24px 24px 16px; }
.stepper-progress-bg { height: 4px; background: #334155; border-radius: 2px; margin-bottom: 20px; }
.stepper-progress-fill { height: 100%; background: linear-gradient(90deg, #3b82f6, #8b5cf6); border-radius: 2px; transition: width 0.4s ease; }
.stepper-steps { display: flex; justify-content: space-between; }
.stepper-step { display: flex; align-items: center; gap: 10px; }
.step-circle { width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  font-weight: 600; font-size: 0.85rem; flex-shrink: 0; transition: all 0.3s; }
.stepper-step.upcoming .step-circle { background: #334155; color: #64748b; }
.stepper-step.active .step-circle { background: #3b82f6; color: #fff; box-shadow: 0 0 0 4px rgba(59,130,246,0.3); }
.stepper-step.completed .step-circle { background: #22c55e; color: #fff; }
.step-info { display: flex; flex-direction: column; }
.step-label { font-size: 0.85rem; font-weight: 600; }
.step-desc { font-size: 0.7rem; color: #64748b; }
.stepper-step.upcoming .step-label { color: #64748b; }

/* Wizard Body */
.wizard-body { padding: 0 24px 16px; min-height: 300px; }
.step-content h2 { font-size: 1.2rem; margin-bottom: 4px; }
.step-subtitle { font-size: 0.85rem; color: #64748b; margin-bottom: 20px; }

/* 폼 요소 */
.form-group { margin-bottom: 16px; }
.form-group > label { display: block; font-size: 0.85rem; color: #94a3b8; margin-bottom: 6px; }
.form-group input[type="text"], .form-group input[type="email"], .form-group input[type="tel"],
.form-group input[type="number"], .form-group select {
  width: 100%; padding: 10px 14px; border-radius: 8px; border: 1px solid #334155;
  background: #0f172a; color: #e2e8f0; font-size: 0.9rem; outline: none; transition: border-color 0.2s;
}
.form-group input:focus, .form-group select:focus { border-color: #3b82f6; }
.form-group input.error { border-color: #ef4444; }
.error-msg { color: #ef4444; font-size: 0.8rem; margin-top: 4px; display: block; }
.radio-group { display: flex; gap: 16px; }
.radio-label { display: flex; align-items: center; gap: 6px; font-size: 0.9rem; cursor: pointer; }
.checkbox-label { display: flex; align-items: center; gap: 8px; cursor: pointer; font-size: 0.9rem; }

/* 칩 */
.chip-group { display: flex; flex-wrap: wrap; gap: 8px; }
.chip { padding: 6px 14px; border-radius: 20px; border: 1px solid #334155; background: #0f172a;
  color: #94a3b8; cursor: pointer; font-size: 0.85rem; transition: all 0.2s; }
.chip.active { background: #3b82f6; border-color: #3b82f6; color: #fff; }
.chip:hover { border-color: #3b82f6; }

/* Review */
.review-section { margin-bottom: 20px; }
.review-section h3 { font-size: 0.9rem; color: #64748b; margin-bottom: 8px; border-bottom: 1px solid #334155; padding-bottom: 6px; }
.review-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.review-item { display: flex; flex-direction: column; }
.review-label { font-size: 0.75rem; color: #64748b; }
.review-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.review-chip { padding: 4px 10px; border-radius: 12px; background: #334155; font-size: 0.8rem; }

/* Footer */
.wizard-footer { display: flex; padding: 16px 24px; border-top: 1px solid #334155; }
.btn-primary { padding: 10px 24px; border-radius: 8px; border: none; background: #3b82f6; color: #fff; cursor: pointer; font-weight: 600; font-size: 0.9rem; }
.btn-secondary { padding: 10px 24px; border-radius: 8px; border: 1px solid #334155; background: transparent; color: #94a3b8; cursor: pointer; font-size: 0.9rem; }
.btn-submit { padding: 10px 24px; border-radius: 8px; border: none; background: #22c55e; color: #fff; cursor: pointer; font-weight: 600; font-size: 0.9rem; }
.btn-primary:hover { background: #2563eb; }
.btn-submit:hover { background: #16a34a; }

/* 제출 완료 */
.submit-success { text-align: center; padding: 60px 24px; }
.success-icon { width: 64px; height: 64px; border-radius: 50%; background: #22c55e; color: #fff;
  font-size: 2rem; display: flex; align-items: center; justify-content: center; margin: 0 auto 16px; }
.submit-success h2 { margin-bottom: 8px; }
.submit-success p { color: #94a3b8; margin-bottom: 24px; }
```

번호 스테퍼와 프로그레스 바가 현재 단계를 시각적으로 표시하고, 각 단계에서 유효성 검증을 통과해야 다음으로 넘어갑니다. 마지막 단계에서 입력한 정보를 한눈에 확인한 뒤 제출합니다.'''),
]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/mega_extra_2.jsonl")
    args = parser.parse_args()
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    logger.info(f"추가 데이터 2: {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
