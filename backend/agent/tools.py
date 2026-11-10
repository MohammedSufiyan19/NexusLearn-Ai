from vectorstore.store import search


def topic_explainer(query: str) -> dict:
    """
    Tool 1: Explains a topic using uploaded study material.
    eg: "Explain Database Normalization"
    """
    chunks = search(query, k=5)

    if not chunks:
        return {"answer": None, "sources": []}

    context = "\n\n".join([c.page_content for c in chunks])
    sources = [
        {
            "source": c.metadata.get("source"),
            "page": c.metadata.get("page"),
            "source_type": c.metadata.get("source_type")
        }
        for c in chunks
    ]

    prompt = f"""You are an academic tutor helping a student understand a topic.
Using ONLY the study material below, explain the topic clearly.
Structure your answer as:
1. What it is (simple definition)
2. Key concepts (bullet points)
3. Example (if available in the material)
4. Related topics (if mentioned)

Study Material:
{context}

Topic to explain: {query}

Give a comprehensive, student-friendly explanation."""

    return {"prompt": prompt, "sources": sources}


def question_solver(query: str) -> dict:
    """
    Tool 2: Solves exam questions using uploaded question papers + notes.
    eg: "Solve Q3 from 2023 DBMS paper"
    """
    chunks = search(query, k=6)

    if not chunks:
        return {"answer": None, "sources": []}

    context = "\n\n".join([c.page_content for c in chunks])
    sources = [
        {
            "source": c.metadata.get("source"),
            "page": c.metadata.get("page"),
            "source_type": c.metadata.get("source_type")
        }
        for c in chunks
    ]

    prompt = f"""You are an academic tutor helping a student solve an exam question.
Using the study material below, provide a complete step-by-step solution.
Structure your answer as:
1. Understanding the question
2. Relevant concepts needed
3. Step-by-step solution
4. Key points to remember for exams

Study Material:
{context}

Question: {query}

Provide a clear, marks-worthy answer."""

    return {"prompt": prompt, "sources": sources}


def learning_path_generator(query: str) -> dict:
    """
    Tool 3: Generates a study plan based on uploaded syllabus/notes.
    eg: "I have exams in 3 days, help me study OS"
    BONUS POINTS TOOL — worth +15 in grading
    """
    chunks = search(query, k=5)

    context = "\n\n".join([c.page_content for c in chunks]) if chunks else ""
    sources = [
        {
            "source": c.metadata.get("source"),
            "page": c.metadata.get("page"),
            "source_type": c.metadata.get("source_type")
        }
        for c in chunks
    ]

    prompt = f"""You are an academic advisor helping a student prepare for exams.
Based on the study material available, create a practical study plan.
Structure your answer as:
1. Topic priority order (most important first)
2. Day-wise study schedule
3. Key topics to focus on per day
4. Quick revision tips
5. Important concepts not to miss

Available Study Material:
{context if context else "No material uploaded yet — give a general study plan for the topic."}

Student Request: {query}

Create a realistic, actionable study plan."""

    return {"prompt": prompt, "sources": sources}


def content_synthesizer(query: str) -> dict:
    """
    Tool 4: Cross-references ALL uploaded docs to give comprehensive answer.
    eg: "What does my textbook AND notes say about SQL joins?"
    """
    # search across all source types
    pdf_chunks = search(query, k=3, source_type="pdf")
    docx_chunks = search(query, k=3, source_type="docx")
    pptx_chunks = search(query, k=3, source_type="pptx")

    all_chunks = pdf_chunks + docx_chunks + pptx_chunks

    if not all_chunks:
        return {"answer": None, "sources": []}

    # build context showing which source each chunk came from
    context_parts = []
    for c in all_chunks:
        src = c.metadata.get("source", "unknown")
        context_parts.append(f"[From {src}]:\n{c.page_content}")

    context = "\n\n".join(context_parts)
    sources = [
        {
            "source": c.metadata.get("source"),
            "page": c.metadata.get("page"),
            "source_type": c.metadata.get("source_type")
        }
        for c in all_chunks
    ]

    prompt = f"""You are an academic assistant synthesizing information from multiple sources.
The student wants a comprehensive answer combining all their study materials.
Structure your answer as:
1. Combined explanation from all sources
2. Key points from each source
3. Any differences or complementary information between sources
4. Summary

Study Materials (from multiple sources):
{context}

Student Query: {query}

Give a comprehensive answer that connects information from all available sources."""

    return {"prompt": prompt, "sources": sources}


# router uses this to pick the right tool
TOOL_MAP = {
    "topic_explainer": topic_explainer,
    "question_solver": question_solver,
    "learning_path_generator": learning_path_generator,
    "content_synthesizer": content_synthesizer,
}
