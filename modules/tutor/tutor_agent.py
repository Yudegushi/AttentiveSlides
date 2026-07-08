"""Task-bounded tutor agent for the first dry-run pipeline."""

from __future__ import annotations

from modules.common.schemas import ResolvedQuery, TutorResponse
from modules.interaction.interaction_history import InteractionHistory
from modules.tutor.context_retriever import ContextRetriever, MockDeckStore
from modules.tutor.llm_tutor import LLMClient, MockLLM
from modules.tutor.prompt_template import build_prompt


class TutorAgent:
    def __init__(
        self,
        context_retriever: ContextRetriever | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self.context_retriever = context_retriever or ContextRetriever()
        self.llm_client = llm_client or MockLLM()

    def answer(
        self,
        resolved_query: ResolvedQuery,
        deck_state: MockDeckStore | None = None,
        history: InteractionHistory | None = None,
    ) -> TutorResponse:
        if deck_state:
            self.context_retriever = ContextRetriever(deck_state)

        context = self.context_retriever.retrieve_context(resolved_query, history)
        prompt = build_prompt(context)
        return self.llm_client.generate(context, prompt)
