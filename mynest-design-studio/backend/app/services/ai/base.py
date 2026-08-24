from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class GenerationRequest:
    prompt: str
    style: str | None
    count: int
    width: int = 1024
    height: int = 768


class AIProviderAdapter(ABC):
    """Vendor-agnostic image-generation adapter (PRD §27).

    The core app depends only on this interface; providers are swappable via
    configuration. Keys live server-side only.
    """

    name: str = "base"
    model: str = "unknown"

    @abstractmethod
    def generate(self, request: GenerationRequest) -> list[bytes]:
        """Return a list of PNG image byte strings, one per requested design."""
