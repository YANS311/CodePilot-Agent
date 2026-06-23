"""Intent routing layer — hybrid rule + embedding + LLM fallback."""

from app.router.intent_router import IntentRouter, IntentResult, get_intent_router

__all__ = ["IntentRouter", "IntentResult", "get_intent_router"]
