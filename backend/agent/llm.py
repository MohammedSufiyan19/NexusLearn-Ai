import os

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_mistralai import ChatMistralAI

load_dotenv()

GROQ_KEYS = [
    os.getenv("GROQ_API_KEY_1"),
    os.getenv("GROQ_API_KEY_2"),
    os.getenv("GROQ_API_KEY_3"),
    os.getenv("GROQ_API_KEY_4"),
    os.getenv("GROQ_API_KEY_5"),
]

# filter out any None keys
GROQ_KEYS = [k for k in GROQ_KEYS if k]

_key_index = 0


def get_llm():
    """
    Returns a Groq LLM rotating through 5 keys.
    Falls back to Mistral if all Groq keys fail.
    """
    global _key_index

    for _ in range(len(GROQ_KEYS)):
        key = GROQ_KEYS[_key_index % len(GROQ_KEYS)]
        _key_index += 1
        try:
            return ChatGroq(
                api_key=key,
                model="llama-3.3-70b-versatile",
                temperature=0.3,
            )
        except Exception:
            continue

    # all groq keys failed — fallback to Mistral
    return ChatMistralAI(
        api_key=os.getenv("MISTRAL_API_KEY"),
        model="mistral-large-latest",
        temperature=0.3,
    )
