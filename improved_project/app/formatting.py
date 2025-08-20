# app/formatting.py
import re

_ALLOWED = ("b","strong","i","em","u","ins","s","strike","del","a","code","pre")

def sanitize_html(text: str) -> str:
    if not text:
        return ""
    t = text
    # <br> -> \n
    t = re.sub(r"(?i)<br\s*/?>", "\n", t)
    # remove tags except whitelist
    t = re.sub(rf"(?is)</?(?!{'|'.join(_ALLOWED)})\w+[^>]*>", "", t)
    # only http/https links
    t = re.sub(r'(?is)<a\s+[^>]*href\s*=\s*"(?!(?:https?://))[^"]*"[^>]*>(.*?)</a>', r"\1", t)
    # normalize newlines
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t


def ensure_min_words(text: str, min_words: int = 10) -> str:
    """Ensure bot replies contain at least `min_words` words.

    Adds a neutral suffix repeatedly until threshold is reached to
    keep messages natural and non-spammy.
    """
    if not text:
        return ""
    words = re.findall(r"\b\w+\b", text, flags=re.UNICODE)
    if len(words) >= min_words:
        return text
    suffix = " Пожалуйста, дайте знать, если нужна дополнительная информация."
    result = text
    while len(re.findall(r"\b\w+\b", result)) < min_words:
        result += suffix
    return result