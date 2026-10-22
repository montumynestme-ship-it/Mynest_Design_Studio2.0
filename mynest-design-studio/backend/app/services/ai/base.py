from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class GenerationRequest:
    prompt: str
    style: str | None
    count: int
    width: int = 1024
    height: int = 768
    seed: int | None = None
    generation_id: str | None = None
    room_label: str | None = None
    room_id: str | None = None
    variation_profile: str | None = None
    reference_images: list[str] = field(default_factory=list)
    control_image: bytes | None = None


class AIProviderError(Exception):
    """Structured error from an AI image provider.

    Carries the actionable diagnostics the UI should surface (HTTP status, the
    endpoint hit, elapsed time, and the provider's request/correlation id) so a
    failure is never reduced to a generic message. The provider API key is NEVER
    stored here or included in the message.
    """

    def __init__(
        self,
        provider: str,
        reason: str,
        status_code: int = 502,
        model: str | None = None,
        *,
        endpoint: str | None = None,
        elapsed: float | None = None,
        request_id: str | None = None,
    ) -> None:
        self.provider = provider
        self.reason = reason
        self.status_code = status_code
        self.model = model
        self.endpoint = endpoint
        self.elapsed = elapsed
        self.request_id = request_id
        extra = []
        if model:
            extra.append(f"model={model}")
        if endpoint:
            extra.append(f"endpoint={endpoint}")
        if elapsed is not None:
            extra.append(f"elapsed={elapsed:.2f}s")
        if request_id:
            extra.append(f"request_id={request_id}")
        suffix = f" [{'; '.join(extra)}]" if extra else ""
        super().__init__(f"[{provider}] {reason} (status {status_code}){suffix}")


class AIProviderAdapter(ABC):
    """Vendor-agnostic image-generation adapter (PRD §27).

    The core app depends only on this interface; providers are swappable via
    configuration. Keys live server-side only.
    """

    name: str = "base"
    model: str = "unknown"
    supports_seed: bool = True
    supports_image_reference: bool = False
    supports_control_image: bool = False

    @abstractmethod
    def generate(self, request: GenerationRequest) -> list[bytes]:
        """Return a list of PNG image byte strings, one per requested design."""
