import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

import db
import rag
from agent import graph

st.set_page_config(page_title="سامانه محرمانه سلامت روان")
st.title("سامانه محرمانه سلامت روان صنایع غذایی سلامت اندیشان نو")


@st.cache_resource
def setup():
    db.seed_sample_data()
    if not rag.index.exists():
        rag.build_index()


def show_history(messages):
    sources = set()
    for msg in messages:
        if isinstance(msg, HumanMessage):
            st.chat_message("user").markdown(msg.content)
        elif isinstance(msg, ToolMessage) and msg.artifact:
            sources.update(msg.artifact)
        elif isinstance(msg, AIMessage) and msg.content:
            with st.chat_message("assistant"):
                st.markdown(msg.content)
                if sources:
                    st.caption("منابع: " + "، ".join(sorted(sources)))
            sources = set()


def stream_answer(text, config):
    for chunk, meta in graph.stream({"messages": [HumanMessage(text)]}, config, stream_mode="messages"):
        if meta["langgraph_node"] == "agent" and chunk.content:
            yield chunk.content


setup()

if "username" not in st.session_state:
    st.subheader("ورود")
    with st.form("login_form"):
        username = st.text_input("نام کاربری")
        password = st.text_input("کلمه عبور", type="password")
        if st.form_submit_button("ورود"):
            if not username.strip() or not password:
                st.error("نام کاربری و کلمه عبور را کامل وارد کنید.")
            elif db.login(username.strip(), password):
                st.session_state.username = username.strip()
                st.rerun()
            else:
                st.error("کلمه عبور اشتباه است.")
    st.stop()

username = st.session_state.username
config = {"configurable": {"thread_id": username}}

with st.sidebar:
    st.write(f"کاربر: {username}")
    st.header("وقت‌های مشاوره من")
    for item in db.my_appointments(username) or ["رزروی ندارید."]:
        st.write(item)
    if st.button("خروج"):
        del st.session_state.username
        st.rerun()

show_history(graph.get_state(config).values.get("messages", []))

if prompt := st.chat_input("احساس یا سوال خود را بنویسید"):
    st.chat_message("user").markdown(prompt)
    with st.chat_message("assistant"):
        st.write_stream(stream_answer(prompt, config))
    st.rerun()
