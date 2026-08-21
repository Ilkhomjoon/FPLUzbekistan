"""FPLUzbekistan Telegram avtomatlashtirish boti."""

import sys

__version__ = "1.0.0"

# Windows konsoli standart holatda cp866/cp1251 ishlatadi va emoji (🚨) chop etishda
# UnicodeEncodeError beradi. Chiqishni majburan UTF-8 ga o'tkazamiz.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # eski Python yoki oddiy fayl bo'lsa — e'tibor bermaymiz
        pass
