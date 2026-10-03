import os
from datetime import date

from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, trim_messages
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.redis import RedisSaver
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

import db
import rag

load_dotenv()

SYSTEM_PROMPT = """تو یک دستیار محرمانه سلامت روان برای همکاران شرکت صنایع غذایی سلامت اندیشان نو هستی.
با لحن آرام و همدل پاسخ بده و راهکارهای عملی برای مدیریت استرس و بهزیستی روانی پیشنهاد کن.
- برای سوال‌های مربوط به سلامت روان و قوانین مشاوره شرکت از ابزار search_docs استفاده کن و فقط بر اساس نتایج آن جواب بده.
- برای رزرو وقت، اول وقت‌های خالی را با get_free_slots ببین. قبل از رزرو، روز و ساعت را با کاربر تایید کن.
- اگر کاربر از آسیب به خود یا بحران جدی صحبت کرد، فورا شماره ۱۴۸۰ (صدای مشاور) و ۱۲۳ (اورژانس اجتماعی) را بده و او را به متخصص ارجاع بده.
امروز {today} است."""


def current_user(config):
    return config["configurable"]["thread_id"]


@tool(response_format="content_and_artifact")
def search_docs(question: str):
    """Search the company mental health guides: stress, sleep, burnout, counseling service rules and emergency numbers."""
    results = rag.search(question)
    text = "\n\n".join(f"[{r['source']}]\n{r['text']}" for r in results)
    return text, sorted({r["source"] for r in results})


@tool
def get_free_slots(config: RunnableConfig) -> str:
    """Show free counseling times for the next 7 working days and the user's current bookings."""
    lines = [f"{day}: {'، '.join(hours) or 'پر است'}" for day, hours in db.free_slots().items()]
    mine = db.my_appointments(current_user(config))
    lines.append("رزروهای فعلی کاربر: " + ("، ".join(mine) or "ندارد"))
    return "\n".join(lines)


@tool
def book_appointment(day: str, hour: str, config: RunnableConfig) -> str:
    """Book a counseling session. day format: YYYY-MM-DD, hour format: HH:00"""
    return db.book(current_user(config), day, hour)


@tool
def cancel_appointment(day: str, hour: str, config: RunnableConfig) -> str:
    """Cancel one of the user's counseling sessions. day format: YYYY-MM-DD, hour format: HH:00"""
    return db.cancel(current_user(config), day, hour)


tools = [search_docs, get_free_slots, book_appointment, cancel_appointment]

llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.4,
    api_key=os.getenv("AVALAI_API_KEY"),
    base_url="https://api.avalai.ir/v1",
).bind_tools(tools)


def agent_node(state: MessagesState):
    # only send the last 5 messages to the model
    messages = trim_messages(state["messages"], max_tokens=5, token_counter=len, strategy="last", start_on="human")
    today = date.today()
    system = SystemMessage(SYSTEM_PROMPT.format(today=f"{db.DAY_NAMES[today.weekday()]} {today.isoformat()}"))
    return {"messages": [llm.invoke([system] + messages)]}


builder = StateGraph(MessagesState)
builder.add_node("agent", agent_node)
builder.add_node("tools", ToolNode(tools))
builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", tools_condition)
builder.add_edge("tools", "agent")

checkpointer = RedisSaver(redis_url=rag.REDIS_URL)
checkpointer.setup()
graph = builder.compile(checkpointer=checkpointer)
