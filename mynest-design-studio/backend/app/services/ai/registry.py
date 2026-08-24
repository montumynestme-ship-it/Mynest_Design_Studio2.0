from app.services.ai.base import AIProviderAdapter
from app.services.ai.mock_adapter import MockAdapter
from app.services.ai.nvidia_adapter import NvidiaAdapter

# Provider name -> adapter factory. New providers (gemini/openai/…) plug in here.
_ADAPTERS: dict[str, type[AIProviderAdapter]] = {
    "nvidia": NvidiaAdapter,
    "demo": MockAdapter,
}


def get_adapter(name: str) -> AIProviderAdapter:
    factory = _ADAPTERS.get(name, NvidiaAdapter)
    return factory()


def demo_adapter() -> AIProviderAdapter:
    return MockAdapter()
