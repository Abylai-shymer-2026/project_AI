# app/formatting.py
import re

_ALLOWED = ("b","strong","i","em","u","ins","s","strike","del","a","code","pre")

def sanitize_html(text: str) -> str:
    if not text:
        return ""
    t = text
    # <br> -> \n
    t = re.sub(r"(?i)<br\s*/?>", "\n", t)
    # убираем теги, кроме белого списка
    t = re.sub(rf"(?is)</?(?!{'|'.join(_ALLOWED)})\w+[^>]*>", "", t)
    # ссылки только http/https
    t = re.sub(r'(?is)<a\s+[^>]*href\s*=\s*"(?!(?:https?://))[^"]*"[^>]*>(.*?)</a>', r"\1", t)
    # нормализация переносов
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t
