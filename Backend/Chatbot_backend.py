from langgraph.graph import StateGraph, START
from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph.message import add_messages
import sqlite3
from langchain_community.tools import DuckDuckGoSearchRun, WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper
from langgraph.prebuilt import ToolNode, tools_condition
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
import os

# ---------- Load Environment Variables ----------
load_dotenv()
google_api_key = os.getenv("GOOGLE_API_KEY")

# Initialize LLM
llm = init_chat_model("google_genai:gemini-2.0-flash", api_key=google_api_key)


# ---------- Define Chat State ----------
class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


# ---------- Define Tools ----------
search_tool = DuckDuckGoSearchRun()
wikipedia_tool = WikipediaQueryRun(api_wrapper=WikipediaAPIWrapper())


tools = [search_tool, wikipedia_tool]
llm_with_tools = llm.bind_tools(tools)
tool_node = ToolNode(tools=tools)


# ---------- Define Chat Node ----------
def chat_node(state: ChatState):
    messages = state['messages']
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


# ---------- SQLite Checkpointing ----------
conn = sqlite3.connect('chatbot.db', check_same_thread=False, isolation_level=None)
checkpointer = SqliteSaver(conn=conn)


# ---------- LangGraph Setup ----------
graph = StateGraph(ChatState)
graph.add_node('chat_node', chat_node)
graph.add_node('tools', tool_node)

graph.add_edge(START, 'chat_node')
graph.add_conditional_edges('chat_node', tools_condition)
graph.add_edge('tools', 'chat_node')

chatbot = graph.compile(checkpointer=checkpointer)


# ---------- Thread Management ----------
def retrieve_all_threads():
    unique_threads = set()
    for checkpoint in checkpointer.list(None):
        cfg = checkpoint.config.get('configurable', {})
        if 'thread_id' in cfg:
            unique_threads.add(cfg['thread_id'])
    return list(unique_threads)


# ---------- Chat File Handling ----------
CHAT_HISTORY_DIR = "chat_history"
os.makedirs(CHAT_HISTORY_DIR, exist_ok=True)


def save_chat_to_file(thread_id: str, messages: list, chat_name: str = None):
    """Save chat to file."""
    filename = chat_name or thread_id
    file_path = os.path.join(CHAT_HISTORY_DIR, f"{filename}.txt")
    with open(file_path, "w", encoding="utf-8") as f:
        for msg in messages:
            role = msg.__class__.__name__.replace("Message", "").lower()
            f.write(f"{role}: {msg.content}\n\n")
    return file_path


def delete_chat_history(thread_id: str):
    """Delete SQLite checkpoint + chat file."""
    for checkpoint in checkpointer.list(None):
        cfg = checkpoint.config.get('configurable', {})
        if cfg.get('thread_id') == thread_id:
            checkpointer.delete(config=checkpoint.config)

    for file in os.listdir(CHAT_HISTORY_DIR):
        if thread_id in file:
            os.remove(os.path.join(CHAT_HISTORY_DIR, file))
