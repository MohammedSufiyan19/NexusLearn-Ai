from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


# This is the "memory" of our agent
# Every node in the graph reads from and writes to this
class AgentState(TypedDict):

    # stores the full chat history
    # add_messages means it appends, not overwrites
    messages: Annotated[list, add_messages]

    # what the user just asked
    query: str

    # chunks retrieved from FAISS (empty if normal chat)
    context: list

    # router decides this: "rag" or "chat"
    route: str

    # list of sources shown as pills in the UI
    # eg: [{"source": "dbms.pdf", "page": 3}]
    sources: list
