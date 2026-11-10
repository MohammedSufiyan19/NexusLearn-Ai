import os
import shutil

from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_mistralai import MistralAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

FAISS_PATH = "vectorstore/faiss_index"

embeddings = MistralAIEmbeddings(
    api_key=os.getenv("MISTRAL_API_KEY"),
    model="mistral-embed"
)

splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200,
)


def add_documents(docs: list[Document]) -> int:
    """
    Chunks and adds documents to FAISS.
    Returns number of chunks stored.
    """
    chunks = splitter.split_documents(docs)

    if os.path.exists(FAISS_PATH):
        db = FAISS.load_local(
            FAISS_PATH,
            embeddings,
            allow_dangerous_deserialization=True
        )
        db.add_documents(chunks)
    else:
        db = FAISS.from_documents(chunks, embeddings)

    db.save_local(FAISS_PATH)
    return len(chunks)


def search(query: str, k: int = 5, source_type: str = None) -> list[Document]:
    """
    Searches FAISS for relevant chunks.
    Optionally filter by source_type: 'pdf', 'docx', 'pptx'
    """
    if not os.path.exists(FAISS_PATH):
        return []

    db = FAISS.load_local(
        FAISS_PATH,
        embeddings,
        allow_dangerous_deserialization=True
    )
    results = db.similarity_search(query, k=k * 2)

    if source_type:
        results = [
            r for r in results
            if r.metadata.get("source_type") == source_type
        ]

    return results[:k]


def get_all_sources() -> list[dict]:
    """
    Returns list of all uploaded documents.
    Used by the sidebar in the UI.
    """
    if not os.path.exists(FAISS_PATH):
        return []

    db = FAISS.load_local(
        FAISS_PATH,
        embeddings,
        allow_dangerous_deserialization=True
    )
    seen = set()
    sources = []

    for doc in db.docstore._dict.values():
        src = doc.metadata.get("source")
        if src and src not in seen:
            seen.add(src)
            sources.append({
                "source": src,
                "source_type": doc.metadata.get("source_type")
            })

    return sources


def clear_store():
    """Wipes the entire vector store."""
    if os.path.exists(FAISS_PATH):
        shutil.rmtree(FAISS_PATH)
