"""
Text utility functions for sanitizing device names.
"""
import unicodedata


def sanitize_device_name(name: str) -> str:
    """
    Sanitize device/zone name by normalizing unicode characters.

    Replaces:
    - Curly quotes (' ' " ") with straight quotes (' ")
    - Other smart punctuation with ASCII equivalents

    Args:
        name: Raw device/zone name from API

    Returns:
        Sanitized name

    Examples:
        >>> sanitize_device_name("Master's Bedroom")
        "Master's Bedroom"
        >>> sanitize_device_name("Living\u2013Room")  # En dash
        "Living-Room"
    """
    if not name:
        return name

    # Replace curly quotes with straight quotes
    replacements = {
        '\u2018': "'",  # Left single quote
        '\u2019': "'",  # Right single quote
        '\u201c': '"',  # Left double quote
        '\u201d': '"',  # Right double quote
        '\u2013': '-',  # En dash
        '\u2014': '-',  # Em dash
    }

    for old, new in replacements.items():
        name = name.replace(old, new)

    # Normalize to NFKC (compatibility decomposition + canonical composition)
    name = unicodedata.normalize('NFKC', name)

    return name


# Alias for backward compatibility
sanitize_zone_name = sanitize_device_name
