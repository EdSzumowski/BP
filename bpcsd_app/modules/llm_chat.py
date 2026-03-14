"""
llm_chat.py — LLM-powered chat over aggregated BPCSD reports.

Supports:
  - Google Gemini (via google-generativeai)
  - OpenAI (via openai)
  - Anthropic Claude (via anthropic)

Usage:
  client = LLMClient.from_key(api_key)   # auto-detects provider from key format
  response = client.chat(
      system_prompt="You are a school board analyst...",
      context_docs={"January 2025 Revenue Status": "...text...", ...},
      history=[{"role": "user", "content": "..."}, ...],
      question="How many people were appointed to sports positions?",
  )

The context window strategy:
  - All document text is concatenated into the system/context prompt
  - Gemini 1.5 Pro supports 1M tokens — ideal for full-year document sets
  - For OpenAI/Anthropic (smaller windows), we truncate to fit
"""

import re
from typing import Generator

# Token budget constants
GEMINI_MAX_TOKENS  = 900_000   # leave headroom in 1M window
OPENAI_MAX_TOKENS  = 110_000   # gpt-4o context ~128K
ANTHROPIC_MAX_TOKENS = 180_000 # claude-3.5 context ~200K

CHARS_PER_TOKEN = 4  # rough estimate


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n\n[...truncated: {len(text)-max_chars:,} chars omitted...]"


def _build_context_block(docs: dict[str, str], max_chars: int) -> str:
    """Concatenate all documents into a context block, truncating if needed."""
    parts = []
    remaining = max_chars
    for title, text in docs.items():
        if remaining <= 0:
            parts.append(f"\n\n## {title}\n[omitted — context limit reached]")
            continue
        snippet = _truncate(text, remaining)
        parts.append(f"\n\n## {title}\n{snippet}")
        remaining -= len(snippet)
    return "\n".join(parts)


SYSTEM_PROMPT_TEMPLATE = """You are an expert school board analyst for Broadalbin-Perth Central School District (BPCSD) in upstate New York. You have been given a collection of official board reports extracted from BoardDocs.

Your role is to:
- Answer questions accurately based on the provided documents
- Cite specific reports and months when making claims
- Flag when information is not present in the documents
- Identify trends, anomalies, and notable changes across months
- Be concise but thorough; use bullet points for lists of facts

When referring to financial figures, always include the specific account code and description if available.

The following board reports have been loaded:
{doc_list}

Full report content follows:
---
{context}
---
"""


class LLMClient:
    """Unified LLM client that wraps Gemini, OpenAI, or Anthropic."""

    def __init__(self, provider: str, api_key: str, model: str | None = None):
        self.provider = provider
        self.api_key  = api_key
        self.model    = model or _default_model(provider)

    @classmethod
    def from_key(cls, api_key: str) -> "LLMClient":
        """Auto-detect provider from API key prefix."""
        key = api_key.strip()
        if key.startswith("AIza") or key.startswith("AI") and len(key) > 30:
            return cls("gemini", key)
        elif key.startswith("sk-ant-"):
            return cls("anthropic", key)
        elif key.startswith("sk-"):
            return cls("openai", key)
        else:
            raise ValueError(
                "Cannot detect provider from key. "
                "Gemini keys start with 'AIza', OpenAI with 'sk-', Anthropic with 'sk-ant-'."
            )

    @property
    def provider_label(self) -> str:
        return {"gemini": "Google Gemini", "openai": "OpenAI", "anthropic": "Anthropic Claude"}.get(
            self.provider, self.provider.title()
        )

    def max_context_chars(self) -> int:
        return {
            "gemini":    GEMINI_MAX_TOKENS * CHARS_PER_TOKEN,
            "openai":    OPENAI_MAX_TOKENS * CHARS_PER_TOKEN,
            "anthropic": ANTHROPIC_MAX_TOKENS * CHARS_PER_TOKEN,
        }.get(self.provider, 400_000)

    def chat(self, context_docs: dict[str, str], history: list[dict],
             question: str) -> str:
        """
        Send a chat message and return the response string.
        context_docs: {title: extracted_text}
        history: [{role: "user"|"assistant", content: str}]
        question: the new user message
        """
        doc_list = "\n".join(f"- {title}" for title in context_docs)
        context  = _build_context_block(context_docs, self.max_context_chars() - 5000)
        system   = SYSTEM_PROMPT_TEMPLATE.format(doc_list=doc_list, context=context)

        if self.provider == "gemini":
            return self._chat_gemini(system, history, question)
        elif self.provider == "openai":
            return self._chat_openai(system, history, question)
        elif self.provider == "anthropic":
            return self._chat_anthropic(system, history, question)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    # ── Gemini ────────────────────────────────────────────────────────────────
    def _chat_gemini(self, system: str, history: list, question: str) -> str:
        try:
            import google.generativeai as genai
        except ImportError:
            raise ImportError(
                "google-generativeai not installed. "
                "Run: pip install google-generativeai"
            )
        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(
            model_name=self.model,
            system_instruction=system,
        )
        # Build history in Gemini format
        gemini_history = []
        for msg in history:
            role = "user" if msg["role"] == "user" else "model"
            gemini_history.append({"role": role, "parts": [msg["content"]]})

        chat = model.start_chat(history=gemini_history)
        response = chat.send_message(question)
        return response.text

    # ── OpenAI ────────────────────────────────────────────────────────────────
    def _chat_openai(self, system: str, history: list, question: str) -> str:
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("openai not installed. Run: pip install openai")
        client = OpenAI(api_key=self.api_key)
        messages = [{"role": "system", "content": system}]
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": question})
        resp = client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.2,
        )
        return resp.choices[0].message.content

    # ── Anthropic ─────────────────────────────────────────────────────────────
    def _chat_anthropic(self, system: str, history: list, question: str) -> str:
        try:
            import anthropic
        except ImportError:
            raise ImportError("anthropic not installed. Run: pip install anthropic")
        client = anthropic.Anthropic(api_key=self.api_key)
        messages = []
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": question})
        resp = client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            messages=messages,
        )
        return resp.content[0].text


def _default_model(provider: str) -> str:
    return {
        "gemini":    "gemini-1.5-pro",
        "openai":    "gpt-4o",
        "anthropic": "claude-3-5-sonnet-20241022",
    }.get(provider, "gemini-1.5-pro")


def validate_key(api_key: str) -> tuple[bool, str]:
    """
    Quick validation: try a minimal API call to verify the key works.
    Returns (success, message).
    """
    try:
        client = LLMClient.from_key(api_key)
    except ValueError as e:
        return False, str(e)

    try:
        result = client.chat(
            context_docs={"test": "This is a test."},
            history=[],
            question="Reply with exactly the word: OK"
        )
        if result:
            return True, f"Connected to {client.provider_label} ({client.model})"
        return False, "Empty response from API"
    except Exception as e:
        return False, f"API error: {e}"
