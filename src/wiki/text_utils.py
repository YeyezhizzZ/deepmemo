import re

def normalize_lookup(value: str) -> str:
    """
    Normalize lookup values for indexing and fuzzy matching.
    Replaces whitespace, slashes, dashes, dots, and underscores with spaces,
    and strips the result after converting to lowercase.
    """
    return re.sub(r"[\s_/\\.-]+", " ", value.strip().lower()).strip()
