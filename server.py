import sys
import os
import random
import copy
import json

from flask import Flask, render_template_string
from flask_socketio import SocketIO, emit, join_room

# 強制加入當前路徑以防止找不到 questions.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from questions import QUESTION, QUESTION_PICTURE, QUESTION_VIDEO
except Exception as e:
    print(f"⚠️ 讀取 questions.py 失敗，使用預設範例題: {e}")
    QUESTION = [{"question": "Rami 在隊內擔任什麼定位？", "options": ["主唱", "主舞", "門面"], "answer": "主唱"}]
    QUESTION_PICTURE, QUESTION_VIDEO = [], []

app = Flask(__name__)
app.config['SECRET_KEY'] = 'babymonster_quiz_2026'

# 改為 let SocketIO 自動選擇或綁定 eventlet
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

ROOMS = {}
GLOBAL_LEADERBOARD = []
LEADERBOARD_FILE = "leaderboard_local.json"

if os.path.exists(LEADERBOARD_FILE):
    try:
        with open(LEADERBOARD_FILE, "r", encoding="utf-8") as f:
            GLOBAL_LEADERBOARD = json.load(f)
            print(f"✅ 成功載入 {len(GLOBAL_LEADERBOARD)} 筆歷史排行榜紀錄！")
    except Exception as e:
        print(f"⚠️ 讀取排行榜失敗: {e}")

HTML_TEMPLATE_RAMI = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>🎂 1017 HAPPY RAMI DAY | 生日問答遊戲</title>
    <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', Arial, sans-serif; }
        
        body {
            position: relative;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
            overflow-x: hidden;
            background-color: #0f172a;
        }

        .bg-single {
            position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
            background-image: url('/static/rami11.jpg');
            background-size: cover; background-position: center; background-repeat: no-repeat; z-index: -2;
        }

        .bg-overlay {
            position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
            background: rgba(15, 10, 30, 0.65); z-index: -1;
        }

        @media (max-width: 768px) {
            body { padding: 10px; padding-top: 20px; }
            .bg-single { background-image: url('/static/rami4.jpg'); }
            .container { width: 95% !important; padding: 20px 15px !important; }
            .title { font-size: 20px !important; }
        }

        .container {
            width: 90%; max-width: 420px;
            background: rgba(24, 15, 46, 0.78); backdrop-filter: blur(16px);
            border: 1px solid rgba(192, 132, 252, 0.5); border-radius: 20px;
            padding: 25px; box-shadow: 0 10px 40px rgba(0, 0, 0, 0.7); z-index: 1;
            margin: auto; text-align: center;
        }

        .title {
            text-align: center; font-size: 22px; font-weight: 900;
            color: #c084fc; text-shadow: 0 0 15px rgba(192, 132, 252, 0.8); margin-bottom: 20px; line-height: 1.3;
        }

        .form-group { margin-bottom: 14px; text-align: left; }
        label { display: block; font-size: 13px; color: #ffffff; font-weight: bold; margin-bottom: 6px; }
        input {
            width: 100%; padding: 11px 14px; border-radius: 10px;
            border: 1px solid rgba(192, 132, 252, 0.4); background: rgba(15, 23, 42, 0.6);
            color: #fff; font-size: 14px; outline: none;
        }

        .btn {
            width: 100%; padding: 13px; background: linear-gradient(135deg, #a855f7, #ec4899);
            border: none; border-radius: 10px; color: #fff; font-size: 15px; font-weight: bold;
            cursor: pointer; margin-top: 10px; box-shadow: 0 4px 15px rgba(168, 85, 247, 0.4);
        }

        .hidden { display: none !important; }

        .quiz-media {
            width: 100%; max-height: 200px; border-radius: 12px; margin: 10px 0; object-fit: cover; border: 1px solid rgba(192, 132, 252, 0.3);
        }

        .quiz-text {
            font-weight: bold; font-size: 16px; color: #ffffff !important;
            text-shadow: 0 0 8px rgba(255, 255, 255, 0.4); margin: 15px 0; line-height: 1.4; word-break: break-word;
        }

        .quiz-option {
            width: 100%; padding: 12px; margin-top: 10px;
            background: rgba(255, 255, 255, 0.1); border: 1px solid rgba(192, 132, 252, 0.4);
            border-radius: 10px; color: #fff; font-size: 14px; font-weight: bold; cursor: pointer; transition: 0.2s;
        }

        .quiz-option:disabled {
            background: rgba(255, 255, 255, 0.05) !important;
            border-color: rgba(255, 255, 255, 0.15) !important;
            color: #64748b !important;
            cursor: not-allowed;
            opacity: 0.6;
        }

        .quiz-option.correct { background: #10b981 !important; border-color: #10b981 !important; color: #fff !important; opacity: 1; }
        .quiz-option.wrong { background: #ef4444 !important; border-color: #ef4444 !important; color: #fff !important; opacity: 1; }

        .timer-bar {
            height: 6px; background: #c084fc; border-radius: 3px; margin: 12px 0; transition: width 0.1s linear;
        }

        .leaderboard-table {
            width: 100%; border-collapse: collapse; font-size: 13px; color: #fff; text-align: center; margin-top: 10px;
        }
        .leaderboard-table th, .leaderboard-table td {
            padding: 8px 4px; border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }
        .leaderboard-table th { color: #c084fc; background: rgba(168, 85, 247, 0.2); }
    </style>
</head>
<body>
    <div class="bg-single"></div>
    <div class="bg-overlay"></div>

    <div class="container">
        <h1 class="title">🎂 1017 HAPPY RAMI DAY<br><span style="font-size:15px; color:#e9d5ff;">生咖問答測試版</span></h1>

        <div id="setup-view">
            <div class="form-group">
                <label>你的暱稱</label>
                <input type="text" id="username" placeholder="請輸入暱稱">
            </div>
            <button class="btn" onclick="joinGame()">🎮 進入遊戲</button>
            <button class="btn" onclick="openLeaderboardModal()" style="background: rgba(255,255,255,0.15); margin-top: 8px;">🏆 應援排行榜</button>
        </div>

        <div id="lobby-view" class="hidden">
            <h3 style="color:#c084fc;">🎂 準備挑戰</h3>
            <div id="player-list" style="margin: 15px 0;"></div>
            <button class="btn" onclick="startGame()">🚀 開始答題</button>
        </div>

        <div id="game-view" class="hidden">
            <div id="quiz-box"></div>
        </div>
    </div>

    <div id="leaderboard-modal" class="modal-overlay hidden" style="position:fixed; top:0; left:0; width:100vw; height:100vh; background:rgba(0,0,0,0.8); display:flex; justify-content:center; align-items:center; z-index:999;">
        <div style="background:#1e1b4b; border:1px solid #c084fc; padding:20px; border-radius:16px; width:90%; max-width:380px;">
            <h3 style="color:#c084fc; margin-bottom:10px;">🏆 應援排行榜 TOP 30</h3>
            <div style="max-height:220px; overflow-y:auto;">
                <table class="leaderboard-table">
                    <thead><tr><th>名次</th><th>名稱</th><th>答對</th><th>分數</th></tr></thead>
                    <tbody id="leaderboard-body"></tbody>
                </table>
            </div>
            <button class="btn" onclick="closeLeaderboardModal()" style="margin-top:15px;">關閉</button>
        </div>
    </div>

<script>
    const socket = io();
    let myName = "", myRoom = "", timerInterval = null, timeLeft = 10, hasAnswered = false;

    function getRamiTitle(correct) {
        if (correct >= 11) return "👑 Rami 首席靈魂音霸";
        if (correct >= 8) return "💎 資深拉米葵";
        if (correct >= 6) return "✨ 核心拉米控";
        return "🌱 預備拉米粉";
    }

    function openLeaderboardModal() {
        socket.emit('get_leaderboard');
        document.getElementById('leaderboard-modal').classList.remove('hidden');
    }
    function closeLeaderboardModal() { document.getElementById('leaderboard-modal').classList.add('hidden'); }

    socket.on('update_leaderboard', (data) => {
        let html = "";
        if (data.leaderboard && data.leaderboard.length > 0) {
            data.leaderboard.forEach((p, index) => {
                html += `<tr><td>${index + 1}</td><td><b>${p.name}</b></td><td>${p.correct_count || 0} 題</td><td style="color:#c084fc; font-weight:bold;">${p.score}</td></tr>`;
            });
        } else { html = "<tr><td colspan='4'>暫無紀錄</td></tr>"; }
        document.getElementById('leaderboard-body').innerHTML = html;
    });

    function joinGame() {
        myName = document.getElementById('username').value.trim();
        if (!myName) return alert("請填寫暱稱！");
        socket.emit('join_room', { name: myName, bias: "Rami" });
    }

    socket.on('room_assigned', (data) => {
        myRoom = data.room;
        document.getElementById('setup-view').classList.add('hidden');
        document.getElementById('lobby-view').classList.remove('hidden');
        document.getElementById('player-list').innerHTML = `<div style="background:rgba(255,255,255,0.1); padding:10px; border-radius:8px;">👤 玩家：<b>${myName}</b></div>`;
    });

    function startGame() { socket.emit('start_game', { room: myRoom }); }

    socket.on('new_question', (data) => {
        document.getElementById('lobby-view').classList.add('hidden');
        document.getElementById('game-view').classList.remove('hidden');
        hasAnswered = false;
        clearInterval(timerInterval);

        let q = data.question;
        let html = `
            <div style="display:flex; justify-content:space-between; color:#e9d5ff; font-weight:bold; font-size:13px;">
                <span>第 ${data.index + 1} / ${data.total} 題</span>
                <span id="timer-text">⏱️ 10 秒</span>
            </div>
            <div class="timer-bar" id="timer-bar" style="width:100%;"></div>
        `;

        if (q.image_url) {
            html += `<img src="${q.image_url}" class="quiz-media" alt="題目圖片">`;
        }
        
        if (q.video_url) {
            const isMuted = q.muted ? "muted" : "";
            html += `<video id="quiz-video" src="${q.video_url}" class="quiz-media" autoplay ${isMuted} playsinline onended="enableVideoOptions()"></video>`;
        }

        html += `<p class="quiz-text">${q.question}</p>`;

        const isVideo = !!q.video_url;
        if (q.options) {
            q.options.forEach(opt => {
                const disabledAttr = isVideo ? "disabled" : "";
                html += `<button class="quiz-option" ${disabledAttr} onclick="clickAnswer(this, '${opt}', '${q.answer}')">${opt}</button>`;
            });
        }
        
        document.getElementById('quiz-box').innerHTML = html;

        // 💡 邏輯判斷：影片題等播完；文字題與圖片題皆統一延遲 1 秒倒數
        if (q.video_url) {
            document.getElementById('timer-text').innerText = "🎬 觀看影片中...";
        } else {
            document.getElementById('timer-text').innerText = "⏱️ 準備計時...";
            setTimeout(() => { startTimer(); }, 1000);
        }
    });

    function enableVideoOptions() {
        document.querySelectorAll('.quiz-option').forEach(b => b.disabled = false);
        startTimer();
    }

    function startTimer() {
        timeLeft = 10;
        clearInterval(timerInterval);
        timerInterval = setInterval(() => {
            timeLeft -= 0.1;
            if (timeLeft <= 0) {
                clearInterval(timerInterval);
                if (!hasAnswered) timeOutAnswer();
            }
            document.getElementById('timer-text').innerText = `⏱️ ${Math.ceil(timeLeft)} 秒`;
            document.getElementById('timer-bar').style.width = `${(timeLeft / 10) * 100}%`;
        }, 100);
    }

    function clickAnswer(btn, selected, correct) {
        if (hasAnswered) return;
        hasAnswered = true;
        clearInterval(timerInterval);
        document.querySelectorAll('.quiz-option').forEach(b => b.disabled = true);
        const isCorrect = (selected === correct);
        btn.classList.add(isCorrect ? 'correct' : 'wrong');
        setTimeout(() => {
            socket.emit('submit_answer', { room: myRoom, name: myName, is_correct: isCorrect, time_left: timeLeft });
        }, 1000);
    }

    function timeOutAnswer() {
        hasAnswered = true;
        document.querySelectorAll('.quiz-option').forEach(b => b.disabled = true);
        setTimeout(() => {
            socket.emit('submit_answer', { room: myRoom, name: myName, is_correct: false, time_left: 0 });
        }, 1000);
    }

    socket.on('game_over', (data) => {
        clearInterval(timerInterval);
        let myInfo = data.my_result ? data.my_result[0] : null;
        let correct = myInfo ? (myInfo.correct_count || 0) : 0;
        let score = myInfo ? (myInfo.score || 0) : 0;
        
        let html = `
            <h3 style="color:#c084fc; margin-bottom:10px;">🎉 挑戰結束</h3>
            <p style="margin:10px 0; font-size:15px;">稱號：<b style="color:#e9d5ff;">${getRamiTitle(correct)}</b></p>
            <p style="font-size:14px; color:#cbd5e1;">答對：<b>${correct}</b> 題 | 得分：<b style="color:#c084fc;">${score}</b> 分</p>
            <button class="btn" onclick="location.reload()" style="margin-top:15px;">🔄 再次挑戰</button>
        `;
        document.getElementById('quiz-box').innerHTML = html;
    });
</script>
</body>
</html>
"""

@app.route('/')
@app.route('/rami-birthday')
def rami_birthday():
    return render_template_string(HTML_TEMPLATE_RAMI)

@socketio.on('join_room')
def handle_join(data):
    name = data.get('name', '').strip()
    room = f"user_{name}"
    join_room(room)
    if room not in ROOMS or ROOMS[room].get("status") == "FINISHED":
        ROOMS[room] = {"players": [], "status": "LOBBY", "selected_questions": [], "current_q": 0}
    r = ROOMS[room]
    player = next((p for p in r['players'] if p['name'] == name), None)
    if not player:
        r['players'].append({"name": name, "bias": "Rami", "score": 0, "correct_count": 0})
    emit('room_assigned', {"room": room, "players": r['players']}, room=room)

@socketio.on('start_game')
def handle_start(data):
    room = data.get('room')
    if room and room in ROOMS:
        r = ROOMS[room]
        r['status'] = "PLAYING"
        r['current_q'] = 0
        for p in r['players']: p['score'] = 0; p['correct_count'] = 0
        
        selected_raw = copy.deepcopy(QUESTION) + copy.deepcopy(QUESTION_PICTURE) + copy.deepcopy(QUESTION_VIDEO)
        
        for q in selected_raw:
            q['base_score'] = 100
            if 'options' in q and isinstance(q['options'], list):
                random.shuffle(q['options'])
                
        r['selected_questions'] = selected_raw
        send_question(room)

def send_question(room):
    r = ROOMS[room]
    q_idx = r['current_q']
    if q_idx < len(r['selected_questions']):
        emit('new_question', {"question": r['selected_questions'][q_idx], "index": q_idx, "total": len(r['selected_questions'])}, room=room)
    else:
        r['status'] = "FINISHED"
        for p in r['players']: GLOBAL_LEADERBOARD.append(copy.deepcopy(p))
        try:
            with open(LEADERBOARD_FILE, "w", encoding="utf-8") as f:
                json.dump(GLOBAL_LEADERBOARD, f, ensure_ascii=False, indent=2)
        except Exception as e: print(f"⚠️ 儲存失敗: {e}")
        
        sorted_global = sorted(GLOBAL_LEADERBOARD, key=lambda x: x['score'], reverse=True)
        emit('game_over', {"leaderboard": sorted_global[:30], "my_result": r['players']}, room=room)

@socketio.on('submit_answer')
def handle_answer(data):
    room = data.get('room')
    name = data.get('name')
    is_correct = data.get('is_correct', False)
    time_left = data.get('time_left', 0)
    
    if room in ROOMS:
        r = ROOMS[room]
        for p in r['players']:
            if p['name'] == name and is_correct:
                p['score'] += 100 + int(time_left * 10)
                p['correct_count'] = p.get('correct_count', 0) + 1
        r['current_q'] += 1
        send_question(room)

@socketio.on('get_leaderboard')
def handle_get_leaderboard():
    sorted_global = sorted(GLOBAL_LEADERBOARD, key=lambda x: x['score'], reverse=True)
    emit('update_leaderboard', {"leaderboard": sorted_global[:30]})

if __name__ == '__main__':
    print("🚀 Rami 生日特別版伺服器啟動中...")
    print("👉 請開啟網址: http://127.0.0.1:5000")
    socketio.run(app, host='127.0.0.1', port=5000, debug=False, allow_unsafe_werkzeug=True)