"""화랑 AI 실시간 채팅 추가 학습 데이터

실시간 통신(Socket.IO / WebSocket) 기반 프로젝트 학습 데이터.
각 항목은 폴더 구조 + 6~10개 파일의 완전한 코드 포함.

카테고리:
  - Socket.IO 1:1 DM 시스템 (1건)
  - WebSocket 실시간 투표 시스템 (1건)
  - Socket.IO 채팅방 관리자 기능 (1건)
  - WebSocket 주식 시세 대시보드 (1건)
  - Socket.IO 멀티플레이어 끝말잇기 (1건)
  - WebSocket IoT 센서 모니터링 (1건)
"""

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
    # ═══ 1. Socket.IO 1:1 다이렉트 메시지 시스템 ═══
    m("Socket.IO로 1:1 다이렉트 메시지 시스템 만들어줘 전체 코드로",
'''1:1 다이렉트 메시지 시스템을 만들어 드릴게요. DM방 생성, 온라인 상태 추적, 읽음 확인(배달/읽음 타임스탬프), 대화 목록을 구현합니다.

## 폴더 구조

```
dm-system/
├── server/
│   ├── index.js
│   ├── socket/
│   │   └── dmHandler.js
│   ├── models/
│   │   ├── User.js
│   │   └── Message.js
│   └── routes/
│       └── conversations.js
├── client/
│   ├── index.html
│   ├── app.js
│   └── style.css
└── package.json
```

## package.json

```json
{
  "name": "dm-system",
  "version": "1.0.0",
  "scripts": {
    "start": "node server/index.js"
  },
  "dependencies": {
    "express": "^4.18.2",
    "socket.io": "^4.7.4",
    "mongoose": "^8.1.0",
    "cors": "^2.8.5"
  }
}
```

## server/index.js

```javascript
const express = require("express");
const http = require("http");
const { Server } = require("socket.io");
const mongoose = require("mongoose");
const cors = require("cors");
const conversationRoutes = require("./routes/conversations");
const { setupDmHandler } = require("./socket/dmHandler");

const app = express();
const server = http.createServer(app);
const io = new Server(server, { cors: { origin: "*" } });

app.use(cors());
app.use(express.json());
app.use(express.static("client"));
app.use("/api/conversations", conversationRoutes);

// 온라인 유저 관리 맵: userId → socketId
const onlineUsers = new Map();

mongoose.connect("mongodb://localhost:27017/dm-system").then(() => {
  console.log("MongoDB 연결 완료");
});

io.on("connection", (socket) => {
  console.log(`소켓 연결: ${socket.id}`);

  socket.on("register", (userId) => {
    onlineUsers.set(userId, socket.id);
    socket.userId = userId;
    io.emit("online-users", Array.from(onlineUsers.keys()));
    console.log(`${userId} 온라인 등록`);
  });

  setupDmHandler(io, socket, onlineUsers);

  socket.on("disconnect", () => {
    if (socket.userId) {
      onlineUsers.delete(socket.userId);
      io.emit("online-users", Array.from(onlineUsers.keys()));
    }
  });
});

server.listen(3000, () => console.log("서버 실행: http://localhost:3000"));
```

## server/models/User.js

```javascript
const mongoose = require("mongoose");

const userSchema = new mongoose.Schema({
  username: { type: String, required: true, unique: true },
  displayName: { type: String, required: true },
  avatar: { type: String, default: "" },
  lastSeen: { type: Date, default: Date.now },
  createdAt: { type: Date, default: Date.now }
});

module.exports = mongoose.model("User", userSchema);
```

## server/models/Message.js

```javascript
const mongoose = require("mongoose");

const messageSchema = new mongoose.Schema({
  roomId: { type: String, required: true, index: true },
  senderId: { type: String, required: true },
  receiverId: { type: String, required: true },
  content: { type: String, required: true },
  deliveredAt: { type: Date, default: null },
  readAt: { type: Date, default: null },
  createdAt: { type: Date, default: Date.now }
});

// DM방 ID 생성: 두 유저 ID를 정렬하여 고유 키 생성
messageSchema.statics.createRoomId = function (userA, userB) {
  return [userA, userB].sort().join("_");
};

module.exports = mongoose.model("Message", messageSchema);
```

## server/socket/dmHandler.js

```javascript
const Message = require("../models/Message");

function setupDmHandler(io, socket, onlineUsers) {
  // DM방 입장: 두 유저 간 고유 룸 생성
  socket.on("join-dm", async ({ targetUserId }) => {
    const roomId = Message.createRoomId(socket.userId, targetUserId);
    socket.join(roomId);

    // 기존 메시지 로드 (최근 50건)
    const messages = await Message.find({ roomId })
      .sort({ createdAt: -1 })
      .limit(50)
      .lean();

    socket.emit("dm-history", { roomId, messages: messages.reverse() });

    // 안 읽은 메시지를 읽음 처리
    await Message.updateMany(
      { roomId, receiverId: socket.userId, readAt: null },
      { readAt: new Date() }
    );

    const targetSocketId = onlineUsers.get(targetUserId);
    if (targetSocketId) {
      io.to(targetSocketId).emit("messages-read", {
        roomId,
        readBy: socket.userId,
        readAt: new Date()
      });
    }
  });

  // 메시지 전송
  socket.on("send-dm", async ({ targetUserId, content }) => {
    const roomId = Message.createRoomId(socket.userId, targetUserId);
    const now = new Date();

    const message = await Message.create({
      roomId,
      senderId: socket.userId,
      receiverId: targetUserId,
      content,
      createdAt: now
    });

    // 수신자가 온라인이면 배달 확인 타임스탬프 설정
    const targetSocketId = onlineUsers.get(targetUserId);
    if (targetSocketId) {
      message.deliveredAt = now;
      await message.save();
    }

    io.to(roomId).emit("new-dm", message.toObject());

    // 수신자가 DM방에 없으면 알림 전송
    if (targetSocketId) {
      io.to(targetSocketId).emit("dm-notification", {
        roomId,
        senderId: socket.userId,
        content: content.substring(0, 50),
        createdAt: now
      });
    }
  });

  // 읽음 확인 처리
  socket.on("mark-read", async ({ roomId }) => {
    const readAt = new Date();
    await Message.updateMany(
      { roomId, receiverId: socket.userId, readAt: null },
      { readAt }
    );

    socket.to(roomId).emit("messages-read", {
      roomId,
      readBy: socket.userId,
      readAt
    });
  });

  // 타이핑 상태 전송
  socket.on("typing", ({ roomId, isTyping }) => {
    socket.to(roomId).emit("user-typing", {
      userId: socket.userId,
      isTyping
    });
  });
}

module.exports = { setupDmHandler };
```

## server/routes/conversations.js

```javascript
const express = require("express");
const router = express.Router();
const Message = require("../models/Message");

// 유저의 전체 대화 목록 조회
router.get("/:userId", async (req, res) => {
  const { userId } = req.params;

  const messages = await Message.aggregate([
    { $match: { $or: [{ senderId: userId }, { receiverId: userId }] } },
    { $sort: { createdAt: -1 } },
    {
      $group: {
        _id: "$roomId",
        lastMessage: { $first: "$$ROOT" },
        unreadCount: {
          $sum: {
            $cond: [
              { $and: [{ $eq: ["$receiverId", userId] }, { $eq: ["$readAt", null] }] },
              1, 0
            ]
          }
        }
      }
    },
    { $sort: { "lastMessage.createdAt": -1 } }
  ]);

  const conversations = messages.map((m) => ({
    roomId: m._id,
    partnerId: m.lastMessage.senderId === userId
      ? m.lastMessage.receiverId
      : m.lastMessage.senderId,
    lastMessage: m.lastMessage.content,
    lastMessageAt: m.lastMessage.createdAt,
    unreadCount: m.unreadCount
  }));

  res.json(conversations);
});

module.exports = router;
```

## client/index.html

```html
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>DM 시스템</title>
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <div id="app">
    <aside id="sidebar">
      <div id="user-info"></div>
      <h3>대화 목록</h3>
      <ul id="conversation-list"></ul>
      <h3>온라인 유저</h3>
      <ul id="online-list"></ul>
    </aside>
    <main id="chat-area">
      <div id="chat-header"></div>
      <div id="messages"></div>
      <div id="typing-indicator"></div>
      <form id="msg-form">
        <input type="text" id="msg-input" placeholder="메시지 입력..." />
        <button type="submit">전송</button>
      </form>
    </main>
  </div>
  <script src="/socket.io/socket.io.js"></script>
  <script src="app.js"></script>
</body>
</html>
```

## client/app.js

```javascript
const socket = io();
const myUserId = prompt("유저 ID를 입력하세요:") || "user_" + Date.now();
let currentRoomId = null;
let currentTarget = null;

socket.emit("register", myUserId);
document.getElementById("user-info").textContent = `나: ${myUserId}`;

// 온라인 유저 목록 갱신
socket.on("online-users", (users) => {
  const list = document.getElementById("online-list");
  list.innerHTML = users
    .filter((u) => u !== myUserId)
    .map((u) => `<li class="user-item" onclick="startDm('${u}')">${u} 🟢</li>`)
    .join("");
});

// DM 시작
function startDm(targetUserId) {
  currentTarget = targetUserId;
  document.getElementById("chat-header").textContent = `${targetUserId}님과의 대화`;
  document.getElementById("messages").innerHTML = "";
  socket.emit("join-dm", { targetUserId });
}

// 메시지 이력 수신
socket.on("dm-history", ({ roomId, messages }) => {
  currentRoomId = roomId;
  const container = document.getElementById("messages");
  container.innerHTML = messages.map((m) => renderMessage(m)).join("");
  container.scrollTop = container.scrollHeight;
});

// 새 메시지 수신
socket.on("new-dm", (msg) => {
  const container = document.getElementById("messages");
  container.innerHTML += renderMessage(msg);
  container.scrollTop = container.scrollHeight;

  if (msg.receiverId === myUserId) {
    socket.emit("mark-read", { roomId: currentRoomId });
  }
});

// 읽음 확인 표시
socket.on("messages-read", ({ roomId, readAt }) => {
  document.querySelectorAll(`[data-room="${roomId}"] .status`).forEach((el) => {
    el.textContent = `✓✓ 읽음 ${new Date(readAt).toLocaleTimeString("ko-KR")}`;
    el.classList.add("read");
  });
});

// 타이핑 표시
socket.on("user-typing", ({ userId, isTyping }) => {
  document.getElementById("typing-indicator").textContent =
    isTyping ? `${userId}님이 입력 중...` : "";
});

// 알림 수신
socket.on("dm-notification", ({ senderId, content }) => {
  if (currentTarget !== senderId) {
    const list = document.getElementById("conversation-list");
    list.innerHTML = `<li class="unread" onclick="startDm('${senderId}')">
      <strong>${senderId}</strong>: ${content}
    </li>` + list.innerHTML;
  }
});

// 메시지 전송
document.getElementById("msg-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const input = document.getElementById("msg-input");
  if (!input.value.trim() || !currentTarget) return;
  socket.emit("send-dm", { targetUserId: currentTarget, content: input.value.trim() });
  input.value = "";
});

// 타이핑 감지
let typingTimeout;
document.getElementById("msg-input").addEventListener("input", () => {
  if (currentRoomId) {
    socket.emit("typing", { roomId: currentRoomId, isTyping: true });
    clearTimeout(typingTimeout);
    typingTimeout = setTimeout(() => {
      socket.emit("typing", { roomId: currentRoomId, isTyping: false });
    }, 1500);
  }
});

function renderMessage(msg) {
  const isMine = msg.senderId === myUserId;
  const time = new Date(msg.createdAt).toLocaleTimeString("ko-KR");
  const status = isMine
    ? msg.readAt
      ? `✓✓ 읽음 ${new Date(msg.readAt).toLocaleTimeString("ko-KR")}`
      : msg.deliveredAt ? "✓ 배달됨" : "전송됨"
    : "";
  return `<div class="msg ${isMine ? "mine" : "theirs"}" data-room="${msg.roomId}">
    <div class="sender">${msg.senderId}</div>
    <div class="content">${msg.content}</div>
    <div class="meta"><span class="time">${time}</span> <span class="status">${status}</span></div>
  </div>`;
}
```

## client/style.css

```css
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: "Pretendard", sans-serif; background: #1a1a2e; color: #e0e0e0; }
#app { display: flex; height: 100vh; }
#sidebar { width: 280px; background: #16213e; padding: 16px; overflow-y: auto; border-right: 1px solid #0f3460; }
#sidebar h3 { color: #e94560; margin: 16px 0 8px; font-size: 14px; }
#user-info { padding: 12px; background: #0f3460; border-radius: 8px; text-align: center; font-weight: 600; }
.user-item { list-style: none; padding: 10px 12px; cursor: pointer; border-radius: 6px; transition: background 0.2s; }
.user-item:hover { background: #0f3460; }
.unread { background: #1a3a5c; font-weight: 600; border-radius: 6px; padding: 10px; margin-bottom: 4px; cursor: pointer; }
#chat-area { flex: 1; display: flex; flex-direction: column; }
#chat-header { padding: 16px 20px; background: #16213e; font-weight: 600; font-size: 16px; border-bottom: 1px solid #0f3460; }
#messages { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 8px; }
.msg { max-width: 65%; padding: 10px 14px; border-radius: 12px; }
.msg.mine { align-self: flex-end; background: #0f3460; }
.msg.theirs { align-self: flex-start; background: #533483; }
.sender { font-size: 11px; color: #aaa; margin-bottom: 2px; }
.content { font-size: 14px; line-height: 1.5; }
.meta { font-size: 10px; color: #888; text-align: right; margin-top: 4px; }
.status.read { color: #4fc3f7; }
#typing-indicator { padding: 4px 20px; font-size: 12px; color: #e94560; min-height: 20px; }
#msg-form { display: flex; padding: 12px 20px; background: #16213e; gap: 8px; }
#msg-input { flex: 1; padding: 10px 14px; border: 1px solid #0f3460; border-radius: 20px; background: #1a1a2e; color: #fff; outline: none; }
#msg-form button { padding: 10px 20px; background: #e94560; color: white; border: none; border-radius: 20px; cursor: pointer; font-weight: 600; }
```

모든 파일을 작성하면 `npm install` 후 MongoDB를 실행하고 `npm start`로 서버를 시작하세요. 브라우저 탭 2개를 열어 각각 다른 유저 ID로 접속하면 1:1 DM을 테스트할 수 있습니다.'''),

    # ═══ 2. WebSocket 실시간 투표/설문 시스템 ═══
    m("WebSocket으로 실시간 투표/설문 시스템 만들어줘 전체 코드로",
'''실시간 투표/설문 시스템을 만들어 드릴게요. 단일/다중 선택 투표, 실시간 집계, 퍼센트 막대 그래프, 마감 타이머를 구현합니다.

## 폴더 구조

```
poll-system/
├── server/
│   ├── index.js
│   ├── pollManager.js
│   └── wsHandler.js
├── client/
│   ├── index.html
│   ├── app.js
│   └── style.css
├── package.json
└── README.md
```

## package.json

```json
{
  "name": "poll-system",
  "version": "1.0.0",
  "scripts": {
    "start": "node server/index.js"
  },
  "dependencies": {
    "express": "^4.18.2",
    "ws": "^8.16.0",
    "uuid": "^9.0.0"
  }
}
```

## server/index.js

```javascript
const express = require("express");
const http = require("http");
const { WebSocketServer } = require("ws");
const { handleConnection } = require("./wsHandler");

const app = express();
const server = http.createServer(app);
const wss = new WebSocketServer({ server });

app.use(express.static("client"));

wss.on("connection", (ws) => handleConnection(ws, wss));

server.listen(3000, () => console.log("투표 서버 실행: http://localhost:3000"));
```

## server/pollManager.js

```javascript
const { v4: uuidv4 } = require("uuid");

// 인메모리 투표 저장소
const polls = new Map();
const timers = new Map();

function createPoll({ title, options, multiSelect, deadlineMinutes, creatorId }) {
  const id = uuidv4();
  const deadline = deadlineMinutes
    ? new Date(Date.now() + deadlineMinutes * 60000)
    : null;

  const poll = {
    id,
    title,
    options: options.map((text, idx) => ({ id: idx, text, votes: 0 })),
    multiSelect: multiSelect || false,
    deadline,
    creatorId,
    voters: {},  // { oderId: [optionIdx, ...] }
    closed: false,
    createdAt: new Date()
  };

  polls.set(id, poll);
  return poll;
}

function castVote(pollId, voterId, optionIds) {
  const poll = polls.get(pollId);
  if (!poll || poll.closed) return null;

  // 이전 투표 제거
  if (poll.voters[voterId]) {
    poll.voters[voterId].forEach((idx) => {
      poll.options[idx].votes = Math.max(0, poll.options[idx].votes - 1);
    });
  }

  // 단일 선택이면 첫 번째만
  const selected = poll.multiSelect ? optionIds : [optionIds[0]];
  selected.forEach((idx) => {
    if (poll.options[idx]) poll.options[idx].votes += 1;
  });
  poll.voters[voterId] = selected;

  return poll;
}

function closePoll(pollId) {
  const poll = polls.get(pollId);
  if (poll) poll.closed = true;
  return poll;
}

function getPoll(pollId) {
  return polls.get(pollId) || null;
}

function getAllPolls() {
  return Array.from(polls.values()).sort(
    (a, b) => b.createdAt - a.createdAt
  );
}

function getTotalVotes(poll) {
  return poll.options.reduce((sum, opt) => sum + opt.votes, 0);
}

function startDeadlineTimer(pollId, deadline, onExpire) {
  const remaining = deadline - Date.now();
  if (remaining <= 0) {
    closePoll(pollId);
    onExpire(pollId);
    return;
  }
  const timer = setTimeout(() => {
    closePoll(pollId);
    onExpire(pollId);
  }, remaining);
  timers.set(pollId, timer);
}

module.exports = {
  createPoll, castVote, closePoll, getPoll,
  getAllPolls, getTotalVotes, startDeadlineTimer
};
```

## server/wsHandler.js

```javascript
const pm = require("./pollManager");

const clients = new Map();
let clientIdCounter = 0;

function broadcast(wss, data) {
  const msg = JSON.stringify(data);
  wss.clients.forEach((c) => {
    if (c.readyState === 1) c.send(msg);
  });
}

function send(ws, data) {
  ws.send(JSON.stringify(data));
}

function handleConnection(ws, wss) {
  const clientId = `voter_${++clientIdCounter}`;
  clients.set(ws, clientId);

  send(ws, { type: "connected", clientId });
  send(ws, { type: "poll-list", polls: pm.getAllPolls() });

  ws.on("message", (raw) => {
    let msg;
    try { msg = JSON.parse(raw); } catch { return; }

    switch (msg.type) {
      case "create-poll": {
        const poll = pm.createPoll({ ...msg, creatorId: clientId });

        if (poll.deadline) {
          pm.startDeadlineTimer(poll.id, poll.deadline, (pollId) => {
            const closed = pm.getPoll(pollId);
            broadcast(wss, { type: "poll-closed", poll: closed });
          });
        }

        broadcast(wss, { type: "new-poll", poll });
        break;
      }

      case "vote": {
        const updated = pm.castVote(msg.pollId, clientId, msg.optionIds);
        if (updated) {
          broadcast(wss, {
            type: "poll-updated",
            poll: updated,
            totalVotes: pm.getTotalVotes(updated)
          });
        }
        break;
      }

      case "close-poll": {
        const poll = pm.getPoll(msg.pollId);
        if (poll && poll.creatorId === clientId) {
          pm.closePoll(msg.pollId);
          broadcast(wss, { type: "poll-closed", poll });
        }
        break;
      }
    }
  });

  ws.on("close", () => clients.delete(ws));
}

module.exports = { handleConnection };
```

## client/index.html

```html
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>실시간 투표 시스템</title>
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <div id="app">
    <header>
      <h1>실시간 투표/설문</h1>
      <button id="btn-create">+ 새 투표 만들기</button>
    </header>
    <div id="create-form" class="hidden">
      <input id="poll-title" placeholder="투표 제목" />
      <div id="options-container">
        <input class="option-input" placeholder="선택지 1" />
        <input class="option-input" placeholder="선택지 2" />
      </div>
      <button id="btn-add-option">+ 선택지 추가</button>
      <label><input type="checkbox" id="multi-select" /> 복수 선택 허용</label>
      <label>마감: <input type="number" id="deadline" placeholder="분" min="1" max="1440" /> 분</label>
      <button id="btn-submit">투표 생성</button>
    </div>
    <div id="polls"></div>
  </div>
  <script src="app.js"></script>
</body>
</html>
```

## client/app.js

```javascript
const ws = new WebSocket(`ws://${location.host}`);
let myClientId = null;

ws.onopen = () => console.log("WebSocket 연결 완료");

ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);

  switch (msg.type) {
    case "connected":
      myClientId = msg.clientId;
      break;
    case "poll-list":
      msg.polls.forEach((p) => renderPoll(p));
      break;
    case "new-poll":
      renderPoll(msg.poll);
      break;
    case "poll-updated":
      renderPoll(msg.poll);
      break;
    case "poll-closed":
      renderPoll(msg.poll);
      break;
  }
};

// 투표 생성 UI 토글
document.getElementById("btn-create").addEventListener("click", () => {
  document.getElementById("create-form").classList.toggle("hidden");
});

document.getElementById("btn-add-option").addEventListener("click", () => {
  const input = document.createElement("input");
  input.className = "option-input";
  input.placeholder = `선택지 ${document.querySelectorAll(".option-input").length + 1}`;
  document.getElementById("options-container").appendChild(input);
});

document.getElementById("btn-submit").addEventListener("click", () => {
  const title = document.getElementById("poll-title").value.trim();
  const options = Array.from(document.querySelectorAll(".option-input"))
    .map((i) => i.value.trim())
    .filter(Boolean);
  const multiSelect = document.getElementById("multi-select").checked;
  const deadlineMinutes = parseInt(document.getElementById("deadline").value) || 0;

  if (!title || options.length < 2) return alert("제목과 최소 2개 선택지를 입력하세요.");

  ws.send(JSON.stringify({
    type: "create-poll", title, options, multiSelect,
    deadlineMinutes: deadlineMinutes || null
  }));

  document.getElementById("create-form").classList.add("hidden");
  document.getElementById("poll-title").value = "";
  document.querySelectorAll(".option-input").forEach((i) => (i.value = ""));
});

function renderPoll(poll) {
  let el = document.getElementById(`poll-${poll.id}`);
  if (!el) {
    el = document.createElement("div");
    el.id = `poll-${poll.id}`;
    el.className = "poll-card";
    document.getElementById("polls").prepend(el);
  }

  const totalVotes = poll.options.reduce((s, o) => s + o.votes, 0);
  const isMine = poll.creatorId === myClientId;
  const inputType = poll.multiSelect ? "checkbox" : "radio";

  let deadlineHtml = "";
  if (poll.deadline && !poll.closed) {
    const remain = Math.max(0, Math.floor((new Date(poll.deadline) - Date.now()) / 1000));
    const mins = Math.floor(remain / 60);
    const secs = remain % 60;
    deadlineHtml = `<div class="deadline">남은 시간: ${mins}분 ${secs}초</div>`;
  }

  el.className = `poll-card ${poll.closed ? "closed" : ""}`;
  el.innerHTML = `
    <h3>${poll.title} ${poll.closed ? "<span class='badge'>마감</span>" : ""}
      ${poll.multiSelect ? "<span class='badge multi'>복수선택</span>" : ""}
    </h3>
    ${deadlineHtml}
    <div class="options">
      ${poll.options.map((opt) => {
        const pct = totalVotes > 0 ? ((opt.votes / totalVotes) * 100).toFixed(1) : 0;
        return `<div class="option" onclick="vote('${poll.id}', ${opt.id})">
          <div class="bar" style="width:${pct}%"></div>
          <span class="opt-text">${opt.text}</span>
          <span class="opt-pct">${pct}% (${opt.votes}표)</span>
        </div>`;
      }).join("")}
    </div>
    <div class="total">총 ${totalVotes}표 참여</div>
    ${isMine && !poll.closed ? `<button onclick="closePoll('${poll.id}')">투표 마감</button>` : ""}
  `;

  // 마감 타이머 갱신
  if (poll.deadline && !poll.closed) {
    setTimeout(() => renderPoll(poll), 1000);
  }
}

function vote(pollId, optionId) {
  ws.send(JSON.stringify({ type: "vote", pollId, optionIds: [optionId] }));
}

function closePoll(pollId) {
  ws.send(JSON.stringify({ type: "close-poll", pollId }));
}
```

## client/style.css

```css
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: "Pretendard", sans-serif; background: #0f0f23; color: #e0e0e0; }
#app { max-width: 720px; margin: 0 auto; padding: 20px; }
header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
h1 { font-size: 22px; color: #4fc3f7; }
button { padding: 8px 16px; background: #e94560; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; }
#create-form { background: #1a1a3e; padding: 16px; border-radius: 10px; margin-bottom: 20px; display: flex; flex-direction: column; gap: 10px; }
.hidden { display: none !important; }
#create-form input { padding: 10px; border: 1px solid #333; border-radius: 6px; background: #12122b; color: #fff; }
#create-form label { font-size: 13px; display: flex; align-items: center; gap: 6px; }
.poll-card { background: #1a1a3e; border-radius: 10px; padding: 20px; margin-bottom: 16px; }
.poll-card.closed { opacity: 0.7; }
.poll-card h3 { margin-bottom: 12px; font-size: 18px; }
.badge { font-size: 11px; background: #e94560; padding: 2px 8px; border-radius: 10px; margin-left: 8px; }
.badge.multi { background: #4fc3f7; color: #000; }
.deadline { color: #e94560; font-size: 13px; margin-bottom: 10px; font-weight: 600; }
.options { display: flex; flex-direction: column; gap: 8px; }
.option { position: relative; padding: 12px 14px; background: #12122b; border-radius: 8px; cursor: pointer; overflow: hidden; display: flex; justify-content: space-between; }
.option:hover { background: #1e1e4a; }
.bar { position: absolute; left: 0; top: 0; height: 100%; background: rgba(79, 195, 247, 0.15); transition: width 0.5s ease; }
.opt-text { position: relative; z-index: 1; }
.opt-pct { position: relative; z-index: 1; color: #4fc3f7; font-weight: 600; font-size: 13px; }
.total { margin-top: 12px; font-size: 13px; color: #888; }
```

`npm install` 후 `npm start`로 실행하세요. 브라우저 탭 여러 개를 열어 동시 투표를 테스트할 수 있습니다.'''),

    # ═══ 3. Socket.IO 채팅방 관리자 기능 ═══
    m("Socket.IO로 채팅방 관리자 기능 만들어줘 전체 코드로",
'''채팅방 관리자 기능 시스템을 만들어 드릴게요. 강퇴/뮤트/밴, 공지사항, 방 설정(이름/설명/비공개), 멤버 역할 관리를 구현합니다.

## 폴더 구조

```
chat-admin/
├── server/
│   ├── index.js
│   ├── roomManager.js
│   └── socket/
│       ├── chatHandler.js
│       └── adminHandler.js
├── client/
│   ├── index.html
│   ├── app.js
│   └── style.css
└── package.json
```

## package.json

```json
{
  "name": "chat-admin",
  "version": "1.0.0",
  "scripts": {
    "start": "node server/index.js"
  },
  "dependencies": {
    "express": "^4.18.2",
    "socket.io": "^4.7.4"
  }
}
```

## server/roomManager.js

```javascript
// 인메모리 방/멤버 관리
const rooms = new Map();

const ROLES = { OWNER: "owner", ADMIN: "admin", MEMBER: "member" };

function createRoom(roomId, ownerId, options = {}) {
  const room = {
    id: roomId,
    name: options.name || roomId,
    description: options.description || "",
    isPrivate: options.isPrivate || false,
    ownerId,
    members: new Map([[ownerId, { role: ROLES.OWNER, joinedAt: new Date(), muted: false }]]),
    bannedUsers: new Set(),
    announcements: [],
    createdAt: new Date()
  };
  rooms.set(roomId, room);
  return room;
}

function getRoom(roomId) {
  return rooms.get(roomId) || null;
}

function getAllRooms() {
  return Array.from(rooms.values())
    .filter((r) => !r.isPrivate)
    .map((r) => ({
      id: r.id, name: r.name, description: r.description,
      memberCount: r.members.size, isPrivate: r.isPrivate
    }));
}

function joinRoom(roomId, userId) {
  const room = rooms.get(roomId);
  if (!room) return { error: "방이 존재하지 않습니다." };
  if (room.bannedUsers.has(userId)) return { error: "차단된 사용자입니다." };
  if (!room.members.has(userId)) {
    room.members.set(userId, { role: ROLES.MEMBER, joinedAt: new Date(), muted: false });
  }
  return { success: true };
}

function hasPermission(roomId, userId) {
  const room = rooms.get(roomId);
  if (!room) return false;
  const member = room.members.get(userId);
  return member && (member.role === ROLES.OWNER || member.role === ROLES.ADMIN);
}

function kickUser(roomId, adminId, targetId) {
  if (!hasPermission(roomId, adminId)) return { error: "권한이 없습니다." };
  const room = rooms.get(roomId);
  const target = room.members.get(targetId);
  if (!target) return { error: "멤버가 아닙니다." };
  if (target.role === ROLES.OWNER) return { error: "방장은 강퇴할 수 없습니다." };
  room.members.delete(targetId);
  return { success: true };
}

function muteUser(roomId, adminId, targetId, duration) {
  if (!hasPermission(roomId, adminId)) return { error: "권한이 없습니다." };
  const room = rooms.get(roomId);
  const target = room.members.get(targetId);
  if (!target) return { error: "멤버가 아닙니다." };
  target.muted = true;
  target.muteUntil = new Date(Date.now() + duration * 60000);
  return { success: true, muteUntil: target.muteUntil };
}

function banUser(roomId, adminId, targetId) {
  if (!hasPermission(roomId, adminId)) return { error: "권한이 없습니다." };
  const room = rooms.get(roomId);
  const target = room.members.get(targetId);
  if (target && target.role === ROLES.OWNER) return { error: "방장은 밴할 수 없습니다." };
  room.members.delete(targetId);
  room.bannedUsers.add(targetId);
  return { success: true };
}

function setRole(roomId, ownerId, targetId, newRole) {
  const room = rooms.get(roomId);
  if (!room || room.ownerId !== ownerId) return { error: "방장만 역할을 변경할 수 있습니다." };
  const target = room.members.get(targetId);
  if (!target) return { error: "멤버가 아닙니다." };
  if (newRole === ROLES.OWNER) return { error: "방장 위임은 별도 기능입니다." };
  target.role = newRole;
  return { success: true, role: newRole };
}

function addAnnouncement(roomId, adminId, text) {
  if (!hasPermission(roomId, adminId)) return { error: "권한이 없습니다." };
  const room = rooms.get(roomId);
  const announcement = { id: Date.now(), text, authorId: adminId, createdAt: new Date() };
  room.announcements.unshift(announcement);
  if (room.announcements.length > 10) room.announcements.pop();
  return announcement;
}

function updateSettings(roomId, ownerId, settings) {
  const room = rooms.get(roomId);
  if (!room) return { error: "방이 없습니다." };
  if (!hasPermission(roomId, ownerId)) return { error: "권한이 없습니다." };
  if (settings.name) room.name = settings.name;
  if (settings.description !== undefined) room.description = settings.description;
  if (settings.isPrivate !== undefined) room.isPrivate = settings.isPrivate;
  return { success: true, room: { name: room.name, description: room.description, isPrivate: room.isPrivate } };
}

function isMuted(roomId, userId) {
  const room = rooms.get(roomId);
  if (!room) return false;
  const member = room.members.get(userId);
  if (!member || !member.muted) return false;
  if (member.muteUntil && member.muteUntil < new Date()) {
    member.muted = false;
    return false;
  }
  return true;
}

function getMemberList(roomId) {
  const room = rooms.get(roomId);
  if (!room) return [];
  return Array.from(room.members.entries()).map(([userId, info]) => ({
    userId, role: info.role, muted: info.muted, joinedAt: info.joinedAt
  }));
}

module.exports = {
  ROLES, createRoom, getRoom, getAllRooms, joinRoom,
  kickUser, muteUser, banUser, setRole, addAnnouncement,
  updateSettings, isMuted, getMemberList, hasPermission
};
```

## server/socket/chatHandler.js

```javascript
const rm = require("../roomManager");

function setupChatHandler(io, socket) {
  socket.on("join-room", ({ roomId }) => {
    const result = rm.joinRoom(roomId, socket.userId);
    if (result.error) return socket.emit("error", result.error);
    socket.join(roomId);
    socket.currentRoom = roomId;

    const members = rm.getMemberList(roomId);
    const room = rm.getRoom(roomId);
    socket.emit("room-joined", {
      roomId, name: room.name, description: room.description,
      members, announcements: room.announcements
    });
    socket.to(roomId).emit("member-joined", { userId: socket.userId });
  });

  socket.on("chat-message", ({ roomId, content }) => {
    if (rm.isMuted(roomId, socket.userId)) {
      return socket.emit("error", "현재 뮤트 상태입니다. 잠시 후 다시 시도하세요.");
    }
    io.to(roomId).emit("chat-message", {
      userId: socket.userId,
      content,
      timestamp: new Date()
    });
  });

  socket.on("leave-room", ({ roomId }) => {
    socket.leave(roomId);
    socket.to(roomId).emit("member-left", { userId: socket.userId });
  });
}

module.exports = { setupChatHandler };
```

## server/socket/adminHandler.js

```javascript
const rm = require("../roomManager");

function setupAdminHandler(io, socket) {
  socket.on("create-room", ({ name, description, isPrivate }) => {
    const roomId = `room_${Date.now()}`;
    const room = rm.createRoom(roomId, socket.userId, { name, description, isPrivate });
    socket.join(roomId);
    socket.currentRoom = roomId;
    socket.emit("room-created", { roomId, name: room.name });
    io.emit("room-list", rm.getAllRooms());
  });

  socket.on("kick-user", ({ roomId, targetId }) => {
    const result = rm.kickUser(roomId, socket.userId, targetId);
    if (result.error) return socket.emit("error", result.error);
    io.to(roomId).emit("user-kicked", { userId: targetId, by: socket.userId });
    io.emit("force-leave", { roomId, userId: targetId });
  });

  socket.on("mute-user", ({ roomId, targetId, duration }) => {
    const result = rm.muteUser(roomId, socket.userId, targetId, duration || 5);
    if (result.error) return socket.emit("error", result.error);
    io.to(roomId).emit("user-muted", {
      userId: targetId, by: socket.userId, until: result.muteUntil
    });
  });

  socket.on("ban-user", ({ roomId, targetId }) => {
    const result = rm.banUser(roomId, socket.userId, targetId);
    if (result.error) return socket.emit("error", result.error);
    io.to(roomId).emit("user-banned", { userId: targetId, by: socket.userId });
    io.emit("force-leave", { roomId, userId: targetId });
  });

  socket.on("set-role", ({ roomId, targetId, role }) => {
    const result = rm.setRole(roomId, socket.userId, targetId, role);
    if (result.error) return socket.emit("error", result.error);
    io.to(roomId).emit("role-changed", { userId: targetId, role: result.role });
  });

  socket.on("announce", ({ roomId, text }) => {
    const result = rm.addAnnouncement(roomId, socket.userId, text);
    if (result.error) return socket.emit("error", result.error);
    io.to(roomId).emit("new-announcement", result);
  });

  socket.on("update-settings", ({ roomId, settings }) => {
    const result = rm.updateSettings(roomId, socket.userId, settings);
    if (result.error) return socket.emit("error", result.error);
    io.to(roomId).emit("settings-updated", result.room);
    io.emit("room-list", rm.getAllRooms());
  });

  socket.on("get-rooms", () => {
    socket.emit("room-list", rm.getAllRooms());
  });

  socket.on("get-members", ({ roomId }) => {
    socket.emit("member-list", rm.getMemberList(roomId));
  });
}

module.exports = { setupAdminHandler };
```

## server/index.js

```javascript
const express = require("express");
const http = require("http");
const { Server } = require("socket.io");
const { setupChatHandler } = require("./socket/chatHandler");
const { setupAdminHandler } = require("./socket/adminHandler");

const app = express();
const server = http.createServer(app);
const io = new Server(server, { cors: { origin: "*" } });

app.use(express.static("client"));

io.on("connection", (socket) => {
  socket.on("register", (userId) => {
    socket.userId = userId;
    console.log(`${userId} 접속`);
    socket.emit("registered", { userId });
  });

  setupChatHandler(io, socket);
  setupAdminHandler(io, socket);

  socket.on("disconnect", () => {
    if (socket.currentRoom) {
      socket.to(socket.currentRoom).emit("member-left", { userId: socket.userId });
    }
  });
});

server.listen(3000, () => console.log("채팅 관리자 서버 실행: http://localhost:3000"));
```

## client/index.html

```html
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>채팅방 관리자</title>
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <div id="app">
    <aside id="sidebar">
      <div id="user-info"></div>
      <button id="btn-create-room">+ 방 만들기</button>
      <div id="create-room-form" class="hidden">
        <input id="room-name" placeholder="방 이름" />
        <input id="room-desc" placeholder="설명" />
        <label><input type="checkbox" id="room-private" /> 비공개</label>
        <button id="btn-submit-room">생성</button>
      </div>
      <h3>채팅방 목록</h3>
      <ul id="room-list"></ul>
    </aside>
    <main id="chat-area">
      <div id="room-header"></div>
      <div id="announcement-bar"></div>
      <div id="messages"></div>
      <form id="msg-form">
        <input id="msg-input" placeholder="메시지 입력..." />
        <button type="submit">전송</button>
      </form>
    </main>
    <aside id="member-panel">
      <h3>멤버 목록</h3>
      <ul id="member-list"></ul>
      <div id="admin-panel" class="hidden">
        <h4>관리자 도구</h4>
        <input id="target-user" placeholder="대상 유저 ID" />
        <div class="admin-buttons">
          <button onclick="doKick()">강퇴</button>
          <button onclick="doMute()">뮤트(5분)</button>
          <button onclick="doBan()">밴</button>
          <button onclick="doPromote()">관리자 임명</button>
          <button onclick="doDemote()">관리자 해제</button>
        </div>
        <hr />
        <h4>공지사항</h4>
        <input id="announce-input" placeholder="공지 내용" />
        <button onclick="doAnnounce()">공지 등록</button>
        <hr />
        <h4>방 설정</h4>
        <input id="edit-name" placeholder="방 이름 변경" />
        <input id="edit-desc" placeholder="설명 변경" />
        <button onclick="doUpdateSettings()">설정 저장</button>
      </div>
    </aside>
  </div>
  <script src="/socket.io/socket.io.js"></script>
  <script src="app.js"></script>
</body>
</html>
```

## client/app.js

```javascript
const socket = io();
const myUserId = prompt("유저 ID를 입력하세요:") || "user_" + Date.now();
let currentRoom = null;
let myRole = "member";

socket.emit("register", myUserId);
socket.emit("get-rooms");
document.getElementById("user-info").textContent = myUserId;

// 방 목록
socket.on("room-list", (rooms) => {
  document.getElementById("room-list").innerHTML = rooms
    .map((r) => `<li onclick="joinRoom('${r.id}')">${r.name} (${r.memberCount}명)</li>`)
    .join("");
});

socket.on("room-joined", ({ roomId, name, description, members, announcements }) => {
  currentRoom = roomId;
  document.getElementById("room-header").innerHTML =
    `<h2>${name}</h2><p>${description}</p>`;
  document.getElementById("messages").innerHTML = "";

  if (announcements.length > 0) {
    document.getElementById("announcement-bar").innerHTML =
      `<div class="announce">📢 ${announcements[0].text}</div>`;
  }

  const me = members.find((m) => m.userId === myUserId);
  myRole = me ? me.role : "member";
  renderMembers(members);
  toggleAdminPanel();
});

socket.on("chat-message", ({ userId, content, timestamp }) => {
  const el = document.getElementById("messages");
  const time = new Date(timestamp).toLocaleTimeString("ko-KR");
  el.innerHTML += `<div class="msg"><span class="sender">${userId}</span>
    <span class="text">${content}</span><span class="time">${time}</span></div>`;
  el.scrollTop = el.scrollHeight;
});

socket.on("user-kicked", ({ userId, by }) => appendSystem(`${userId}님이 ${by}에 의해 강퇴됨`));
socket.on("user-muted", ({ userId, until }) => appendSystem(`${userId}님 뮤트됨 (~${new Date(until).toLocaleTimeString("ko-KR")})`));
socket.on("user-banned", ({ userId }) => appendSystem(`${userId}님이 밴됨`));
socket.on("member-joined", ({ userId }) => appendSystem(`${userId}님 입장`));
socket.on("member-left", ({ userId }) => appendSystem(`${userId}님 퇴장`));
socket.on("role-changed", ({ userId, role }) => { appendSystem(`${userId}님 역할 변경: ${role}`); if (userId === myUserId) { myRole = role; toggleAdminPanel(); } });
socket.on("new-announcement", (a) => { document.getElementById("announcement-bar").innerHTML = `<div class="announce">📢 ${a.text}</div>`; });
socket.on("settings-updated", ({ name, description }) => { document.getElementById("room-header").innerHTML = `<h2>${name}</h2><p>${description}</p>`; });
socket.on("member-list", (members) => renderMembers(members));
socket.on("force-leave", ({ roomId, userId }) => { if (userId === myUserId) { alert("방에서 퇴장당했습니다."); currentRoom = null; document.getElementById("messages").innerHTML = ""; } });
socket.on("error", (msg) => alert(`오류: ${msg}`));

// 방 만들기
document.getElementById("btn-create-room").addEventListener("click", () => {
  document.getElementById("create-room-form").classList.toggle("hidden");
});
document.getElementById("btn-submit-room").addEventListener("click", () => {
  socket.emit("create-room", {
    name: document.getElementById("room-name").value || "새 방",
    description: document.getElementById("room-desc").value || "",
    isPrivate: document.getElementById("room-private").checked
  });
  document.getElementById("create-room-form").classList.add("hidden");
});

document.getElementById("msg-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const input = document.getElementById("msg-input");
  if (!input.value.trim() || !currentRoom) return;
  socket.emit("chat-message", { roomId: currentRoom, content: input.value.trim() });
  input.value = "";
});

function joinRoom(roomId) { socket.emit("join-room", { roomId }); }

function renderMembers(members) {
  const roleIcon = { owner: "👑", admin: "⭐", member: "" };
  document.getElementById("member-list").innerHTML = members
    .map((m) => `<li>${roleIcon[m.role] || ""} ${m.userId} ${m.muted ? "🔇" : ""}</li>`)
    .join("");
}

function toggleAdminPanel() {
  const panel = document.getElementById("admin-panel");
  panel.classList.toggle("hidden", myRole === "member");
}

function getTarget() { return document.getElementById("target-user").value.trim(); }
function doKick() { if (getTarget()) socket.emit("kick-user", { roomId: currentRoom, targetId: getTarget() }); }
function doMute() { if (getTarget()) socket.emit("mute-user", { roomId: currentRoom, targetId: getTarget(), duration: 5 }); }
function doBan() { if (getTarget()) socket.emit("ban-user", { roomId: currentRoom, targetId: getTarget() }); }
function doPromote() { if (getTarget()) socket.emit("set-role", { roomId: currentRoom, targetId: getTarget(), role: "admin" }); }
function doDemote() { if (getTarget()) socket.emit("set-role", { roomId: currentRoom, targetId: getTarget(), role: "member" }); }
function doAnnounce() { const t = document.getElementById("announce-input").value.trim(); if (t) socket.emit("announce", { roomId: currentRoom, text: t }); }
function doUpdateSettings() {
  socket.emit("update-settings", {
    roomId: currentRoom,
    settings: {
      name: document.getElementById("edit-name").value || undefined,
      description: document.getElementById("edit-desc").value || undefined
    }
  });
}
function appendSystem(text) {
  const el = document.getElementById("messages");
  el.innerHTML += `<div class="system-msg">ℹ ${text}</div>`;
  el.scrollTop = el.scrollHeight;
}
```

## client/style.css

```css
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: "Pretendard", sans-serif; background: #0f0f23; color: #e0e0e0; }
#app { display: grid; grid-template-columns: 240px 1fr 260px; height: 100vh; }
#sidebar { background: #16213e; padding: 16px; overflow-y: auto; }
#sidebar h3 { color: #e94560; margin: 16px 0 8px; }
#sidebar ul { list-style: none; }
#sidebar li { padding: 10px; cursor: pointer; border-radius: 6px; }
#sidebar li:hover { background: #0f3460; }
#user-info { padding: 10px; background: #0f3460; border-radius: 8px; text-align: center; font-weight: 600; margin-bottom: 12px; }
.hidden { display: none !important; }
#create-room-form { display: flex; flex-direction: column; gap: 6px; margin: 8px 0; }
#create-room-form input { padding: 8px; border: 1px solid #333; border-radius: 4px; background: #0f0f23; color: #fff; }
button { padding: 8px 14px; background: #e94560; border: none; color: white; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 12px; }
#chat-area { display: flex; flex-direction: column; }
#room-header { padding: 14px 20px; background: #16213e; border-bottom: 1px solid #0f3460; }
#room-header h2 { font-size: 16px; } #room-header p { font-size: 12px; color: #888; }
.announce { background: #1a3a5c; padding: 8px 20px; font-size: 13px; color: #4fc3f7; }
#messages { flex: 1; overflow-y: auto; padding: 16px 20px; display: flex; flex-direction: column; gap: 6px; }
.msg { display: flex; gap: 8px; align-items: baseline; } .sender { color: #e94560; font-weight: 600; font-size: 13px; }
.text { font-size: 14px; } .time { font-size: 10px; color: #666; }
.system-msg { font-size: 12px; color: #4fc3f7; text-align: center; padding: 4px; }
#msg-form { display: flex; padding: 12px 20px; gap: 8px; background: #16213e; }
#msg-input { flex: 1; padding: 10px; border: 1px solid #0f3460; border-radius: 20px; background: #0f0f23; color: #fff; outline: none; }
#member-panel { background: #16213e; padding: 16px; overflow-y: auto; border-left: 1px solid #0f3460; }
#member-panel h3, #member-panel h4 { color: #e94560; margin: 12px 0 6px; font-size: 14px; }
#member-panel ul { list-style: none; } #member-panel li { padding: 6px 0; font-size: 13px; }
#admin-panel { margin-top: 16px; } #admin-panel input { width: 100%; padding: 6px; margin: 4px 0; border: 1px solid #333; border-radius: 4px; background: #0f0f23; color: #fff; }
.admin-buttons { display: flex; flex-wrap: wrap; gap: 4px; margin: 6px 0; }
.admin-buttons button { font-size: 11px; padding: 4px 8px; }
hr { border: none; border-top: 1px solid #333; margin: 10px 0; }
```

`npm install && npm start`로 실행 후 브라우저 여러 탭에서 다른 유저로 접속하여 방 생성, 관리자 기능을 테스트할 수 있습니다.'''),

    # ═══ 4. WebSocket 실시간 주식 시세 대시보드 ═══
    m("WebSocket으로 실시간 주식 시세 대시보드 만들어줘 전체 코드로",
'''실시간 주식 시세 대시보드를 만들어 드릴게요. 모의 시세 스트리밍, 캔들스틱 표시, 관심종목, 가격 알림, 거래량 추적을 구현합니다.

## 폴더 구조

```
stock-dashboard/
├── server/
│   ├── index.js
│   ├── stockEngine.js
│   └── wsHandler.js
├── client/
│   ├── index.html
│   ├── app.js
│   ├── chart.js
│   └── style.css
└── package.json
```

## package.json

```json
{
  "name": "stock-dashboard",
  "version": "1.0.0",
  "scripts": {
    "start": "node server/index.js"
  },
  "dependencies": {
    "express": "^4.18.2",
    "ws": "^8.16.0"
  }
}
```

## server/stockEngine.js

```javascript
// 모의 주식 데이터 엔진
const STOCKS = {
  "SAMS": { name: "삼성전자", price: 72000, volume: 0 },
  "SKHY": { name: "SK하이닉스", price: 185000, volume: 0 },
  "NAVER": { name: "네이버", price: 210000, volume: 0 },
  "KAKAO": { name: "카카오", price: 52000, volume: 0 },
  "LG_EN": { name: "LG에너지솔루션", price: 390000, volume: 0 },
  "HYUN": { name: "현대차", price: 245000, volume: 0 },
  "CELL": { name: "셀트리온", price: 178000, volume: 0 },
  "KB_FN": { name: "KB금융", price: 68000, volume: 0 }
};

const priceHistory = {};
const candleData = {};

// 초기화: 각 종목 히스토리
Object.keys(STOCKS).forEach((symbol) => {
  priceHistory[symbol] = [STOCKS[symbol].price];
  candleData[symbol] = [];
});

function generateTick() {
  const updates = {};

  Object.entries(STOCKS).forEach(([symbol, stock]) => {
    // 랜덤 가격 변동 (-2% ~ +2%)
    const change = stock.price * (Math.random() * 0.04 - 0.02);
    const newPrice = Math.round(stock.price + change);
    const vol = Math.floor(Math.random() * 50000) + 1000;

    stock.price = Math.max(newPrice, 100);
    stock.volume += vol;

    priceHistory[symbol].push(stock.price);
    if (priceHistory[symbol].length > 100) priceHistory[symbol].shift();

    updates[symbol] = {
      symbol,
      name: stock.name,
      price: stock.price,
      change: Math.round(change),
      changePercent: ((change / (stock.price - change)) * 100).toFixed(2),
      volume: stock.volume,
      tickVolume: vol,
      high: Math.max(...priceHistory[symbol].slice(-20)),
      low: Math.min(...priceHistory[symbol].slice(-20)),
      timestamp: Date.now()
    };
  });

  return updates;
}

// 1분 캔들 생성
function generateCandle(symbol) {
  const history = priceHistory[symbol];
  if (history.length < 2) return null;
  const recent = history.slice(-10);
  const candle = {
    open: recent[0],
    close: recent[recent.length - 1],
    high: Math.max(...recent),
    low: Math.min(...recent),
    volume: STOCKS[symbol].volume,
    timestamp: Date.now()
  };
  candleData[symbol].push(candle);
  if (candleData[symbol].length > 60) candleData[symbol].shift();
  return candle;
}

function getStockList() {
  return Object.entries(STOCKS).map(([symbol, s]) => ({
    symbol, name: s.name, price: s.price, volume: s.volume
  }));
}

function getCandles(symbol) {
  return candleData[symbol] || [];
}

function getPriceHistory(symbol) {
  return priceHistory[symbol] || [];
}

module.exports = { generateTick, generateCandle, getStockList, getCandles, getPriceHistory, STOCKS };
```

## server/wsHandler.js

```javascript
const engine = require("./stockEngine");

const clients = new Map();

function broadcast(wss, data) {
  const msg = JSON.stringify(data);
  wss.clients.forEach((c) => { if (c.readyState === 1) c.send(msg); });
}

function send(ws, data) {
  if (ws.readyState === 1) ws.send(JSON.stringify(data));
}

function handleConnection(ws, wss) {
  const clientState = {
    watchlist: new Set(["SAMS", "SKHY", "NAVER"]),
    alerts: []  // { symbol, targetPrice, direction }
  };
  clients.set(ws, clientState);

  send(ws, { type: "stock-list", stocks: engine.getStockList() });
  send(ws, { type: "watchlist", symbols: Array.from(clientState.watchlist) });

  ws.on("message", (raw) => {
    let msg;
    try { msg = JSON.parse(raw); } catch { return; }

    switch (msg.type) {
      case "add-watchlist":
        clientState.watchlist.add(msg.symbol);
        send(ws, { type: "watchlist", symbols: Array.from(clientState.watchlist) });
        break;

      case "remove-watchlist":
        clientState.watchlist.delete(msg.symbol);
        send(ws, { type: "watchlist", symbols: Array.from(clientState.watchlist) });
        break;

      case "set-alert":
        clientState.alerts.push({
          symbol: msg.symbol,
          targetPrice: msg.targetPrice,
          direction: msg.direction  // "above" | "below"
        });
        send(ws, { type: "alert-set", alerts: clientState.alerts });
        break;

      case "get-candles":
        send(ws, { type: "candle-data", symbol: msg.symbol, candles: engine.getCandles(msg.symbol) });
        break;

      case "get-history":
        send(ws, { type: "price-history", symbol: msg.symbol, prices: engine.getPriceHistory(msg.symbol) });
        break;
    }
  });

  ws.on("close", () => clients.delete(ws));
}

function checkAlerts(wss, updates) {
  clients.forEach((state, ws) => {
    state.alerts = state.alerts.filter((alert) => {
      const tick = updates[alert.symbol];
      if (!tick) return true;
      const triggered =
        (alert.direction === "above" && tick.price >= alert.targetPrice) ||
        (alert.direction === "below" && tick.price <= alert.targetPrice);
      if (triggered) {
        send(ws, {
          type: "alert-triggered",
          symbol: alert.symbol,
          price: tick.price,
          targetPrice: alert.targetPrice,
          direction: alert.direction
        });
        return false;
      }
      return true;
    });
  });
}

module.exports = { handleConnection, broadcast, checkAlerts };
```

## server/index.js

```javascript
const express = require("express");
const http = require("http");
const { WebSocketServer } = require("ws");
const engine = require("./stockEngine");
const { handleConnection, broadcast, checkAlerts } = require("./wsHandler");

const app = express();
const server = http.createServer(app);
const wss = new WebSocketServer({ server });

app.use(express.static("client"));

wss.on("connection", (ws) => handleConnection(ws, wss));

// 1초마다 시세 업데이트
setInterval(() => {
  const updates = engine.generateTick();
  broadcast(wss, { type: "tick", data: updates });
  checkAlerts(wss, updates);
}, 1000);

// 10초마다 캔들 생성
setInterval(() => {
  Object.keys(engine.STOCKS).forEach((symbol) => {
    const candle = engine.generateCandle(symbol);
    if (candle) {
      broadcast(wss, { type: "new-candle", symbol, candle });
    }
  });
}, 10000);

server.listen(3000, () => console.log("주식 대시보드 서버 실행: http://localhost:3000"));
```

## client/chart.js

```javascript
// 간단한 캔버스 기반 캔들스틱 차트
class CandleChart {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    this.ctx = this.canvas.getContext("2d");
    this.candles = [];
    this.resize();
    window.addEventListener("resize", () => this.resize());
  }

  resize() {
    this.canvas.width = this.canvas.parentElement.clientWidth;
    this.canvas.height = 300;
    this.draw();
  }

  update(candles) {
    this.candles = candles.slice(-40);
    this.draw();
  }

  draw() {
    const { ctx, canvas, candles } = this;
    const w = canvas.width;
    const h = canvas.height;
    const padding = 40;

    ctx.fillStyle = "#0f0f23";
    ctx.fillRect(0, 0, w, h);

    if (candles.length === 0) {
      ctx.fillStyle = "#666";
      ctx.font = "14px sans-serif";
      ctx.fillText("데이터를 기다리는 중...", w / 2 - 80, h / 2);
      return;
    }

    const allPrices = candles.flatMap((c) => [c.high, c.low]);
    const maxPrice = Math.max(...allPrices);
    const minPrice = Math.min(...allPrices);
    const priceRange = maxPrice - minPrice || 1;

    const barWidth = (w - padding * 2) / candles.length;
    const toY = (price) => padding + ((maxPrice - price) / priceRange) * (h - padding * 2);

    // 그리드 라인
    ctx.strokeStyle = "#1a1a3e";
    ctx.lineWidth = 0.5;
    for (let i = 0; i <= 4; i++) {
      const y = padding + (i / 4) * (h - padding * 2);
      ctx.beginPath(); ctx.moveTo(padding, y); ctx.lineTo(w - padding, y); ctx.stroke();
      ctx.fillStyle = "#666";
      ctx.font = "10px sans-serif";
      const price = maxPrice - (i / 4) * priceRange;
      ctx.fillText(Math.round(price).toLocaleString(), 2, y + 3);
    }

    candles.forEach((candle, i) => {
      const x = padding + i * barWidth + barWidth / 2;
      const isUp = candle.close >= candle.open;
      const color = isUp ? "#e94560" : "#4fc3f7";

      // 심지(위꼬리/아래꼬리)
      ctx.strokeStyle = color;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, toY(candle.high));
      ctx.lineTo(x, toY(candle.low));
      ctx.stroke();

      // 몸통
      const bodyTop = toY(Math.max(candle.open, candle.close));
      const bodyBottom = toY(Math.min(candle.open, candle.close));
      const bodyHeight = Math.max(bodyBottom - bodyTop, 1);

      ctx.fillStyle = color;
      ctx.fillRect(x - barWidth * 0.35, bodyTop, barWidth * 0.7, bodyHeight);
    });
  }
}
```

## client/app.js

```javascript
const ws = new WebSocket(`ws://${location.host}`);
let selectedSymbol = "SAMS";
let chart = null;

ws.onopen = () => {
  console.log("WebSocket 연결");
  chart = new CandleChart("candle-chart");
};

ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);

  switch (msg.type) {
    case "stock-list":
      renderStockList(msg.stocks);
      break;
    case "tick":
      updateTicker(msg.data);
      break;
    case "watchlist":
      renderWatchlist(msg.symbols);
      break;
    case "new-candle":
      if (msg.symbol === selectedSymbol) {
        ws.send(JSON.stringify({ type: "get-candles", symbol: selectedSymbol }));
      }
      break;
    case "candle-data":
      if (chart && msg.symbol === selectedSymbol) chart.update(msg.candles);
      break;
    case "alert-triggered":
      showAlert(msg);
      break;
    case "alert-set":
      document.getElementById("alert-count").textContent = `알림 ${msg.alerts.length}건`;
      break;
  }
};

function updateTicker(data) {
  Object.entries(data).forEach(([symbol, tick]) => {
    const el = document.getElementById(`stock-${symbol}`);
    if (!el) return;
    const sign = tick.change >= 0 ? "+" : "";
    const colorClass = tick.change >= 0 ? "up" : "down";
    el.querySelector(".price").textContent = tick.price.toLocaleString();
    el.querySelector(".change").textContent = `${sign}${tick.change.toLocaleString()} (${sign}${tick.changePercent}%)`;
    el.querySelector(".change").className = `change ${colorClass}`;
    el.querySelector(".volume").textContent = `거래량: ${tick.tickVolume.toLocaleString()}`;
  });

  // 선택 종목 상세 업데이트
  const sel = data[selectedSymbol];
  if (sel) {
    document.getElementById("detail-price").textContent = sel.price.toLocaleString();
    document.getElementById("detail-high").textContent = sel.high.toLocaleString();
    document.getElementById("detail-low").textContent = sel.low.toLocaleString();
    document.getElementById("detail-vol").textContent = sel.volume.toLocaleString();
  }
}

function renderStockList(stocks) {
  document.getElementById("stock-grid").innerHTML = stocks.map((s) => `
    <div id="stock-${s.symbol}" class="stock-card" onclick="selectStock('${s.symbol}')">
      <div class="symbol">${s.symbol}</div>
      <div class="name">${s.name}</div>
      <div class="price">${s.price.toLocaleString()}</div>
      <div class="change">-</div>
      <div class="volume">거래량: ${s.volume.toLocaleString()}</div>
      <button class="btn-watch" onclick="event.stopPropagation(); toggleWatch('${s.symbol}')">★</button>
    </div>
  `).join("");
}

function renderWatchlist(symbols) {
  document.getElementById("watchlist").innerHTML = symbols
    .map((s) => `<li onclick="selectStock('${s}')">${s}</li>`)
    .join("");
}

function selectStock(symbol) {
  selectedSymbol = symbol;
  document.getElementById("selected-name").textContent = symbol;
  ws.send(JSON.stringify({ type: "get-candles", symbol }));
}

function toggleWatch(symbol) {
  ws.send(JSON.stringify({ type: "add-watchlist", symbol }));
}

function showAlert(msg) {
  const el = document.getElementById("alert-banner");
  const dir = msg.direction === "above" ? "이상 도달" : "이하 도달";
  el.textContent = `🔔 ${msg.symbol} ${msg.price.toLocaleString()}원 — 목표가 ${msg.targetPrice.toLocaleString()}원 ${dir}`;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 5000);
}

// 알림 설정
document.getElementById("btn-set-alert").addEventListener("click", () => {
  const price = parseInt(document.getElementById("alert-price").value);
  const dir = document.getElementById("alert-dir").value;
  if (price) {
    ws.send(JSON.stringify({ type: "set-alert", symbol: selectedSymbol, targetPrice: price, direction: dir }));
  }
});
```

## client/index.html

```html
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>실시간 주식 대시보드</title>
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <div id="alert-banner"></div>
  <div id="app">
    <header>
      <h1>실시간 주식 시세</h1>
      <span id="alert-count">알림 0건</span>
    </header>
    <div id="stock-grid"></div>
    <div id="detail-panel">
      <div id="detail-header">
        <h2 id="selected-name">SAMS</h2>
        <span id="detail-price">-</span>
      </div>
      <div id="detail-stats">
        <div>고가: <span id="detail-high">-</span></div>
        <div>저가: <span id="detail-low">-</span></div>
        <div>거래량: <span id="detail-vol">-</span></div>
      </div>
      <div id="chart-container"><canvas id="candle-chart"></canvas></div>
      <div id="alert-setting">
        <input id="alert-price" type="number" placeholder="목표 가격" />
        <select id="alert-dir"><option value="above">이상</option><option value="below">이하</option></select>
        <button id="btn-set-alert">알림 설정</button>
      </div>
    </div>
    <aside id="watch-panel">
      <h3>관심종목</h3>
      <ul id="watchlist"></ul>
    </aside>
  </div>
  <script src="chart.js"></script>
  <script src="app.js"></script>
</body>
</html>
```

## client/style.css

```css
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: "Pretendard", sans-serif; background: #0f0f23; color: #e0e0e0; }
#app { max-width: 1200px; margin: 0 auto; padding: 16px; }
header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
h1 { font-size: 20px; color: #e94560; }
#alert-count { font-size: 13px; color: #4fc3f7; }
#stock-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 20px; }
.stock-card { background: #16213e; padding: 14px; border-radius: 8px; cursor: pointer; position: relative; transition: transform 0.15s; }
.stock-card:hover { transform: translateY(-2px); }
.symbol { font-weight: 700; color: #e94560; font-size: 14px; }
.name { font-size: 12px; color: #aaa; margin-bottom: 6px; }
.price { font-size: 20px; font-weight: 700; }
.change { font-size: 13px; margin-top: 2px; }
.change.up { color: #e94560; } .change.down { color: #4fc3f7; }
.volume { font-size: 11px; color: #666; margin-top: 4px; }
.btn-watch { position: absolute; top: 10px; right: 10px; background: none; border: none; color: #ffd700; font-size: 18px; cursor: pointer; padding: 0; }
#detail-panel { background: #16213e; border-radius: 10px; padding: 20px; margin-bottom: 16px; }
#detail-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
#detail-header h2 { font-size: 18px; } #detail-price { font-size: 28px; font-weight: 700; }
#detail-stats { display: flex; gap: 24px; font-size: 13px; color: #aaa; margin-bottom: 14px; }
#chart-container { margin-bottom: 14px; }
canvas { width: 100%; border-radius: 6px; }
#alert-setting { display: flex; gap: 8px; align-items: center; }
#alert-setting input, #alert-setting select { padding: 8px; border: 1px solid #333; border-radius: 6px; background: #0f0f23; color: #fff; }
#alert-setting button { padding: 8px 16px; background: #e94560; color: white; border: none; border-radius: 6px; cursor: pointer; }
#watch-panel { background: #16213e; border-radius: 10px; padding: 16px; }
#watch-panel h3 { color: #e94560; margin-bottom: 8px; }
#watchlist { list-style: none; } #watchlist li { padding: 8px; cursor: pointer; border-radius: 4px; } #watchlist li:hover { background: #0f3460; }
#alert-banner { position: fixed; top: 0; left: 0; right: 0; background: #e94560; color: white; text-align: center; padding: 12px; font-weight: 600; transform: translateY(-100%); transition: transform 0.3s; z-index: 999; }
#alert-banner.show { transform: translateY(0); }
```

`npm install && npm start`로 실행하면 1초마다 모의 시세가 갱신되고, 10초마다 캔들이 생성됩니다.'''),

    # ═══ 5. Socket.IO 멀티플레이어 끝말잇기 게임 ═══
    m("Socket.IO로 멀티플레이어 끝말잇기 게임 만들어줘 전체 코드로",
'''멀티플레이어 끝말잇기 게임을 만들어 드릴게요. 단어 검증, 턴 타이머, 점수 시스템, 게임 로비, 채팅 통합을 구현합니다.

## 폴더 구조

```
word-chain/
├── server/
│   ├── index.js
│   ├── gameManager.js
│   ├── wordValidator.js
│   └── socket/
│       └── gameHandler.js
├── client/
│   ├── index.html
│   ├── app.js
│   └── style.css
├── data/
│   └── words.json
└── package.json
```

## package.json

```json
{
  "name": "word-chain",
  "version": "1.0.0",
  "scripts": {
    "start": "node server/index.js"
  },
  "dependencies": {
    "express": "^4.18.2",
    "socket.io": "^4.7.4"
  }
}
```

## data/words.json

```json
{
  "words": [
    "사과", "과일", "일출", "출구", "구름", "름빗", "기차", "차량", "양말", "말벌",
    "벌꿀", "꿀벌", "자동차", "사람", "람쥐", "쥐구멍", "멍석", "석유", "유리", "리본",
    "본문", "문제", "제비", "비행기", "기름", "기사", "사탕", "탕수육", "육지", "지구",
    "구두", "두부", "부엌", "부산", "산길", "길거리", "거미", "미소", "소나무", "무지개",
    "개미", "미역", "역사", "사자", "자유", "유학", "학교", "교실", "실내", "내일",
    "일기", "기온", "온도", "도서", "서점", "점수", "수박", "박쥐", "쥐약", "약국",
    "국가", "가방", "방문", "문화", "화분", "분수", "수영", "영화", "화산", "산소",
    "소금", "금메달", "달빛", "빛나다", "나비", "비누", "누리", "리듬", "금고", "고구마",
    "마을", "을지", "지도", "도로", "로봇", "봇물", "물고기", "기계", "계단", "단풍",
    "풍선", "선물", "물결", "결과", "과학", "학생", "생일", "일요일", "강아지", "지하철"
  ]
}
```

## server/wordValidator.js

```javascript
const fs = require("fs");
const path = require("path");

let wordSet = new Set();

function loadWords() {
  try {
    const data = JSON.parse(fs.readFileSync(path.join(__dirname, "../data/words.json"), "utf-8"));
    wordSet = new Set(data.words);
    console.log(`단어 사전 로드 완료: ${wordSet.size}개`);
  } catch (err) {
    console.error("단어 사전 로드 실패:", err.message);
  }
}

function isValidWord(word) {
  return wordSet.has(word);
}

function isValidChain(prevWord, newWord) {
  if (!prevWord) return true;
  // 끝말잇기: 이전 단어의 마지막 글자 === 새 단어의 첫 글자
  const lastChar = prevWord[prevWord.length - 1];
  const firstChar = newWord[0];
  return lastChar === firstChar;
}

function addWord(word) {
  wordSet.add(word);
}

loadWords();

module.exports = { isValidWord, isValidChain, addWord, loadWords };
```

## server/gameManager.js

```javascript
const GAME_STATES = { WAITING: "waiting", PLAYING: "playing", FINISHED: "finished" };
const TURN_TIME = 15; // 초

const lobbies = new Map();
let lobbyCounter = 0;

function createLobby(hostId, hostName) {
  const id = `lobby_${++lobbyCounter}`;
  const lobby = {
    id,
    state: GAME_STATES.WAITING,
    players: [{ id: hostId, name: hostName, score: 0, lives: 3 }],
    hostId,
    maxPlayers: 6,
    currentTurn: 0,
    lastWord: null,
    usedWords: new Set(),
    turnTimer: null,
    turnTimeLeft: TURN_TIME,
    round: 0,
    chatLog: []
  };
  lobbies.set(id, lobby);
  return lobby;
}

function joinLobby(lobbyId, playerId, playerName) {
  const lobby = lobbies.get(lobbyId);
  if (!lobby) return { error: "로비가 존재하지 않습니다." };
  if (lobby.state !== GAME_STATES.WAITING) return { error: "이미 게임이 진행 중입니다." };
  if (lobby.players.length >= lobby.maxPlayers) return { error: "인원이 가득 찼습니다." };
  if (lobby.players.find((p) => p.id === playerId)) return { error: "이미 참여 중입니다." };

  lobby.players.push({ id: playerId, name: playerName, score: 0, lives: 3 });
  return { success: true, lobby };
}

function startGame(lobbyId, requesterId) {
  const lobby = lobbies.get(lobbyId);
  if (!lobby || lobby.hostId !== requesterId) return { error: "호스트만 시작할 수 있습니다." };
  if (lobby.players.length < 2) return { error: "2명 이상 필요합니다." };

  lobby.state = GAME_STATES.PLAYING;
  lobby.currentTurn = 0;
  lobby.round = 1;
  lobby.lastWord = null;
  lobby.usedWords.clear();
  lobby.players.forEach((p) => { p.score = 0; p.lives = 3; });

  return { success: true, lobby };
}

function submitWord(lobbyId, playerId, word, validator) {
  const lobby = lobbies.get(lobbyId);
  if (!lobby || lobby.state !== GAME_STATES.PLAYING) return { error: "게임 중이 아닙니다." };

  const currentPlayer = lobby.players[lobby.currentTurn];
  if (currentPlayer.id !== playerId) return { error: "당신의 턴이 아닙니다." };

  // 중복 검사
  if (lobby.usedWords.has(word)) return { error: "이미 사용된 단어입니다.", valid: false };

  // 끝말잇기 규칙 검사
  if (!validator.isValidChain(lobby.lastWord, word)) {
    return { error: `'${lobby.lastWord}'의 마지막 글자로 시작해야 합니다.`, valid: false };
  }

  // 사전 검사 (사전에 없으면 추가하여 자유롭게 플레이 가능하게)
  if (!validator.isValidWord(word)) {
    validator.addWord(word); // 유연하게 허용
  }

  // 성공
  lobby.usedWords.add(word);
  lobby.lastWord = word;
  currentPlayer.score += word.length * 10;

  // 다음 턴
  advanceTurn(lobby);

  return { success: true, word, player: currentPlayer, lobby };
}

function timeOut(lobbyId) {
  const lobby = lobbies.get(lobbyId);
  if (!lobby || lobby.state !== GAME_STATES.PLAYING) return null;

  const currentPlayer = lobby.players[lobby.currentTurn];
  currentPlayer.lives -= 1;

  // 탈락 검사
  if (currentPlayer.lives <= 0) {
    lobby.players = lobby.players.filter((p) => p.id !== currentPlayer.id);
    if (lobby.players.length <= 1) {
      lobby.state = GAME_STATES.FINISHED;
      return { finished: true, winner: lobby.players[0] || null, lobby };
    }
    if (lobby.currentTurn >= lobby.players.length) lobby.currentTurn = 0;
  } else {
    advanceTurn(lobby);
  }

  return { timedOut: currentPlayer, lobby };
}

function advanceTurn(lobby) {
  lobby.currentTurn = (lobby.currentTurn + 1) % lobby.players.length;
  if (lobby.currentTurn === 0) lobby.round += 1;
  lobby.turnTimeLeft = TURN_TIME;
}

function getLobby(lobbyId) {
  return lobbies.get(lobbyId) || null;
}

function getAllLobbies() {
  return Array.from(lobbies.values())
    .filter((l) => l.state === GAME_STATES.WAITING)
    .map((l) => ({
      id: l.id, hostName: l.players[0]?.name, playerCount: l.players.length, maxPlayers: l.maxPlayers
    }));
}

module.exports = {
  GAME_STATES, TURN_TIME, createLobby, joinLobby, startGame,
  submitWord, timeOut, getLobby, getAllLobbies
};
```

## server/socket/gameHandler.js

```javascript
const gm = require("../gameManager");
const validator = require("../wordValidator");

const turnTimers = new Map();

function setupGameHandler(io, socket) {
  socket.on("create-lobby", ({ playerName }) => {
    const lobby = gm.createLobby(socket.id, playerName);
    socket.join(lobby.id);
    socket.lobbyId = lobby.id;
    socket.playerName = playerName;
    socket.emit("lobby-joined", lobby);
    io.emit("lobby-list", gm.getAllLobbies());
  });

  socket.on("join-lobby", ({ lobbyId, playerName }) => {
    const result = gm.joinLobby(lobbyId, socket.id, playerName);
    if (result.error) return socket.emit("error", result.error);
    socket.join(lobbyId);
    socket.lobbyId = lobbyId;
    socket.playerName = playerName;
    socket.emit("lobby-joined", result.lobby);
    io.to(lobbyId).emit("lobby-updated", result.lobby);
  });

  socket.on("start-game", () => {
    const result = gm.startGame(socket.lobbyId, socket.id);
    if (result.error) return socket.emit("error", result.error);
    io.to(socket.lobbyId).emit("game-started", result.lobby);
    startTurnTimer(io, socket.lobbyId);
  });

  socket.on("submit-word", ({ word }) => {
    const result = gm.submitWord(socket.lobbyId, socket.id, word.trim(), validator);
    if (result.error) {
      return socket.emit("word-rejected", { error: result.error, word });
    }
    clearTurnTimer(socket.lobbyId);
    io.to(socket.lobbyId).emit("word-accepted", {
      word: result.word,
      player: result.player,
      lobby: result.lobby
    });
    startTurnTimer(io, socket.lobbyId);
  });

  socket.on("game-chat", ({ message }) => {
    io.to(socket.lobbyId).emit("game-chat", {
      playerId: socket.id,
      playerName: socket.playerName,
      message,
      timestamp: Date.now()
    });
  });

  socket.on("get-lobbies", () => {
    socket.emit("lobby-list", gm.getAllLobbies());
  });

  socket.on("disconnect", () => {
    if (socket.lobbyId) {
      io.to(socket.lobbyId).emit("player-left", { playerId: socket.id, playerName: socket.playerName });
    }
  });
}

function startTurnTimer(io, lobbyId) {
  clearTurnTimer(lobbyId);
  let timeLeft = gm.TURN_TIME;

  const interval = setInterval(() => {
    timeLeft -= 1;
    io.to(lobbyId).emit("timer-tick", { timeLeft });

    if (timeLeft <= 0) {
      clearInterval(interval);
      turnTimers.delete(lobbyId);

      const result = gm.timeOut(lobbyId);
      if (!result) return;

      if (result.finished) {
        io.to(lobbyId).emit("game-finished", { winner: result.winner, lobby: result.lobby });
      } else {
        io.to(lobbyId).emit("turn-timeout", { player: result.timedOut, lobby: result.lobby });
        startTurnTimer(io, lobbyId);
      }
    }
  }, 1000);

  turnTimers.set(lobbyId, interval);
}

function clearTurnTimer(lobbyId) {
  const timer = turnTimers.get(lobbyId);
  if (timer) { clearInterval(timer); turnTimers.delete(lobbyId); }
}

module.exports = { setupGameHandler };
```

## server/index.js

```javascript
const express = require("express");
const http = require("http");
const { Server } = require("socket.io");
const { setupGameHandler } = require("./socket/gameHandler");

const app = express();
const server = http.createServer(app);
const io = new Server(server, { cors: { origin: "*" } });

app.use(express.static("client"));

io.on("connection", (socket) => {
  console.log(`연결: ${socket.id}`);
  setupGameHandler(io, socket);
});

server.listen(3000, () => console.log("끝말잇기 서버 실행: http://localhost:3000"));
```

## client/index.html

```html
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>멀티플레이어 끝말잇기</title>
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <div id="app">
    <div id="lobby-screen">
      <h1>끝말잇기</h1>
      <input id="player-name" placeholder="닉네임 입력" />
      <div class="lobby-actions">
        <button onclick="createLobby()">방 만들기</button>
        <button onclick="refreshLobbies()">새로고침</button>
      </div>
      <ul id="lobby-list"></ul>
    </div>
    <div id="game-screen" class="hidden">
      <div id="game-header">
        <div id="round-info">라운드 1</div>
        <div id="timer-bar"><div id="timer-fill"></div></div>
        <div id="timer-text">15</div>
      </div>
      <div id="word-display">
        <span id="last-word">게임 시작 대기 중...</span>
      </div>
      <div id="players-bar"></div>
      <div id="used-words"></div>
      <div id="game-content">
        <div id="game-area">
          <form id="word-form">
            <input id="word-input" placeholder="단어를 입력하세요" autocomplete="off" />
            <button type="submit">제출</button>
          </form>
          <div id="game-log"></div>
        </div>
        <div id="chat-panel">
          <h3>채팅</h3>
          <div id="chat-messages"></div>
          <form id="chat-form">
            <input id="chat-input" placeholder="채팅..." />
          </form>
        </div>
      </div>
      <button id="btn-start" class="hidden" onclick="startGame()">게임 시작</button>
    </div>
  </div>
  <script src="/socket.io/socket.io.js"></script>
  <script src="app.js"></script>
</body>
</html>
```

## client/app.js

```javascript
const socket = io();
let isHost = false;

socket.on("lobby-list", (lobbies) => {
  document.getElementById("lobby-list").innerHTML = lobbies
    .map((l) => `<li onclick="joinLobby('${l.id}')">${l.hostName}의 방 (${l.playerCount}/${l.maxPlayers})</li>`)
    .join("") || "<li>대기 중인 방이 없습니다</li>";
});

socket.on("lobby-joined", (lobby) => {
  document.getElementById("lobby-screen").classList.add("hidden");
  document.getElementById("game-screen").classList.remove("hidden");
  isHost = lobby.hostId === socket.id;
  if (isHost) document.getElementById("btn-start").classList.remove("hidden");
  updatePlayers(lobby.players);
});

socket.on("lobby-updated", (lobby) => updatePlayers(lobby.players));

socket.on("game-started", (lobby) => {
  document.getElementById("btn-start").classList.add("hidden");
  document.getElementById("last-word").textContent = "첫 단어를 입력하세요!";
  document.getElementById("word-input").focus();
  updatePlayers(lobby.players);
  highlightTurn(lobby);
});

socket.on("word-accepted", ({ word, player, lobby }) => {
  document.getElementById("last-word").textContent = word;
  appendLog(`✅ ${player.name}: ${word} (+${word.length * 10}점)`);
  updatePlayers(lobby.players);
  highlightTurn(lobby);

  const usedEl = document.getElementById("used-words");
  usedEl.innerHTML += `<span class="used-word">${word}</span>`;
});

socket.on("word-rejected", ({ error }) => {
  appendLog(`❌ ${error}`, "error");
});

socket.on("timer-tick", ({ timeLeft }) => {
  document.getElementById("timer-text").textContent = timeLeft;
  const pct = (timeLeft / 15) * 100;
  document.getElementById("timer-fill").style.width = `${pct}%`;
  document.getElementById("timer-fill").style.background = timeLeft <= 5 ? "#e94560" : "#4fc3f7";
});

socket.on("turn-timeout", ({ player, lobby }) => {
  appendLog(`⏰ ${player.name} 시간 초과! (남은 목숨: ${player.lives})`, "warn");
  updatePlayers(lobby.players);
  highlightTurn(lobby);
});

socket.on("game-finished", ({ winner }) => {
  const msg = winner ? `🏆 ${winner.name}님 승리! (${winner.score}점)` : "무승부!";
  document.getElementById("last-word").textContent = msg;
  appendLog(msg, "win");
});

socket.on("game-chat", ({ playerName, message }) => {
  const el = document.getElementById("chat-messages");
  el.innerHTML += `<div><strong>${playerName}:</strong> ${message}</div>`;
  el.scrollTop = el.scrollHeight;
});

socket.on("player-left", ({ playerName }) => appendLog(`${playerName}님이 나감`, "warn"));
socket.on("error", (msg) => appendLog(`오류: ${msg}`, "error"));

function createLobby() {
  const name = document.getElementById("player-name").value.trim() || "플레이어";
  socket.emit("create-lobby", { playerName: name });
}

function joinLobby(lobbyId) {
  const name = document.getElementById("player-name").value.trim() || "플레이어";
  socket.emit("join-lobby", { lobbyId, playerName: name });
}

function startGame() { socket.emit("start-game"); }
function refreshLobbies() { socket.emit("get-lobbies"); }

document.getElementById("word-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const input = document.getElementById("word-input");
  if (input.value.trim()) {
    socket.emit("submit-word", { word: input.value.trim() });
    input.value = "";
  }
});

document.getElementById("chat-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const input = document.getElementById("chat-input");
  if (input.value.trim()) {
    socket.emit("game-chat", { message: input.value.trim() });
    input.value = "";
  }
});

function updatePlayers(players) {
  document.getElementById("players-bar").innerHTML = players
    .map((p) => `<div class="player-badge" id="player-${p.id}">
      <span class="pname">${p.name}</span>
      <span class="pscore">${p.score}점</span>
      <span class="plives">${"♥".repeat(p.lives)}</span>
    </div>`).join("");
}

function highlightTurn(lobby) {
  document.querySelectorAll(".player-badge").forEach((el) => el.classList.remove("active-turn"));
  const current = lobby.players[lobby.currentTurn];
  if (current) {
    const el = document.getElementById(`player-${current.id}`);
    if (el) el.classList.add("active-turn");
  }
  document.getElementById("round-info").textContent = `라운드 ${lobby.round}`;
}

function appendLog(text, type = "") {
  const el = document.getElementById("game-log");
  el.innerHTML += `<div class="log-item ${type}">${text}</div>`;
  el.scrollTop = el.scrollHeight;
}

socket.emit("get-lobbies");
```

## client/style.css

```css
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: "Pretendard", sans-serif; background: #0f0f23; color: #e0e0e0; }
.hidden { display: none !important; }
#app { max-width: 960px; margin: 0 auto; padding: 20px; }
#lobby-screen { text-align: center; padding-top: 60px; }
h1 { font-size: 32px; color: #e94560; margin-bottom: 20px; }
#player-name { padding: 12px 20px; border: 2px solid #e94560; border-radius: 8px; background: #16213e; color: #fff; font-size: 16px; width: 300px; margin-bottom: 16px; }
.lobby-actions { display: flex; justify-content: center; gap: 10px; margin-bottom: 20px; }
button { padding: 10px 20px; background: #e94560; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; }
#lobby-list { list-style: none; max-width: 400px; margin: 0 auto; }
#lobby-list li { padding: 14px; background: #16213e; border-radius: 8px; margin-bottom: 8px; cursor: pointer; }
#lobby-list li:hover { background: #1a3a5c; }
#game-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
#round-info { font-weight: 700; color: #e94560; min-width: 80px; }
#timer-bar { flex: 1; height: 8px; background: #1a1a3e; border-radius: 4px; overflow: hidden; }
#timer-fill { height: 100%; background: #4fc3f7; transition: width 1s linear; width: 100%; }
#timer-text { font-size: 20px; font-weight: 700; min-width: 30px; text-align: center; }
#word-display { text-align: center; padding: 24px; background: #16213e; border-radius: 12px; margin-bottom: 16px; }
#last-word { font-size: 28px; font-weight: 700; }
#players-bar { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
.player-badge { padding: 8px 14px; background: #16213e; border-radius: 8px; border: 2px solid transparent; }
.player-badge.active-turn { border-color: #e94560; background: #1a3a5c; }
.pname { font-weight: 600; margin-right: 8px; } .pscore { color: #4fc3f7; margin-right: 8px; } .plives { color: #e94560; }
#used-words { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.used-word { padding: 4px 10px; background: #1a1a3e; border-radius: 12px; font-size: 12px; }
#game-content { display: grid; grid-template-columns: 1fr 280px; gap: 12px; }
#game-area { display: flex; flex-direction: column; }
#word-form { display: flex; gap: 8px; margin-bottom: 12px; }
#word-input { flex: 1; padding: 12px 16px; border: 2px solid #0f3460; border-radius: 8px; background: #16213e; color: #fff; font-size: 16px; }
#game-log { flex: 1; overflow-y: auto; max-height: 240px; }
.log-item { padding: 4px 0; font-size: 13px; } .log-item.error { color: #e94560; } .log-item.warn { color: #ffa726; } .log-item.win { color: #ffd700; font-weight: 700; font-size: 16px; }
#chat-panel { background: #16213e; border-radius: 8px; padding: 12px; display: flex; flex-direction: column; }
#chat-panel h3 { font-size: 14px; color: #e94560; margin-bottom: 8px; }
#chat-messages { flex: 1; overflow-y: auto; max-height: 240px; font-size: 13px; }
#chat-form input { width: 100%; padding: 8px; border: 1px solid #333; border-radius: 6px; background: #0f0f23; color: #fff; margin-top: 8px; }
#btn-start { width: 100%; margin-top: 12px; padding: 14px; font-size: 18px; }
```

`npm install && npm start` 후 여러 브라우저 탭에서 닉네임을 입력하고 방에 참여하면 끝말잇기를 즐길 수 있습니다.'''),

    # ═══ 6. WebSocket IoT 센서 데이터 실시간 모니터링 ═══
    m("WebSocket으로 IoT 센서 데이터 실시간 모니터링 만들어줘 전체 코드로",
'''IoT 센서 데이터 실시간 모니터링 시스템을 만들어 드릴게요. 센서 데이터 수집, 실시간 라인 차트, 임계값 알림, 디바이스 관리, 대시보드 레이아웃을 구현합니다.

## 폴더 구조

```
iot-monitor/
├── server/
│   ├── index.js
│   ├── deviceManager.js
│   ├── sensorSimulator.js
│   └── wsHandler.js
├── client/
│   ├── index.html
│   ├── app.js
│   ├── lineChart.js
│   └── style.css
└── package.json
```

## package.json

```json
{
  "name": "iot-monitor",
  "version": "1.0.0",
  "scripts": {
    "start": "node server/index.js"
  },
  "dependencies": {
    "express": "^4.18.2",
    "ws": "^8.16.0"
  }
}
```

## server/deviceManager.js

```javascript
const devices = new Map();

function registerDevice(deviceId, config) {
  const device = {
    id: deviceId,
    name: config.name || deviceId,
    type: config.type || "generic",
    location: config.location || "미지정",
    sensors: config.sensors || [],
    status: "online",
    lastSeen: Date.now(),
    thresholds: config.thresholds || {},
    history: {}
  };

  device.sensors.forEach((s) => {
    device.history[s.id] = [];
  });

  devices.set(deviceId, device);
  return device;
}

function ingestData(deviceId, sensorId, value) {
  const device = devices.get(deviceId);
  if (!device) return null;

  device.lastSeen = Date.now();
  device.status = "online";

  const entry = { value, timestamp: Date.now() };

  if (!device.history[sensorId]) device.history[sensorId] = [];
  device.history[sensorId].push(entry);
  if (device.history[sensorId].length > 200) device.history[sensorId].shift();

  // 임계값 검사
  const alerts = [];
  const threshold = device.thresholds[sensorId];
  if (threshold) {
    if (threshold.max !== undefined && value > threshold.max) {
      alerts.push({ deviceId, sensorId, type: "high", value, limit: threshold.max, message: `${device.name} ${sensorId}: ${value} > ${threshold.max} (상한 초과)` });
    }
    if (threshold.min !== undefined && value < threshold.min) {
      alerts.push({ deviceId, sensorId, type: "low", value, limit: threshold.min, message: `${device.name} ${sensorId}: ${value} < ${threshold.min} (하한 미달)` });
    }
  }

  return { entry, alerts };
}

function setThreshold(deviceId, sensorId, min, max) {
  const device = devices.get(deviceId);
  if (!device) return null;
  device.thresholds[sensorId] = { min, max };
  return device.thresholds;
}

function getDevice(deviceId) {
  return devices.get(deviceId) || null;
}

function getAllDevices() {
  return Array.from(devices.values()).map((d) => ({
    id: d.id, name: d.name, type: d.type, location: d.location,
    status: d.status, sensors: d.sensors, lastSeen: d.lastSeen
  }));
}

function getHistory(deviceId, sensorId, limit = 100) {
  const device = devices.get(deviceId);
  if (!device || !device.history[sensorId]) return [];
  return device.history[sensorId].slice(-limit);
}

function checkOffline() {
  const now = Date.now();
  devices.forEach((device) => {
    if (now - device.lastSeen > 30000) {
      device.status = "offline";
    }
  });
}

module.exports = { registerDevice, ingestData, setThreshold, getDevice, getAllDevices, getHistory, checkOffline };
```

## server/sensorSimulator.js

```javascript
const dm = require("./deviceManager");

// 모의 디바이스 등록
function initDevices() {
  dm.registerDevice("FARM-01", {
    name: "스마트팜 센서 A",
    type: "agriculture",
    location: "온실 1동",
    sensors: [
      { id: "temp", name: "온도", unit: "°C" },
      { id: "humidity", name: "습도", unit: "%" },
      { id: "soil", name: "토양수분", unit: "%" }
    ],
    thresholds: {
      temp: { min: 15, max: 35 },
      humidity: { min: 40, max: 90 },
      soil: { min: 20, max: 80 }
    }
  });

  dm.registerDevice("FACTORY-01", {
    name: "공장 라인 센서",
    type: "industrial",
    location: "제조동 B",
    sensors: [
      { id: "temp", name: "온도", unit: "°C" },
      { id: "vibration", name: "진동", unit: "mm/s" },
      { id: "power", name: "전력", unit: "kW" }
    ],
    thresholds: {
      temp: { min: 10, max: 60 },
      vibration: { min: 0, max: 15 },
      power: { min: 0, max: 500 }
    }
  });

  dm.registerDevice("OFFICE-01", {
    name: "사무실 환경 센서",
    type: "environment",
    location: "본사 3층",
    sensors: [
      { id: "temp", name: "온도", unit: "°C" },
      { id: "co2", name: "CO2", unit: "ppm" },
      { id: "noise", name: "소음", unit: "dB" }
    ],
    thresholds: {
      temp: { min: 18, max: 28 },
      co2: { min: 0, max: 1000 },
      noise: { min: 0, max: 70 }
    }
  });

  dm.registerDevice("WEATHER-01", {
    name: "기상 관측 센서",
    type: "weather",
    location: "옥상",
    sensors: [
      { id: "temp", name: "온도", unit: "°C" },
      { id: "pressure", name: "기압", unit: "hPa" },
      { id: "wind", name: "풍속", unit: "m/s" }
    ],
    thresholds: {
      wind: { min: 0, max: 20 }
    }
  });
}

// 센서별 기본값과 변동 범위
const sensorProfiles = {
  temp: { base: 24, variance: 3 },
  humidity: { base: 60, variance: 10 },
  soil: { base: 50, variance: 8 },
  vibration: { base: 5, variance: 4 },
  power: { base: 250, variance: 80 },
  co2: { base: 500, variance: 150 },
  noise: { base: 45, variance: 12 },
  pressure: { base: 1013, variance: 5 },
  wind: { base: 5, variance: 6 }
};

function generateReading(sensorId) {
  const profile = sensorProfiles[sensorId] || { base: 50, variance: 10 };
  const value = profile.base + (Math.random() - 0.5) * 2 * profile.variance;
  return Math.round(value * 10) / 10;
}

function simulateTick() {
  const allAlerts = [];

  dm.getAllDevices().forEach((device) => {
    device.sensors.forEach((sensor) => {
      const value = generateReading(sensor.id);
      const result = dm.ingestData(device.id, sensor.id, value);
      if (result && result.alerts.length > 0) {
        allAlerts.push(...result.alerts);
      }
    });
  });

  return allAlerts;
}

module.exports = { initDevices, simulateTick };
```

## server/wsHandler.js

```javascript
const dm = require("./deviceManager");

const clients = new Set();

function broadcast(data) {
  const msg = JSON.stringify(data);
  clients.forEach((ws) => { if (ws.readyState === 1) ws.send(msg); });
}

function send(ws, data) {
  if (ws.readyState === 1) ws.send(JSON.stringify(data));
}

function handleConnection(ws) {
  clients.add(ws);

  send(ws, { type: "device-list", devices: dm.getAllDevices() });

  ws.on("message", (raw) => {
    let msg;
    try { msg = JSON.parse(raw); } catch { return; }

    switch (msg.type) {
      case "get-history":
        send(ws, {
          type: "sensor-history",
          deviceId: msg.deviceId,
          sensorId: msg.sensorId,
          data: dm.getHistory(msg.deviceId, msg.sensorId, msg.limit || 100)
        });
        break;

      case "set-threshold":
        dm.setThreshold(msg.deviceId, msg.sensorId, msg.min, msg.max);
        send(ws, { type: "threshold-updated", deviceId: msg.deviceId, sensorId: msg.sensorId });
        break;

      case "get-devices":
        send(ws, { type: "device-list", devices: dm.getAllDevices() });
        break;
    }
  });

  ws.on("close", () => clients.delete(ws));
}

module.exports = { handleConnection, broadcast };
```

## server/index.js

```javascript
const express = require("express");
const http = require("http");
const { WebSocketServer } = require("ws");
const { initDevices, simulateTick } = require("./sensorSimulator");
const { handleConnection, broadcast } = require("./wsHandler");
const dm = require("./deviceManager");

const app = express();
const server = http.createServer(app);
const wss = new WebSocketServer({ server });

app.use(express.static("client"));

initDevices();
console.log(`디바이스 ${dm.getAllDevices().length}개 초기화 완료`);

wss.on("connection", (ws) => handleConnection(ws));

// 2초마다 센서 데이터 생성 및 브로드캐스트
setInterval(() => {
  const alerts = simulateTick();
  const devices = dm.getAllDevices();

  const latestData = {};
  devices.forEach((device) => {
    latestData[device.id] = {};
    device.sensors.forEach((sensor) => {
      const history = dm.getHistory(device.id, sensor.id, 1);
      latestData[device.id][sensor.id] = history.length > 0 ? history[history.length - 1] : null;
    });
  });

  broadcast({ type: "sensor-tick", data: latestData, timestamp: Date.now() });

  if (alerts.length > 0) {
    broadcast({ type: "alerts", alerts });
  }
}, 2000);

// 30초마다 오프라인 체크
setInterval(() => dm.checkOffline(), 30000);

server.listen(3000, () => console.log("IoT 모니터링 서버 실행: http://localhost:3000"));
```

## client/lineChart.js

```javascript
class LineChart {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext("2d");
    this.datasets = {};
    this.colors = ["#e94560", "#4fc3f7", "#66bb6a", "#ffa726", "#ab47bc"];
    this.resize();
    window.addEventListener("resize", () => this.resize());
  }

  resize() {
    if (!this.canvas) return;
    this.canvas.width = this.canvas.parentElement.clientWidth;
    this.canvas.height = 220;
    this.draw();
  }

  addPoint(label, value) {
    if (!this.datasets[label]) {
      this.datasets[label] = { points: [], colorIdx: Object.keys(this.datasets).length };
    }
    this.datasets[label].points.push(value);
    if (this.datasets[label].points.length > 60) this.datasets[label].points.shift();
    this.draw();
  }

  setData(label, points) {
    if (!this.datasets[label]) {
      this.datasets[label] = { points: [], colorIdx: Object.keys(this.datasets).length };
    }
    this.datasets[label].points = points.slice(-60);
    this.draw();
  }

  draw() {
    const { ctx, canvas } = this;
    if (!ctx) return;
    const w = canvas.width;
    const h = canvas.height;
    const pad = 40;

    ctx.fillStyle = "#12122b";
    ctx.fillRect(0, 0, w, h);

    const allPoints = Object.values(this.datasets).flatMap((d) => d.points);
    if (allPoints.length === 0) return;

    const maxVal = Math.max(...allPoints) * 1.1;
    const minVal = Math.min(...allPoints) * 0.9;
    const range = maxVal - minVal || 1;

    // 그리드
    ctx.strokeStyle = "#1a1a3e";
    ctx.lineWidth = 0.5;
    for (let i = 0; i <= 4; i++) {
      const y = pad + (i / 4) * (h - pad * 2);
      ctx.beginPath(); ctx.moveTo(pad, y); ctx.lineTo(w - 10, y); ctx.stroke();
      ctx.fillStyle = "#666";
      ctx.font = "10px sans-serif";
      const val = maxVal - (i / 4) * range;
      ctx.fillText(val.toFixed(1), 2, y + 3);
    }

    // 데이터 라인
    Object.entries(this.datasets).forEach(([label, dataset]) => {
      const color = this.colors[dataset.colorIdx % this.colors.length];
      const pts = dataset.points;
      if (pts.length < 2) return;

      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.beginPath();

      pts.forEach((val, i) => {
        const x = pad + (i / (pts.length - 1)) * (w - pad - 10);
        const y = pad + ((maxVal - val) / range) * (h - pad * 2);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();

      // 레이블
      ctx.fillStyle = color;
      ctx.font = "11px sans-serif";
      ctx.fillText(label, w - pad - label.length * 7, pad - 5 + dataset.colorIdx * 14);
    });
  }
}
```

## client/app.js

```javascript
const ws = new WebSocket(`ws://${location.host}`);
const charts = {};
let selectedDevice = null;

ws.onopen = () => console.log("WebSocket 연결");

ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);

  switch (msg.type) {
    case "device-list":
      renderDeviceList(msg.devices);
      if (!selectedDevice && msg.devices.length > 0) selectDevice(msg.devices[0].id);
      break;

    case "sensor-tick":
      updateDashboard(msg.data);
      break;

    case "alerts":
      msg.alerts.forEach(showAlert);
      break;

    case "sensor-history":
      if (charts[msg.deviceId]) {
        charts[msg.deviceId].setData(msg.sensorId, msg.data.map((d) => d.value));
      }
      break;

    case "threshold-updated":
      appendLog(`임계값 업데이트: ${msg.deviceId} / ${msg.sensorId}`);
      break;
  }
};

function renderDeviceList(devices) {
  document.getElementById("device-list").innerHTML = devices.map((d) => `
    <div class="device-item ${d.status}" onclick="selectDevice('${d.id}')">
      <span class="status-dot"></span>
      <div>
        <div class="dname">${d.name}</div>
        <div class="dloc">${d.location} | ${d.type}</div>
      </div>
    </div>
  `).join("");
}

function selectDevice(deviceId) {
  selectedDevice = deviceId;
  document.querySelectorAll(".device-item").forEach((el) => el.classList.remove("selected"));

  const chartArea = document.getElementById("chart-area");
  chartArea.innerHTML = `<canvas id="chart-${deviceId}"></canvas>`;

  charts[deviceId] = new LineChart(`chart-${deviceId}`);

  ws.send(JSON.stringify({ type: "get-devices" }));

  // 전체 센서 히스토리 요청 (디바이스 정보를 다시 받은 후)
  setTimeout(() => {
    const devices = document.querySelectorAll(".device-item");
    devices.forEach((el) => {
      if (el.textContent.includes(deviceId)) el.classList.add("selected");
    });
  }, 100);
}

function updateDashboard(data) {
  const sensorGrid = document.getElementById("sensor-values");
  let html = "";

  Object.entries(data).forEach(([deviceId, sensors]) => {
    Object.entries(sensors).forEach(([sensorId, entry]) => {
      if (!entry) return;

      if (deviceId === selectedDevice && charts[deviceId]) {
        charts[deviceId].addPoint(sensorId, entry.value);
      }

      if (deviceId === selectedDevice) {
        html += `<div class="sensor-card">
          <div class="sensor-name">${sensorId}</div>
          <div class="sensor-value">${entry.value}</div>
        </div>`;
      }
    });
  });

  if (html) sensorGrid.innerHTML = html;
}

function showAlert(alert) {
  const el = document.getElementById("alert-list");
  const time = new Date().toLocaleTimeString("ko-KR");
  const alertClass = alert.type === "high" ? "alert-high" : "alert-low";
  el.innerHTML = `<div class="alert-item ${alertClass}">
    <span class="alert-time">${time}</span> ${alert.message}
  </div>` + el.innerHTML;

  // 최대 20개 유지
  const items = el.querySelectorAll(".alert-item");
  if (items.length > 20) items[items.length - 1].remove();
}

function appendLog(text) {
  const el = document.getElementById("alert-list");
  el.innerHTML = `<div class="alert-item">${text}</div>` + el.innerHTML;
}

// 임계값 설정
document.getElementById("btn-threshold").addEventListener("click", () => {
  const sensorId = document.getElementById("th-sensor").value.trim();
  const min = parseFloat(document.getElementById("th-min").value);
  const max = parseFloat(document.getElementById("th-max").value);
  if (selectedDevice && sensorId) {
    ws.send(JSON.stringify({ type: "set-threshold", deviceId: selectedDevice, sensorId, min, max }));
  }
});
```

## client/index.html

```html
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>IoT 센서 모니터링</title>
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <div id="app">
    <header>
      <h1>IoT 센서 모니터링</h1>
    </header>
    <div id="dashboard">
      <aside id="device-panel">
        <h3>디바이스 목록</h3>
        <div id="device-list"></div>
        <div id="threshold-form">
          <h4>임계값 설정</h4>
          <input id="th-sensor" placeholder="센서 ID (예: temp)" />
          <input id="th-min" type="number" placeholder="최소값" />
          <input id="th-max" type="number" placeholder="최대값" />
          <button id="btn-threshold">설정</button>
        </div>
      </aside>
      <main id="main-panel">
        <div id="sensor-values"></div>
        <div id="chart-area"></div>
      </main>
      <aside id="alert-panel">
        <h3>알림 로그</h3>
        <div id="alert-list"></div>
      </aside>
    </div>
  </div>
  <script src="lineChart.js"></script>
  <script src="app.js"></script>
</body>
</html>
```

## client/style.css

```css
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: "Pretendard", sans-serif; background: #0a0a1a; color: #e0e0e0; }
#app { height: 100vh; display: flex; flex-direction: column; }
header { padding: 12px 20px; background: #12122b; border-bottom: 1px solid #1a1a3e; }
h1 { font-size: 18px; color: #4fc3f7; }
#dashboard { flex: 1; display: grid; grid-template-columns: 240px 1fr 280px; overflow: hidden; }
aside { padding: 16px; overflow-y: auto; }
#device-panel { background: #12122b; border-right: 1px solid #1a1a3e; }
#device-panel h3, #alert-panel h3 { color: #e94560; margin-bottom: 12px; font-size: 14px; }
.device-item { display: flex; align-items: center; gap: 10px; padding: 12px; border-radius: 8px; cursor: pointer; margin-bottom: 6px; background: #1a1a3e; }
.device-item:hover, .device-item.selected { background: #0f3460; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; }
.device-item.online .status-dot { background: #66bb6a; }
.device-item.offline .status-dot { background: #e94560; }
.dname { font-size: 13px; font-weight: 600; }
.dloc { font-size: 11px; color: #888; }
#threshold-form { margin-top: 20px; }
#threshold-form h4 { color: #e94560; margin-bottom: 8px; font-size: 13px; }
#threshold-form input { width: 100%; padding: 6px 8px; margin-bottom: 6px; border: 1px solid #333; border-radius: 4px; background: #0a0a1a; color: #fff; font-size: 12px; }
button { padding: 8px 14px; background: #e94560; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 12px; width: 100%; }
#main-panel { padding: 16px; overflow-y: auto; }
#sensor-values { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 10px; margin-bottom: 16px; }
.sensor-card { background: #16213e; padding: 14px; border-radius: 8px; text-align: center; }
.sensor-name { font-size: 12px; color: #aaa; margin-bottom: 4px; }
.sensor-value { font-size: 24px; font-weight: 700; color: #4fc3f7; }
#chart-area { background: #12122b; border-radius: 10px; padding: 12px; }
canvas { width: 100%; border-radius: 6px; }
#alert-panel { background: #12122b; border-left: 1px solid #1a1a3e; }
.alert-item { padding: 8px 10px; font-size: 12px; border-radius: 6px; margin-bottom: 4px; background: #1a1a3e; line-height: 1.4; }
.alert-item.alert-high { background: #3e1a1a; color: #e94560; }
.alert-item.alert-low { background: #1a2e3e; color: #4fc3f7; }
.alert-time { color: #666; }
```

`npm install && npm start`로 실행하면 4개 모의 디바이스의 센서 데이터가 2초마다 갱신되며, 임계값 초과 시 알림이 표시됩니다.'''),
]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/mega_chat.jsonl")
    args = parser.parse_args()
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    logger.info(f"채팅 추가: {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
