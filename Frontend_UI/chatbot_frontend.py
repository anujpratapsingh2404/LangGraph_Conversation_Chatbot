import streamlit as st
import requests
import os
import json
import re
import time
from datetime import datetime
from typing import List, Dict, Any


API_BASE = "http://127.0.0.1:8080"  
CHAT_HISTORY_DIR = "data/uploaded_files"
os.makedirs(CHAT_HISTORY_DIR, exist_ok=True)


import html

def escape_html(text: str) -> str:
    """Escape HTML characters in message text for safe rendering."""
    if not isinstance(text, str):
        text = str(text)
    return html.escape(text)


# -----------------------
# Utilities
# -----------------------
def safe_title(title: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", title).strip("_")[:40] or "untitled"

def local_chat_filename(title: str, thread_id: str) -> str:
    return f"history_{safe_title(title)}_{thread_id}.json"

def save_local_chat(title: str, messages: List[Dict[str, str]], thread_id: str) -> str:
    filename = local_chat_filename(title, thread_id)
    path = os.path.join(CHAT_HISTORY_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"title": title, "thread_id": thread_id, "messages": messages, "updated_at": datetime.utcnow().isoformat()}, f, ensure_ascii=False, indent=2)
    return filename

def load_local_chats() -> List[Dict[str, Any]]:
    items = []
    for file in os.listdir(CHAT_HISTORY_DIR):
        if file.endswith(".json"):
            try:
                with open(os.path.join(CHAT_HISTORY_DIR, file), "r", encoding="utf-8") as f:
                    data = json.load(f)
                    items.append({"file": file, "title": data.get("title", file), "thread_id": data.get("thread_id", ""), "updated_at": data.get("updated_at", "")})
            except Exception:
                continue
    # sort by updated_at if present else by modified time
    def sort_key(x):
        try:
            return x.get("updated_at") or os.path.getmtime(os.path.join(CHAT_HISTORY_DIR, x["file"]))
        except Exception:
            return 0
    return sorted(items, key=sort_key, reverse=True)

def load_local_chat_file(filename: str) -> Dict[str, Any]:
    with open(os.path.join(CHAT_HISTORY_DIR, filename), "r", encoding="utf-8") as f:
        return json.load(f)

def delete_local_chat_file(filename: str):
    path = os.path.join(CHAT_HISTORY_DIR, filename)
    if os.path.exists(path):
        os.remove(path)

def rename_local_chat_file(filename: str, new_title: str) -> str:
    data = load_local_chat_file(filename)
    data["title"] = new_title
    new_filename = local_chat_filename(new_title, data.get("thread_id", ""))
    new_path = os.path.join(CHAT_HISTORY_DIR, new_filename)
    old_path = os.path.join(CHAT_HISTORY_DIR, filename)
    with open(old_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.rename(old_path, new_path)
    return new_filename


def create_new_thread():
    try:
        r = requests.post(f"{API_BASE}/new_thread", timeout=10)
        r.raise_for_status()
        return r.json().get("thread_id")
    except Exception as e:
        st.error(f"Failed to create new thread: {e}")
        return None

def send_message_to_backend(thread_id: str, message: str) -> str:
    try:
        r = requests.post(f"{API_BASE}/chat", json={"thread_id": thread_id, "message": message}, timeout=60)
        r.raise_for_status()
        data = r.json()
        return data.get("response") or data.get("message") or str(data)
    except Exception as e:
        return f"⚠️ Error communicating with backend: {e}"

st.set_page_config(page_title="ChatGPT-like Chat", layout="wide", page_icon="🤖")

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

if "thread_id" not in st.session_state:
    tid = create_new_thread()
    st.session_state.thread_id = tid or f"local-{int(time.time())}"

if "current_file" not in st.session_state:
    st.session_state.current_file = None
if "typing" not in st.session_state:
    st.session_state.typing = False

# Layout: sidebar (history) + main
sidebar, main = st.columns([1.4, 4])


with sidebar:
    st.markdown('<div class="sidebar">', unsafe_allow_html=True)
    st.markdown('<div class="title">💬 Chat History</div>', unsafe_allow_html=True)

    # New Chat button
    if st.button("➕ New Chat", key="new_chat_btn"):
        new_tid = create_new_thread()
        if new_tid:
            st.session_state.thread_id = new_tid
            st.session_state.chat_messages = []
            st.session_state.current_file = None
            st.rerun()

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    # Load local chats
    chats = load_local_chats()
    if not chats:
        st.markdown("<div class='subtle'>No saved chats yet. Start a new chat and it will be saved automatically.</div>", unsafe_allow_html=True)
    else:
        for c in chats:
            cols = st.columns([6,1,1])
            if cols[0].button(c["title"], key=f"open_{c['file']}"):
                data = load_local_chat_file(c["file"])
                st.session_state.chat_messages = data.get("messages", [])
                st.session_state.thread_id = data.get("thread_id", st.session_state.thread_id)
                st.session_state.current_file = c["file"]
                st.experimental_rerun()

            # Delete icon
            if cols[2].button("✖", key=f"del_{c['file']}"):
                delete_local_chat_file(c["file"])
                if st.session_state.current_file == c["file"]:
                    st.session_state.current_file = None
                    st.session_state.chat_messages = []
                st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)


with main:
    st.markdown("<div class='chat-window'>", unsafe_allow_html=True)
    header_cols = st.columns([9,1])
    header_cols[0].markdown("<h2 style='margin:0;color:#fff'>🤖 AI Chat Assistant</h2>", unsafe_allow_html=True)
    header_cols[0].markdown("<div class='subtle'>Start your Conversation</div>", unsafe_allow_html=True)

    # Chat messages container
    chat_box = st.container()
    with chat_box:
        scroll_div = st.empty()
        html_parts = ['<div class="chat-scroll">']
        for m in st.session_state.chat_messages:
            role = m.get("role", "assistant")
            content = m.get("content", "")
            if role == "user":
                html_parts.append(f'<div class="msg user"><div class="meta">You</div>{st.markdown.__wrapped__.__name__}</div>')
            else:
                html_parts.append(f'<div class="msg assistant"><div class="meta">AI</div>{st.markdown.__wrapped__.__name__}</div>')
        html_parts.append("</div>")
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        for m in st.session_state.chat_messages:
            role = m.get("role", "assistant")
            content = m.get("content", "")
            if role == "user":
                st.markdown(f'<div class="msg user"><div class="meta">You</div></div>', unsafe_allow_html=True)
                st.markdown(f"<div style='display:flex; justify-content:flex-end;'><div class='msg user'>{st.session_state.get('user_avatar','')}&nbsp;{st.markdown.__wrapped__.__name__}</div></div>", unsafe_allow_html=True)
                st.markdown(f'<div style="display:flex; justify-content:flex-end;"><div class="msg user">{escape_html(content)}</div></div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div style="display:flex; justify-content:flex-start;"><div class="msg assistant">', unsafe_allow_html=True)
                st.markdown(content, unsafe_allow_html=False)
                st.markdown('</div></div>', unsafe_allow_html=True)

    # Input area fixed at bottom
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    with st.form("input_form", clear_on_submit=False):
        cols = st.columns([12,1])
        user_msg = cols[0].text_input("Type your message and press Enter...", key="input_text", placeholder="Ask me anything...", label_visibility="hidden")
        send = cols[1].form_submit_button("➤")
        if send and user_msg:
            st.session_state.chat_messages.append({"role": "user", "content": user_msg})
            if st.session_state.chat_messages:
                title = st.session_state.chat_messages[0]["content"][:40]
            else:
                title = "Chat"
            save_local_chat(title, st.session_state.chat_messages, st.session_state.thread_id)
            st.session_state.typing = True

            typing_placeholder = st.empty()
            dots = ""
            start_time = time.time()
            resp_text = None
            try:
                with st.spinner("AI is thinking..."):
                    resp_text = send_message_to_backend(st.session_state.thread_id, user_msg)
            except Exception as e:
                resp_text = f"⚠️ {e}"
            finally:
                st.session_state.typing = False
                typing_placeholder.empty()

            st.session_state.chat_messages.append({"role": "assistant", "content": resp_text})
            save_local_chat(title, st.session_state.chat_messages, st.session_state.thread_id)
            st.rerun()

def escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#039;")
        .replace("\n", "<br>")
    )


