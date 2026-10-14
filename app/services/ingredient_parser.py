import re
from typing import List, Optional
from pydantic import BaseModel, Field

class ParsedIngredient(BaseModel):
    raw_text: str = Field(..., description="The raw substring as it appeared on the packaging label")
    clean_name: str = Field(..., description="Cleaned, lowercase ingredient name suitable for database alias matching")
    sub_ingredients: List[str] = Field(default_factory=list, description="Sub-ingredients found inside parentheses (e.g. 'palm oil' inside 'vegetable oil')")
    percentage: Optional[float] = Field(None, description="Percentage of ingredient if declared (e.g. 15.0 for '15%')")

class ParseResult(BaseModel):
    ingredients: List[ParsedIngredient] = Field(default_factory=list, description="List of parsed ingredients")
    allergens_declared: List[str] = Field(default_factory=list, description="Precautionary allergens separated from the main list (e.g. 'may contain traces of...')")
    contains_declared: List[str] = Field(default_factory=list, description="Allergens named in a 'Contains: milk, soy' statement (definite, unlike 'may contain')")
    discarded: List[str] = Field(default_factory=list, description="Fragments judged to be OCR/page noise (URLs, times, over-long text); not treated as ingredients")
    raw_input: str = Field(..., description="The original raw input string")

class IngredientParser:
    """
    Parses messy packaging labels and OCR text into structured ingredient tokens.
    Handles:
    - Stripping 'Ingredients:', 'Contains:', etc. prefixes
    - Separating 'May contain' advisory allergen warnings
    - Smart bracket splitting (avoids breaking sub-ingredients on internal commas)
    - Stripping percentages (e.g. '15%')
    - Removing bullet points, excess whitespace, and OCR artifacts
    """

    # Common prefix patterns to strip from the beginning of labels
    PREFIX_PATTERNS = [
        r"^(ingredients|active ingredients|inactive ingredients|composition|contains)\s*:\s*",
        r"^(ingredients|composition)\s*-\s*",
    ]

    # Anchor: ingredient lists start after the first "Ingredients" word (colon optional, OCR often drops it).
    INGREDIENTS_ANCHOR = re.compile(r"\bingredients?\b\s*[:\-]?\s*", re.IGNORECASE)

    # Noise detection (judgment values, tune with real scans).
    MAX_INGREDIENT_WORDS = 8
    NOISE_PATTERNS = [
        re.compile(r"https?://|www\.|\.(com|pk|in|org|net|co)\b", re.IGNORECASE),  # URLs / domains
        re.compile(r"\b\d{1,2}:\d{2}\b"),  # clock times from screenshots
    ]

    # Advisory statements (allergens) that typically appear at the end
    ADVISORY_PATTERNS = [
        r"(may contain traces of|may contain|allergen advice|manufactured in a facility that also processes|packed in a plant that handles)\s*[:\-]?\s*(.*)$",
    ]

    # A bullet is a separator: "• Water • Sugar" is two ingredients. A "*" only counts when it stands
    # alone ("* Sugar"); "sugar*" is a footnote marker and stays attached to its word.
    BULLET = re.compile(r"[•|]+|(?:(?<=\s)|^)\*+(?=\s|$)")

    # "Contains less than 2% of: salt" / "contains 2% or less of salt" only introduces more ingredients.
    LESS_THAN_INTRO = re.compile(r"\bcontains\s+(?:less than\s*)?\d+(?:\.\d+)?\s*%\s*(?:or less\s*)?(?:of\s*)?:?", re.IGNORECASE)

    @classmethod
    def clean_text(cls, text: str) -> str:
        """Turns bullets into commas, then newlines/tabs into spaces (a list wrapped over several
        lines must stay one list), and collapses spacing."""
        if not text:
            return ""
        cleaned = cls.BULLET.sub(",", text)
        cleaned = cls.LESS_THAN_INTRO.sub(", ", cleaned)
        cleaned = re.sub(r"[\n\r\t]+", " ", cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()

    @classmethod
    def strip_prefix(cls, text: str) -> str:
        """Strips leading 'Ingredients:', 'Contains:', etc."""
        cleaned = text
        for pattern in cls.PREFIX_PATTERNS:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()
        return cleaned

    @classmethod
    def extract_advisories(cls, text: str) -> tuple[str, List[str]]:
        """
        Extracts 'May contain traces of...' warning statements from the text.
        Returns (remaining_text, list_of_allergen_warnings).
        """
        allergens = []
        remaining = text

        for pattern in cls.ADVISORY_PATTERNS:
            match = re.search(pattern, remaining, flags=re.IGNORECASE)
            if match:
                advisory_text = match.group(2).strip()
                # Split advisory into items (e.g. "peanuts, tree nuts, milk")
                for item in re.split(r"[,;.]", advisory_text):
                    clean_item = item.strip().lower()
                    if clean_item and len(clean_item) > 1:
                        allergens.append(clean_item)
                # Remove the entire advisory clause from the main ingredients string
                remaining = remaining[:match.start()].strip()

        return remaining, allergens

    # "Contains: milk, soy" at top level and after some text. Not "contains less than 2% of: salt"
    # (that introduces ingredients) and not "(contains milk)" inside brackets.
    CONTAINS_CLAUSE = re.compile(
        r"(?<![\w(])contains\b(?!\s*(?:less than|\d+\s*%|[:\-]?\s*less than))\s*[:\-]?\s*(.*?)(?=\bmay contain\b|$)",
        re.IGNORECASE,
    )
    ALLERGEN_WORDS = {
        "milk", "egg", "eggs", "peanut", "peanuts", "soy", "soya", "soybean", "soybeans", "wheat", "gluten",
        "barley", "rye", "oats", "almond", "almonds", "hazelnut", "hazelnuts", "walnut", "walnuts", "cashew",
        "cashews", "pecan", "pecans", "pistachio", "pistachios", "macadamia", "brazil nuts", "nuts", "tree nuts",
        "fish", "shellfish", "crustaceans", "molluscs", "sesame", "sesame seeds", "mustard", "celery", "lupin",
        "sulphites", "sulfites", "sulphur dioxide",
    }

    @classmethod
    def extract_contains(cls, text: str) -> tuple[str, List[str]]:
        """Splits a 'Contains: milk and soy.' declaration off the list. Only known allergen words are kept
        (so 'Contains: store in a cool place' yields nothing). Returns (remaining_text, allergens)."""
        for match in cls.CONTAINS_CLAUSE.finditer(text):
            before = text[:match.start()]
            if before.count("(") > before.count(")") or not before.strip():
                continue  # inside brackets, or a leading 'Contains:' that starts the list (handled by strip_prefix)
            items = re.split(r"[,;.]|\band\b|&", re.sub(r"\(.*?\)", "", match.group(1)))
            found = [i.strip().lower() for i in items if i.strip().lower() in cls.ALLERGEN_WORDS]
            return (before + " " + text[match.end():]).strip(), list(dict.fromkeys(found))
        return text, []

    @classmethod
    def anchor_to_ingredients(cls, text: str) -> str:
        """Drops everything before the first 'Ingredients' word (page headers, clock times, URLs)."""
        match = cls.INGREDIENTS_ANCHOR.search(text)
        return text[match.end():] if match else text

    @classmethod
    def is_noise(cls, token: str, base_name: str) -> bool:
        """URL/time fragments, or a name far too long to be one ingredient.
        Word count uses the name outside brackets so long sub-ingredient lists are fine."""
        if any(p.search(token) for p in cls.NOISE_PATTERNS):
            return True
        return len(base_name.split()) > cls.MAX_INGREDIENT_WORDS

    @classmethod
    def split_top_level(cls, text: str) -> List[str]:
        """
        Splits on commas, semicolons, " & " and sentence periods (". ") ONLY when they are
        outside parentheses. Decimals like "2.5" are never split.
        Example:
          'Sugar, Flour (Wheat, Salt), Cocoa'
        Splits into:
          ['Sugar', 'Flour (Wheat, Salt)', 'Cocoa']
        (A standard text.split(',') would incorrectly break 'Wheat, Salt' into separate items!)
        """
        tokens = []
        current = []
        depth = 0

        for i, char in enumerate(text):
            nxt = text[i + 1] if i + 1 < len(text) else " "
            prev = text[i - 1] if i > 0 else " "
            if depth == 0 and (
                char in ",;"
                or (char == "." and nxt.isspace())          # sentence period, not 2.5 or Coco.Glucoside
                or (char == "&" and prev == " " and nxt == " ")  # "A & B" blends
            ):
                token = "".join(current).strip()
                if token:
                    tokens.append(token)
                current = []
            elif char in "([{":
                depth += 1
                current.append(char)
            elif char in ")]}":
                if depth > 0:
                    depth -= 1
                current.append(char)
            else:
                current.append(char)

        last_token = "".join(current).strip()
        if last_token:
            tokens.append(last_token)

        return tokens

    @classmethod
    def extract_sub_ingredients(cls, token: str) -> tuple[str, List[str]]:
        """
        Extracts sub-ingredients from brackets and returns the base name plus sub-items.
        Example:
          'Vegetable Oil (Palm Oil, Soybean Oil)'
          -> ('Vegetable Oil', ['palm oil', 'soybean oil'])
        """
        sub_items = []
        # Find everything inside the outer parentheses
        match = re.search(r"\((.*?)\)", token)
        if match:
            bracket_content = match.group(1).strip()
            # If the content is just a percentage (e.g. '15%') or E-number (e.g. 'E330'), don't treat as sub-ingredients
            if not re.match(r"^(\d+(\.\d+)?%|e\d+[a-z]?)$", bracket_content, flags=re.IGNORECASE):
                # Split sub-items by comma
                for sub in bracket_content.split(","):
                    sub_clean = sub.strip().lower()
                    if sub_clean:
                        sub_items.append(sub_clean)
            
            # Base name is everything outside the brackets
            base_name = token[:match.start()] + token[match.end():]
        else:
            base_name = token

        return base_name.strip(), sub_items

    @classmethod
    def extract_percentage(cls, token: str) -> tuple[str, Optional[float]]:
        """
        Detects and extracts percentages like '15%' or '2.5%' and removes them from the name.
        Example:
          'Cocoa Butter (15%)' -> ('Cocoa Butter', 15.0)
        """
        percentage = None
        match = re.search(r"(\d+(\.\d+)?)\s*%", token)
        if match:
            try:
                percentage = float(match.group(1))
            except ValueError:
                percentage = None
            # Remove the percentage from the text
            token = re.sub(r"\s*\(?\d+(\.\d+)?\s*%\)?", "", token)

        return token.strip(), percentage

    @classmethod
    def normalize_ingredient_token(cls, token: str) -> str:
        """Normalizes a single ingredient token for database lookup."""
        # Lowercase
        norm = token.lower()
        # Remove parentheses if they just contain an E-number or code, but keep the code searchable
        # E.g. 'Citric Acid (E330)' -> 'citric acid'
        norm = re.sub(r"\(.*?\)", "", norm)
        # Remove numbers at start (e.g. '1. Sugar' -> 'sugar')
        norm = re.sub(r"^\d+[\.\)]\s*", "", norm)
        # Remove extra punctuation
        norm = re.sub(r"[\.:;*]+", "", norm)
        # Clean extra spaces
        norm = re.sub(r"\s+", " ", norm).strip()
        return norm

    @classmethod
    def parse(cls, raw_text: str) -> ParseResult:
        """
        Main entry point: parses raw packaging text into structured ingredients.
        """
        if not raw_text or not raw_text.strip():
            return ParseResult(ingredients=[], allergens_declared=[], raw_input=raw_text or "")

        # 1. Clean basic spacing and newlines
        cleaned = cls.clean_text(raw_text)

        # 1b. Start after the first "Ingredients" word (removes page noise before the list)
        cleaned = cls.anchor_to_ingredients(cleaned)

        # 2. Extract 'Contains: ...' declarations, then advisory 'May contain...' warnings
        cleaned, contains = cls.extract_contains(cleaned)
        cleaned, allergens = cls.extract_advisories(cleaned)

        # 3. Strip 'Ingredients:' prefixes
        cleaned = cls.strip_prefix(cleaned)

        # 4. Smart bracket-aware split
        raw_tokens = cls.split_top_level(cleaned)

        parsed_items: List[ParsedIngredient] = []
        discarded: List[str] = []
        seen: set = set()

        for token in raw_tokens:
            token = token.strip()
            if not token or len(token) < 2:
                continue

            # Extract percentage if any
            token_without_pct, percentage = cls.extract_percentage(token)

            # Extract sub-ingredients in brackets
            base_name, sub_ingredients = cls.extract_sub_ingredients(token_without_pct)

            if cls.is_noise(token, base_name or token_without_pct):
                discarded.append(token[:120])
                continue

            # Clean name for matching
            clean_name = cls.normalize_ingredient_token(base_name if base_name else token_without_pct)

            if clean_name and clean_name not in seen:
                seen.add(clean_name)
                parsed_items.append(
                    ParsedIngredient(
                        raw_text=token,
                        clean_name=clean_name,
                        sub_ingredients=sub_ingredients,
                        percentage=percentage
                    )
                )

        return ParseResult(
            ingredients=parsed_items,
            allergens_declared=allergens,
            contains_declared=contains,
            discarded=discarded,
            raw_input=raw_text
        )

# Singleton helper instance
ingredient_parser = IngredientParser()
