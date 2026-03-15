import os
from typing import Iterable

from dotenv import load_dotenv
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

# Load environment variables (for OPENAI_API_KEY)
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Hardcoded model names
LLM_MODEL = "gpt-3.5-turbo"
EMBEDDING_MODEL = "text-embedding-ada-002"

class OpenAIService:
    def __init__(self):
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not set in environment.")
        self.client = OpenAI(api_key=OPENAI_API_KEY)

    def generate_llm_response(self, messages: Iterable[ChatCompletionMessageParam]) -> str:
        """
        Generate a response from the LLM using a list of messages (chat format).
        messages: Iterable[ChatCompletionMessageParam]
        Returns the assistant's reply as a string.
        """
        response = self.client.chat.completions.create(
            model=LLM_MODEL,
            messages=list(messages),
            temperature=0.7,
            max_tokens=512,
        )
        # Defensive: handle possible None return
        content = response.choices[0].message.content
        if content is None:
            return ""
        return content

    def get_embedding(self, text: str) -> list[float]:
        """
        Get the embedding vector for a given text using the embedding model.
        Returns a list of floats.
        """
        response = self.client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text,
        )
        return response.data[0].embedding

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Get embedding vectors for multiple texts in one API call."""
        if not texts:
            return []

        response = self.client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=texts,
        )
        return [item.embedding for item in response.data]

_singleton: "OpenAIService | None" = None

def get_openai_service() -> "OpenAIService":
    global _singleton
    if _singleton is None:
        _singleton = OpenAIService()
    return _singleton
