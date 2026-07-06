import asyncio
from langgraph.graph import StateGraph, START, END
from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


class State(TypedDict):
    messages: Annotated[list, add_messages]


def node_a(state):
    return {"messages": [("assistant", "hello")]}


builder = StateGraph(State)
builder.add_node("a", node_a)
builder.set_entry_point("a")
builder.set_finish_point("a")
graph = builder.compile()


async def run():
    print("--- v2 ---")
    async for event in graph.astream_events(
        {"messages": [("user", "hi")]}, version="v2"
    ):
        if event["event"] in [
            "on_chat_model_stream",
            "on_chain_start",
            "on_chain_stream",
        ]:
            print(event["event"], event.get("name"))
    print("--- v3 (astream messages) ---")
    try:
        async for chunk in graph.astream(
            {"messages": [("user", "hi")]}, stream_mode="messages"
        ):
            print("Message chunk:", chunk)
    except Exception as e:
        print("Error with v3:", e)


asyncio.run(run())
