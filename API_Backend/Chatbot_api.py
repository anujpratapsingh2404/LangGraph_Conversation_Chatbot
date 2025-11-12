from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
from langchain_core.messages import HumanMessage, AIMessage
from Chatbot_backend import chatbot, retrieve_all_threads, save_chat_to_file, delete_chat_history
import uuid

app = FastAPI(title="LangGraph Chatbot API")


# ---------- Helpers ----------
def generate_thread_id():
    return str(uuid.uuid4())

def load_conversation(thread_id: str):
    state = chatbot.get_state(config={"configurable": {"thread_id": thread_id}})
    return state.values.get("messages", [])


# ---------- Models ----------
class ChatRequest(BaseModel):
    thread_id: str
    message: str

class ChatResponse(BaseModel):
    thread_id: str
    response: str

class ThreadListResponse(BaseModel):
    threads: List[str]

class HistoryMessage(BaseModel):
    role: str
    content: str

class ChatHistoryResponse(BaseModel):
    thread_id: str
    history: List[HistoryMessage]

class NewThreadResponse(BaseModel):
    thread_id: str
    message: str

class SaveChatRequest(BaseModel):
    thread_id: str
    chat_name: str

class DeleteChatRequest(BaseModel):
    thread_id: str


# ---------- Endpoints ----------
@app.get("/")
def root():
    return {"message": "Welcome to LangGraph Chatbot API"}

@app.get("/threads", response_model=ThreadListResponse)
def get_threads():
    return {"threads": retrieve_all_threads()}

@app.post("/new_thread", response_model=NewThreadResponse)
def create_thread():
    tid = generate_thread_id()
    return {"thread_id": tid, "message": "New thread created"}

@app.post("/chat", response_model=ChatResponse)
def chat(chat: ChatRequest):
    CONFIG = {
        "configurable": {"thread_id": chat.thread_id},
        "metadata": {"thread_id": chat.thread_id},
        "run_name": "chat_turn",
    }

    try:
        response = chatbot.invoke(
            {"messages": [HumanMessage(content=chat.message)]},
            config=CONFIG
        )
        final_response = response["messages"][-1].content if "messages" in response else "No response generated."
        return {"thread_id": chat.thread_id, "response": final_response}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/history/{thread_id}", response_model=ChatHistoryResponse)
def history(thread_id: str):
    messages = load_conversation(thread_id)
    formatted = []
    for msg in messages:
        role = "user" if isinstance(msg, HumanMessage) else "assistant"
        formatted.append({"role": role, "content": msg.content})
    return {"thread_id": thread_id, "history": formatted}

@app.post("/save_chat")
def save_chat(req: SaveChatRequest):
    messages = load_conversation(req.thread_id)
    path = save_chat_to_file(req.thread_id, messages, req.chat_name)
    return {"message": f"Chat saved as '{req.chat_name}.txt'", "path": path}

@app.delete("/delete_chat")
def delete_chat(req: DeleteChatRequest):
    delete_chat_history(req.thread_id)
    return {"message": f"Chat {req.thread_id} deleted successfully"}
