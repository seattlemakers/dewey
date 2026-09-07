"""Gemini API client for multimodal electronic component identification and catalog label generation."""

import json
import logging
import os
import re
from typing import Any, Dict, Optional, Tuple

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

from dewey.config import (
    DEFAULT_LABEL_CATEGORY,
    DEFAULT_LABEL_DATABASE_ID,
    DEFAULT_LABEL_LOCATION,
    GEMINI_MODEL,
    MAX_DESCRIPTION_WORDS,
)

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = (
    "You are an expert electronics lab assistant cataloging components for a makerspace inventory system.\n"
    "Examine the photograph carefully. It shows an electronic component, breakout board, IC, module, or bag of parts. "
    "It may have printed labels, barcodes, distributor info, handwritten notes, laser etching, or SMD markings.\n"
    "Use Google Search to research the component or board on the web to determine its exact specifications, "
    "breakout board SKU / distributor part number (e.g. Adafruit, SparkFun, Pololu), current MSRP, "
    "voltage and current ratings, communication interfaces, compatible libraries, and pin warnings.\n\n"
    "Return a strictly valid JSON object with the following fields:\n"
    "{\n"
    '  "comp_type": "BOB", // Component classification. MUST be one of: "BOB" (Breakout board / module), "SMT" (Surface mount), "THT" (Through-hole), "PMT" (Panel mount), "OTH" (Other). Prioritize: BOB > SMT > THT > PMT > OTH.\n'
    '  "part_number": "FT232H", // Primary component / IC part number (e.g. FT232H, LM358, ESP32, 2N2222).\n'
    '  "mfr_part_number": "(Adafruit 2264)", // Manufacturer / distributor board SKU enclosed in parentheses if this is a breakout/assembled module, or "" if bare standard component.\n'
    '  "brief_desc": "FT232H Breakout: General Purpose USB to GPIO, SPI, I2C", // Bold summary line, strictly 64 characters maximum.\n'
    '  "price": "MSRP: $14.95", // Typical MSRP or current retail price (e.g. "MSRP: $14.95"). If price is per a quantity rather than per each, include the quantity and unit of measure (e.g. "MSRP: $2.50/10 pcs" or "MSRP: $5.00/pack").\n'
    '  "description": "..." // Approximately 100-word detailed technical specification paragraph covering: essential interfaces, power supply and I/O voltages, max currents, compatible software languages/libraries, and critical pin/usage warnings needed to start using the part.\n'
    "}\n"
    "Output ONLY the JSON object. Do not include markdown preamble, commentary, or backticks."
)


def extract_json_object(raw_text: str) -> Dict[str, Any]:
    """Robustly extracts and parses a JSON object from Gemini response text."""
    text = raw_text.strip()
    if not text:
        return {}

    # Check for markdown code fences
    fence_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except Exception:
            pass

    # Try direct parse
    try:
        return json.loads(text)
    except Exception:
        pass

    # Search for outermost matching braces
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except Exception:
            pass

    return {}


def normalize_comp_type(val: str, default: str = "OTH") -> str:
    """Normalizes component type according to priority: BOB > SMT > THT > PMT > OTH."""
    v = (val or "").strip().upper()
    if "BOB" in v or "BREAKOUT" in v or "MODULE" in v:
        return "BOB"
    if "SMT" in v or "SMD" in v or "SURFACE" in v:
        return "SMT"
    if "THT" in v or "THROUGH" in v or "DIP" in v:
        return "THT"
    if "PMT" in v or "PANEL" in v:
        return "PMT"
    if "OTH" in v or "OTHER" in v:
        return "OTH"
    return default


def normalize_mfr_pn(val: Optional[str]) -> str:
    """Ensures manufacturer SKU is wrapped in parentheses if present."""
    if not val:
        return ""
    v = val.strip()
    if not v or v.lower() in ("none", "n/a", "null"):
        return ""
    if not v.startswith("("):
        v = f"({v}"
    if not v.endswith(")"):
        v = f"{v})"
    return v


def normalize_price(val: Optional[str]) -> str:
    """Ensures price string follows 'MSRP: $X.XX' format, preserving quantity/unit (e.g. 'MSRP: $2.50/10 pcs')."""
    if not val:
        return "MSRP: $0.00"
    v = val.strip()
    if not v or v.lower() in ("none", "n/a", "null"):
        return "MSRP: $0.00"
    if v.startswith("MSRP:"):
        return v
    if v.startswith("$"):
        return f"MSRP: {v}"
    # Match number with optional unit/quantity suffix (e.g. "2.50/10 pcs", "14.95")
    match = re.search(r"^\$?(\d+(?:\.\d{1,2})?)(.*)$", v)
    if match:
        amount = match.group(1)
        unit_suffix = match.group(2).strip()
        return f"MSRP: ${amount}{unit_suffix}"
    return f"MSRP: {v}"


class GeminiComponentIdentifier:
    """Uses Google GenAI SDK with vision and Google Search grounding to catalog electronic components."""

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

    def identify_component(self, jpeg_bytes: bytes) -> Dict[str, Any]:
        """Sends component image to Gemini, performs web research, and returns complete label data dict."""
        if not self.client or types is None:
            if not self.api_key:
                raise ValueError("API Key missing: set GEMINI_API_KEY in environment or .env file.")
            raise RuntimeError("google-genai SDK is not available.")

        image_part = types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg")
        prompt = (
            "Examine this electronic component. Output the catalog JSON object with "
            "comp_type (BOB, SMT, THT, PMT, or OTH), part_number, mfr_part_number, "
            "brief_desc, price, and 100-word description."
        )

        # Google Search grounding triggers Automatic Function Calling (AFC) and requires
        # a paid billing account on Google AI Studio (otherwise returns 429 RESOURCE_EXHAUSTED).
        # Disabled by default; enable via DEWEY_ENABLE_SEARCH=true if billing is configured.
        enable_search_env = os.getenv("DEWEY_ENABLE_SEARCH", "false").lower()
        use_search = enable_search_env in ("1", "true", "yes", "enable")

        # Build tools list with Google Search grounding if explicitly enabled
        tools = []
        if use_search:
            try:
                tools.append(types.Tool(google_search=types.GoogleSearch()))
                logger.info("Google Search grounding tool enabled for Gemini.")
            except Exception as err:
                logger.warning("Could not initialize GoogleSearch tool (%s); proceeding without search.", err)
                use_search = False

        # Candidate models for automatic fallback (gemini-3.6-flash is the primary GA model)
        candidate_models = [self.model]
        for fallback in ["gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.5-flash-lite"]:
            if fallback not in candidate_models:
                candidate_models.append(fallback)

        response = None
        last_err = None

        for candidate in candidate_models:
            # Attempt query on candidate model (with up to 2 retries for transient 503 errors)
            for attempt in range(2):
                try:
                    if use_search and tools:
                        logger.info("Querying Gemini (%s) with web search grounding...", candidate)
                        config = types.GenerateContentConfig(
                            system_instruction=SYSTEM_INSTRUCTION,
                            tools=tools,
                            temperature=0.2,
                        )
                    else:
                        logger.info("Querying Gemini (%s) using direct vision...", candidate)
                        config = types.GenerateContentConfig(
                            system_instruction=SYSTEM_INSTRUCTION,
                            temperature=0.2,
                        )

                    response = self.client.models.generate_content(
                        model=candidate,
                        contents=[image_part, prompt],
                        config=config,
                    )
                    if candidate != self.model:
                        self.model = candidate
                    break
                except Exception as err:
                    last_err = err
                    err_str = str(err)
                    # If 503 high demand spike, brief pause and retry
                    if "503" in err_str or "UNAVAILABLE" in err_str:
                        logger.warning("Gemini model '%s' temporarily busy (503). Retrying in 1s (attempt %d/2)...",
                                       candidate, attempt + 1)
                        import time as _time
                        _time.sleep(1.0)
                        continue
                    # If search grounding failed (e.g. 429 quota exceeded), retry candidate immediately without search
                    if use_search:
                        logger.warning("Search tool failed on '%s' (%s). Retrying with direct vision...",
                                       candidate, err)
                        use_search = False
                        continue
                    logger.warning("Gemini query failed on '%s': %s", candidate, err)
                    break

            if response is not None:
                break

        if response is None and last_err is not None:
            raise last_err

        raw_text = response.text or "{}"
        parsed = extract_json_object(raw_text)

        # Deduce fields from Gemini JSON
        comp_type = normalize_comp_type(parsed.get("comp_type", "OTH"))
        part_number = str(parsed.get("part_number", "UNKNOWN_PART")).strip()
        mfr_part_number = normalize_mfr_pn(parsed.get("mfr_part_number"))

        brief_desc = str(parsed.get("brief_desc", "")).strip()
        if not brief_desc:
            brief_desc = f"{part_number} Component"
        if len(brief_desc) > 64:
            brief_desc = brief_desc[:61] + "..."

        price = normalize_price(parsed.get("price"))

        description = str(parsed.get("description", "")).strip()
        if not description:
            description = (
                f"{part_number} electronic component. Consult manufacturer datasheet for electrical "
                "specifications, pinout, voltage ratings, and recommended operating conditions."
            )

        # Enforce max description word count
        words = description.split()
        if len(words) > MAX_DESCRIPTION_WORDS:
            description = " ".join(words[:MAX_DESCRIPTION_WORDS]) + "..."

        label_data = {
            "comp_type": comp_type,
            "part_number": part_number,
            "mfr_part_number": mfr_part_number,
            "brief_desc": brief_desc,
            "category": DEFAULT_LABEL_CATEGORY,
            "decimal_pn": DEFAULT_LABEL_DATABASE_ID,
            "location": DEFAULT_LABEL_LOCATION,
            "price": price,
            "description": description,
        }

        logger.info("Deduced label data: [%s] %s %s | Price: %s",
                    comp_type, part_number, mfr_part_number, price)
        return label_data

    def identify_component_tuple(self, jpeg_bytes: bytes) -> Tuple[str, str]:
        """Legacy helper returning (part_number, description)."""
        data = self.identify_component(jpeg_bytes)
        return data["part_number"], data["description"]

