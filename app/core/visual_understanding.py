from google.genai import types
from app.core.llm_providers.gemini_provider import GeminiProvider
from PIL import Image
import io

_gemini = GeminiProvider()

MIN_IMAGE_DIMENSION = 80  # skip tiny icons/bullets/decorative images — not worth a vision call


def describe_image(image_bytes: bytes) -> str | None:
    """
    Uses Gemini's vision capability to generate a searchable text description
    of an image, figure, diagram, or chart. Returns None if the image is too
    small to be meaningful, or if description fails for any reason (never
    raises — a failed image description should not break the whole document).
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))

        if image.width < MIN_IMAGE_DIMENSION or image.height < MIN_IMAGE_DIMENSION:
            return None

        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        png_bytes = buffer.getvalue()

        response = _gemini.client.models.generate_content(
            model=_gemini.model_name,
            contents=[
                types.Part.from_bytes(data=png_bytes, mime_type="image/png"),
                "Describe this image in detail for someone who cannot see it. "
                "If it is a chart, graph, or diagram, describe the data, axes, "
                "trends, and any labeled values. If it contains text, include that text. "
                "Be concise but complete.",
            ],
        )
        return response.text.strip() if response.text else None

    except Exception:
        return None
