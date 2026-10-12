from app.models import parse_chapter_number
from app.scraper.cleaner import default_clean, is_spam


def test_parse_chapter_number():
    assert parse_chapter_number("Chapter 12 - O Retorno") == 12
    assert parse_chapter_number("Capítulo 3") == 3
    assert parse_chapter_number("45. Fim") == 45
    assert parse_chapter_number("Prólogo") is None
    assert parse_chapter_number(None) is None


def test_default_clean_keeps_text_escapes_and_drops_scripts():
    html = "<div><p>Olá &lt;mundo&gt;</p><script>alert(1)</script><p></p><p>Fim</p></div>"
    out = default_clean(html)
    assert "<p>Olá &lt;mundo&gt;</p>" in out
    assert "<p>Fim</p>" in out
    assert "alert" not in out


def test_is_spam_is_public_and_boolean():
    assert is_spam("Texto normal da história.") is False
