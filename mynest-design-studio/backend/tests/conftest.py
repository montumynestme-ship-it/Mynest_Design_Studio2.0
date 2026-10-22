"""Shared test fixtures.

Hermetic NVIDIA config: adapter/generation tests must not depend on the
developer's backend/.env (which may point NVIDIA_API_BASE at a local NIM, enable
img2img, etc. for manual testing). This autouse fixture resets the NVIDIA image
config to safe, deterministic defaults — hosted endpoint, flux.1-dev,
text-to-image — before each test. Tests that exercise img2img / self-hosted NIM
patch these names explicitly inside their own `with mock.patch(...)` blocks, and
those patches take precedence for the duration of the test.
"""

from unittest import mock

import pytest

_ADAPTER = "app.services.ai.nvidia_flux_adapter"


@pytest.fixture(autouse=True)
def hermetic_nvidia_config():
    with mock.patch(f"{_ADAPTER}.NVIDIA_API_BASE", "https://ai.api.nvidia.com/v1/genai"), \
         mock.patch(f"{_ADAPTER}.NVIDIA_IMAGE_MODEL", "black-forest-labs/flux.1-dev"), \
         mock.patch(f"{_ADAPTER}.NVIDIA_SUPPORTS_IMG2IMG", False), \
         mock.patch(f"{_ADAPTER}.NVIDIA_ARBITRARY_IMAGE_SUPPORTED", False), \
         mock.patch(f"{_ADAPTER}.NVIDIA_IMG2IMG_MODE", "canny"), \
         mock.patch(f"{_ADAPTER}.NVIDIA_NIM_INFER_PATH", "/v1/infer"):
        yield
