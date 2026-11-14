import textwrap
from io import BytesIO

from PIL import Image, ImageDraw

from app.services.ai.base import AIProviderAdapter, GenerationRequest

# A small rotating palette so multiple designs look distinct.
_PALETTES = [
    ((36, 33, 30), (176, 128, 90)),
    ((25, 34, 44), (56, 189, 248)),
    ((40, 30, 34), (239, 138, 98)),
    ((28, 38, 34), (94, 170, 130)),
]


class MockAdapter(AIProviderAdapter):
    """Deterministic demo renderer (no external API).

    Produces a labeled placeholder image so the full generation → gallery →
    comparison pipeline works without a valid AI provider key.
    """

    name = "demo"
    model = "mynest-demo-render"

    def generate(self, request: GenerationRequest) -> list[bytes]:
        images: list[bytes] = []
        for index in range(request.count):
            images.append(self._render(request, index))
        return images

    def _render(self, request: GenerationRequest, index: int) -> bytes:
        w, h = request.width, request.height
        top, accent = _PALETTES[index % len(_PALETTES)]
        image = Image.new("RGB", (w, h))
        draw = ImageDraw.Draw(image)
        for y in range(h):
            t = y / h
            draw.line(
                [(0, y), (w, y)],
                fill=(
                    int(top[0] + (accent[0] - top[0]) * t),
                    int(top[1] + (accent[1] - top[1]) * t),
                    int(top[2] + (accent[2] - top[2]) * t),
                ),
            )

        lines = [
            "MYNEST DESIGN STUDIO",
            "AI Interior Visualization — DEMO",
            "",
            f"Style: {request.style or 'Default'}",
            f"Design variant: {index + 1}",
            "",
            "Geometry preserved from canonical JSON.",
            "Add a valid NVIDIA API key for a",
            "photorealistic render.",
        ]
        y = h // 2 - 90
        for line in lines:
            draw.text((60, y), line, fill=(245, 245, 245))
            y += 20

        wrapped = textwrap.fill(request.prompt.strip().splitlines()[0][:120], width=70)
        draw.text((60, h - 60), wrapped, fill=(220, 220, 220))

        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
