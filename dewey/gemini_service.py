"""Gemini API client for multimodal electronic component identification."""

import json
import logging
import os
from typing import Optional, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

from dewey.config import GEMINI_MODEL, MAX_DESCRIPTION_WORDS

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = (
    "You are an expert electronics lab assistant cataloging components for an inventory database. "
    "Examine the image carefully. The image shows an electronic component or bag of parts. "
    "It may have a printed label (with or without a barcode or distributor info), a handwritten label, "
    "direct component markings (laser etching, stamped part number, SMD codes, resistor bands), "
    "or no label. "
    "Identify the component: determine the exact manufacturer part number (MPN) or standard industry part number. "
    "Provide a concise, informative technical description of the component (strictly 100 words maximum), "
    "including component type, key ratings (voltage, current, tolerance, etc.), package type, and typical lab function."
)

JSON_SCHEMA = {
    "type": "OBJECT",
    "required": ["part_number", "description"],
    "properties": {
        "part_number": {
            "type": "STRING",
            "description": "Manufacturer part number (MPN), standard industry part number, or part designation.",
        },
        "description": {
            "type": "STRING",
            "description": "Concise technical description of the component (maximum 100 words).",
        },
    },
}


class GeminiComponentIdentifier:
    """Uses Google GenAI SDK to identify electronic components from camera photographs."""

    def __init__(self, api_key: Optional[str] = None, model: str = GEMINI_MODEL):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.model = model
        self.client: Optional["genai.Client"] = None
        self._init_client()

    def _init_client(self) -> None:
        if genai is None:
            logger.warning("google-genai SDK is not installed. Gemini service in mock mode.")
            return

        if not self.api_key:
            logger.warning("No GEMINI_API_KEY or GOOGLE_API_KEY found in environment.")
            return

        try:
            self.client = genai.Client(api_key=self.api_key)
            logger.info("Gemini client initialized with model '%s'.", self.model)
        except Exception as err:
            logger.error("Failed to initialize Gemini client: %s", err)
            self.client = None

    def identify_component(self, jpeg_bytes: bytes) -> Tuple[str, str]:
        """Sends component image to Gemini and returns (part_number, description)."""
        if not self.client or types is None:
            if not self.api_key:
                raise ValueError("API Key missing: set GEMINI_API_KEY in environment or .env file.")
            raise RuntimeError("google-genai SDK is not available.")

        image_part = types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg")
        prompt = (
            "Identify this electronic component from the photograph. "
            "Determine its manufacturer part number (or standard part number) "
            "and write a short description (under 100 words)."
        )

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_json_schema=JSON_SCHEMA,
            temperature=0.2,
        )

        logger.info("Sending image to Gemini (%s)...", self.model)
        response = self.client.models.generate_content(
            model=self.model,
            contents=[image_part, prompt],
            config=config,
        )

        raw_text = response.text or "{}"
        try:
            data = json.loads(raw_text)
            part_number = data.get("part_number", "UNKNOWN_PART").strip()
            description = data.get("description", "No description available.").strip()
        except Exception as err:
            logger.warning("Could not parse JSON response from Gemini (%s), using raw text fallback.", err)
            part_number = "IDENTIFIED_PART"
            description = raw_text.strip()

        # Enforce max description word count
        words = description.split()
        if len(words) > MAX_DESCRIPTION_WORDS:
            description = " ".join(words[:MAX_DESCRIPTION_WORDS]) + "..."

        logger.info("Identified part: %s", part_number)
        return part_number, description
