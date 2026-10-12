"""Selecao do glossario por capitulo + formatacao com orcamento."""

from app.translation.gemini_provider import _format_glossary
from app.translation.glossary import GlossaryEntry, select_for_chapter


def E(term, kind="other", first=None, notes="", conf="medium"):
    return GlossaryEntry(term=term, canonical_pt=term, kind=kind, notes=notes,
                         first_seen_chapter=first, confidence=conf)


def terms(entries):
    return [e.term for e in entries]


def test_selects_only_terms_in_chapter_with_case_possessive_and_multiword():
    gl = [E("Sunny", "character"), E("Spell Core", "system_term"), E("Nephis", "character"),
          E("Forgotten Shore", "place"), E("Cassie", "character")]
    text = "<p>SUNNY'S shadow touched the spell core.</p><p>Far from the Forgotten Shore.</p>"
    sel = select_for_chapter(gl, text, core_cast=0)
    assert terms(sel) == ["Sunny", "Forgotten Shore", "Spell Core"]  # por tipo


def test_multiword_term_needs_the_whole_sequence():
    sel = select_for_chapter([E("Spell Core")], "<p>a spell and a core</p>", core_cast=0)
    assert sel == []


def test_short_terms_ignored_except_acronyms():
    gl = [E("A", "character"), E("Am", "character"), E("AI", "system_term")]
    sel = select_for_chapter(gl, "<p>A man am the AI.</p>", core_cast=0)
    assert terms(sel) == ["AI"]


def test_core_cast_fills_after_chapter_terms_ordered_by_first_seen():
    gl = [E("Late", "character", first=90), E("Hero", "character", first=1),
          E("Rival", "character", first=5), E("Sword", "ability"), E("City", "place", first=1)]
    sel = select_for_chapter(gl, "<p>Sword</p>", core_cast=2)
    assert terms(sel) == ["Sword", "Hero", "Rival"]  # places nao entram no enchimento


def test_html_tags_and_entities_are_ignored():
    sel = select_for_chapter([E("Mordret", "character"), E("span", "other")],
                             '<p class="x"><span>Mordret&#8217;s</span></p>', core_cast=0)
    assert terms(sel) == ["Mordret"]


def test_format_keeps_given_order_and_drops_notes_before_entries():
    chapter = [E(f"Term{i}", "other", notes="n" * 200) for i in range(40)]
    filler = [E(f"Cast{i}", "character", notes="x" * 200) for i in range(40)]
    text = _format_glossary(chapter + filler, max_chars=1800)
    lines = [ln for ln in text.splitlines() if ln.startswith("- ")]
    assert lines[0].startswith("- Term0 ")  # nao reordena por tipo
    assert all(f"- Term{i} " in text for i in range(40))  # cap inteiro coube...
    assert "nnn" not in text  # ...porque as notes sairam antes
    assert "omitidas" in text and "- Cast39 " not in text  # o corte foi no enchimento
