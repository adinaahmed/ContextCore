from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """
    Abstract interface every LLM backend must implement.
    Takes a fully-constructed prompt string, returns generated text.
    Prompt construction stays the caller's responsibility (in LLMService) —
    this keeps providers swappable without duplicating RAG prompt logic per backend.
    """

    @abstractmethod
    def generate(self, prompt: str) -> str:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Cheap check of whether this provider is currently usable."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...
