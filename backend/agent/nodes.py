
from agent.llm import get_llm
from agent.state import AgentState
from agent.tools import TOOL_MAP


def router_node(state: AgentState) -> AgentState:
    """
    Decides whether to use RAG or just chat freely.
    Logic:
    - If no docs uploaded → chat
    - If docs exist + question seems doc-related → rag
    - If question is general knowledge → chat
    """
    query = state["query"]

    # check if any docs are in the vector store
    from vectorstore.store import get_all_sources
    sources = get_all_sources()

    if not sources:
        # no docs uploaded yet, just chat
        return {**state, "route": "chat"}

    # ask the LLM to classify the query
    llm = get_llm()
    classification_prompt = f"""You are a query classifier for an academic assistant.

Uploaded documents available: {[s['source'] for s in sources]}

Student query: "{query}"

Classify this query into ONE of these categories:
- "topic_explainer" → student wants to understand a concept/topic
- "question_solver" → student wants to solve an exam question
- "learning_path_generator" → student wants a study plan or schedule
- "content_synthesizer" → student wants info from multiple sources combined
- "chat" → general question not related to uploaded documents

Reply with ONLY one word from the options above. Nothing else."""

    response = llm.invoke(classification_prompt)
    route = response.content.strip().lower()

    # safety fallback
    valid_routes = list(TOOL_MAP.keys()) + ["chat"]
    if route not in valid_routes:
        route = "chat"

    return {**state, "route": route}


def retriever_node(state: AgentState) -> AgentState:
    """
    Calls the right tool based on router decision.
    Fetches relevant chunks from FAISS.
    """
    query = state["query"]
    route = state["route"]

    if route == "chat":
        return {**state, "context": [], "sources": []}

    # call the appropriate tool
    tool = TOOL_MAP[route]
    result = tool(query)

    return {
        **state,
        "context": result.get("prompt", ""),
        "sources": result.get("sources", [])
    }


def generator_node(state: AgentState) -> AgentState:
    """
    Generates the final answer.
    Uses RAG context if available, otherwise free chat.
    """
    state["query"]
    route = state["route"]
    context = state.get("context", "")

    llm = get_llm()

    if route == "chat" or not context:
        # free chat mode — no documents involved
        messages = state["messages"]
        response = llm.invoke(messages)
    else:
        # RAG mode — use the prompt built by the tool
        response = llm.invoke(context)

    from langchain_core.messages import AIMessage
    return {
        **state,
        "messages": [AIMessage(content=response.content)]
    }
