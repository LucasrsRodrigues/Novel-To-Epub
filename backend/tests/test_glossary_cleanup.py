"""Limpeza do glossario + upsert por term_key."""

from starlette.testclient import TestClient

from app.api.server import create_app
from app.db.cache import ChapterCache
from app.models import ChapterContent, NovelMeta
from app.translation.glossary import GlossaryEntry, GlossaryStore, term_key
from app.translation.glossary_cleanup import apply_cleanup, plan_cleanup


def E(term, kind="other", source="llm", conf="medium", first=None, canonical=None):
    return GlossaryEntry(term=term, canonical_pt=canonical or term, kind=kind, source=source,
                         confidence=conf, first_seen_chapter=first)


def _novel_with_text(paragraphs: list[str]) -> int:
    cache = ChapterCache()
    nid = cache.upsert_novel("x", "n", NovelMeta(title="N", source_url="u", chapters=[]))
    html = "".join(f"<p>{p}</p>" for p in paragraphs)
    cache.save_chapter(nid, ChapterContent(index=1, title="Chapter 1", html=html, url="u/1"))
    return nid


def _insert(nid, entries):
    """Insere cru (sem o casamento por chave), simulando o glossario legado."""
    from app.db import models as orm
    from app.db.database import get_session

    with get_session() as s:
        for e in entries:
            s.add(orm.Glossary(novel_id=nid, term=e.term, canonical_pt=e.canonical_pt, kind=e.kind,
                               gender="n/a", notes="", confidence=e.confidence,
                               first_seen_chapter=e.first_seen_chapter, source=e.source))
        s.commit()


def test_term_key_merges_case_possessive_and_plural():
    assert term_key("Immortal Flame clan") == term_key("Immortal Flame Clans")
    assert term_key("Sunny's") == term_key("Sunny")
    assert term_key("Nephis") != term_key("Nephi")  # final "is" nao e plural
    assert term_key("Sunless") == ("sunless",)


def test_upsert_matches_existing_variant_instead_of_duplicating():
    nid = _novel_with_text(["x"])
    store = GlossaryStore()
    store.upsert_many(nid, [E("Immortal Flame Clan", conf="high")])
    added, updated = store.upsert_many(nid, [E("Immortal Flame clan", conf="high")])
    assert (added, updated) == (0, 1)
    assert len(store.list_for_novel(nid)) == 1


def test_cleanup_merges_duplicates_keeping_most_used_spelling():
    nid = _novel_with_text(["Aina smiled. Then Aina left.", "AIna"])
    _insert(nid, [E("AIna", "character"), E("Aina", "character"), E("Reflections"), E("Reflection")])
    plan = plan_cleanup(nid)
    kept = {k for k, _ in plan.merges}
    assert "Aina" in kept and plan.removed == 2


def test_cleanup_manual_entry_wins_merge():
    nid = _novel_with_text(["Spell Core"])
    _insert(nid, [E("Spell Cores"), E("Spell core", source="manual")])
    assert plan_cleanup(nid).merges == [("Spell core", ["Spell Cores"])]


def test_common_words_ignored_but_names_and_protected_entries_kept():
    text = ["the time passed and time flew, his body ached."] * 25 + [
        "Time stopped.",  # inicio de frase nao conta como nome
        "He looked at Rain and said that Rain was right, the rain fell.",
    ] * 3
    nid = _novel_with_text(text)
    _insert(nid, [
        E("Time", "system_term"),                 # comum → ignored
        E("Body", "ability", source="manual"),    # manual → intocado
        E("Rain", "character"),                   # personagem → intocado
        E("Am", "other"),                         # lixo (curto)
        E("AI", "system_term"),                   # sigla → fica
    ])
    plan = plan_cleanup(nid)
    assert plan.common == ["Time"] and plan.junk == ["Am"]
    apply_cleanup(plan)
    active = {e.term for e in GlossaryStore().list_for_novel(nid)}
    assert active == {"Body", "Rain", "AI"}
    again = plan_cleanup(nid).summary()  # idempotente
    assert again["common_words_ignored"] == 0 and again["already_ignored"] == 2
    assert again["remaining_active"] == 3


def test_ignored_term_cannot_be_revived_by_llm():
    nid = _novel_with_text(["the time " * 30])
    _insert(nid, [E("Time", "system_term")])
    apply_cleanup(plan_cleanup(nid))
    GlossaryStore().upsert_many(nid, [E("Time", "system_term", conf="high")])
    assert GlossaryStore().list_for_novel(nid) == []
    assert len(GlossaryStore().list_for_novel(nid, include_ignored=True)) == 1


def test_api_preview_then_apply():
    nid = _novel_with_text(["x"])
    _insert(nid, [E("Aspect"), E("Aspects")])
    with TestClient(create_app()) as c:
        preview = c.post(f"/api/library/{nid}/glossary/clean").json()
        assert preview["applied"] is False and preview["duplicates_removed"] == 1
        assert len(c.get(f"/api/library/{nid}/glossary").json()) == 2  # nada mudou
        applied = c.post(f"/api/library/{nid}/glossary/clean?apply=true").json()
        assert applied["applied"] is True
        assert len(c.get(f"/api/library/{nid}/glossary").json()) == 1
        assert c.post("/api/library/999/glossary/clean").status_code == 404


def test_merge_inherits_gender_and_notes_from_removed_variant():
    from app.db import models as orm
    from app.db.database import get_session

    nid = _novel_with_text(["Mira Mira Mira"])
    _insert(nid, [E("Mira", "character", conf="high"), E("Mira's", "character")])
    with get_session() as s:
        variant = s.query(orm.Glossary).filter_by(novel_id=nid, term="Mira's").one()
        variant.gender, variant.notes = "female", "irma do heroi"
        s.commit()
    apply_cleanup(plan_cleanup(nid))
    (mira,) = GlossaryStore().list_for_novel(nid)
    assert (mira.term, mira.gender, mira.notes) == ("Mira", "female", "irma do heroi")
