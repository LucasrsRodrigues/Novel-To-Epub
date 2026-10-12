"""Glossario por novel: dataclass de entrada + repositorio SQLite.

O glossario eh o coracao da traducao consistente: cada personagem mencionado
ganha uma entrada com genero, e o tradutor injeta isso no system prompt todo
capitulo. Sem isso, o modelo chuta genero a cada capitulo e contradiz a si
proprio em PT-BR (onde tudo eh marcado).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select

from app.db import models as orm
from app.db.database import get_session, init_db

EntryKind = Literal["character", "place", "ability", "system_term", "other"]
Gender = Literal["male", "female", "non-binary", "unknown", "n/a"]
Confidence = Literal["high", "medium", "low"]
Source = Literal["llm", "wiki", "manual"]


@dataclass
class GlossaryEntry:
    term: str
    canonical_pt: str
    kind: str = "other"
    gender: str = "n/a"
    notes: str = ""
    confidence: str = "medium"
    first_seen_chapter: int | None = None
    source: str = "llm"


def _row_to_entry(row: orm.Glossary) -> GlossaryEntry:
    return GlossaryEntry(
        term=row.term,
        canonical_pt=row.canonical_pt,
        kind=row.kind,
        gender=row.gender,
        notes=row.notes or "",
        confidence=row.confidence,
        first_seen_chapter=row.first_seen_chapter,
        source=row.source,
    )


_CONF_RANK = {"high": 3, "medium": 2, "low": 1}

# ------------------------------------------------------------ selecao por cap
# Glossarios de novel longa passam de milhares de termos (8.6k em Dimensional
# Descent), mas o prompt so comporta ~8k chars (~80 entradas). Mandar "os
# primeiros 80 por tipo + ordem alfabetica" cobria 1-4% dos termos que de fato
# apareciam no capitulo. Aqui escolhemos os termos PRESENTES no texto (busca
# lexical exata — embeddings sao ruins justamente pra nome proprio inventado) e
# completamos com o elenco principal.

_KIND_PRIORITY = {
    "character": 0, "place": 1, "ability": 2, "organization": 3, "system_term": 4, "other": 5,
}
_WORD = re.compile(r"[^\W_]+(?:['’][^\W_]+)*")
_TAG = re.compile(r"<[^>]+>")
# Personagens sempre incluidos mesmo sem aparecer no capitulo (pronomes/voz do
# elenco principal), quando sobra espaco.
CORE_CAST = 30
_MAX_TERM_WORDS = 8


def _words(text: str) -> list[str]:
    """Palavras normalizadas: minusculas, sem posse inglesa ("Sunny's" → "sunny")."""
    out = []
    for w in _WORD.findall(text.lower()):
        if w.endswith(("'s", "’s")):
            w = w[:-2]
        out.append(w)
    return out


def _usable(term: str) -> bool:
    """Termo curto demais casaria qualquer texto ("A", "Am"); siglas ("AI") valem."""
    t = term.strip()
    return len(t) >= 3 or (len(t) == 2 and t.isupper())


def select_for_chapter(
    entries: list[GlossaryEntry], chapter_text: str, *, core_cast: int = CORE_CAST
) -> list[GlossaryEntry]:
    """Entradas do glossario relevantes pra ESTE capitulo, em ordem de prioridade.

    1. Termos que aparecem no texto (titulo + HTML do capitulo), por tipo
       (character, place, ability...). Casamento por sequencia de palavras,
       sem diferenciar maiusculas e ignorando posse ("Sunny's" casa "Sunny").
    2. Depois, ate ``core_cast`` personagens que nao apareceram — os vistos
       primeiro na novel (elenco principal), maior confianca antes.

    A ordem importa: se o prompt precisar cortar, corta do fim (o enchimento),
    nunca um termo do capitulo.
    """
    words = _words(html.unescape(_TAG.sub(" ", chapter_text)))
    keyed = [(e, tuple(_words(e.term))) for e in entries if _usable(e.term)]
    longest = min(_MAX_TERM_WORDS, max((len(k) for _, k in keyed), default=1))
    grams = {
        tuple(words[i:i + n])
        for n in range(1, longest + 1)
        for i in range(len(words) - n + 1)
    }
    matched = [e for e, k in keyed if k and k in grams]
    matched.sort(key=lambda e: (_KIND_PRIORITY.get(e.kind, 99), e.term.lower()))

    seen = {id(e) for e in matched}
    cast = [e for e in entries if e.kind == "character" and id(e) not in seen]
    cast.sort(key=lambda e: (
        e.first_seen_chapter if e.first_seen_chapter is not None else 10**9,
        -_CONF_RANK.get(e.confidence, 0),
        e.term.lower(),
    ))
    return matched + cast[:core_cast]


class GlossaryStore:
    def __init__(self) -> None:
        init_db()

    def list_for_novel(self, novel_id: int) -> list[GlossaryEntry]:
        with get_session() as s:
            rows = s.scalars(
                select(orm.Glossary)
                .where(orm.Glossary.novel_id == novel_id)
                .order_by(orm.Glossary.kind, orm.Glossary.term)
            ).all()
            return [_row_to_entry(r) for r in rows]

    def upsert_many(
        self,
        novel_id: int,
        entries: list[GlossaryEntry],
        *,
        first_seen_chapter: int | None = None,
    ) -> tuple[int, int]:
        """Insere os termos novos, atualiza os existentes.

        Politica: nao rebaixa confianca. Se ja temos uma entrada `high` e o LLM
        propos `low`, mantemos a high (e ignoramos a atualizacao). Edicao manual
        do usuario (source=manual) tambem nunca eh sobrescrita pelo LLM.

        Retorna ``(adicionadas, atualizadas)``.
        """
        added = updated = 0
        with get_session() as s:
            for entry in entries:
                row = s.scalar(
                    select(orm.Glossary).where(
                        orm.Glossary.novel_id == novel_id,
                        orm.Glossary.term == entry.term,
                    )
                )
                if row is None:
                    row = orm.Glossary(
                        novel_id=novel_id,
                        term=entry.term,
                        first_seen_chapter=first_seen_chapter,
                    )
                    s.add(row)
                    _apply(row, entry)
                    added += 1
                    continue

                if row.source == "manual":
                    continue  # nunca sobrescreve edicao manual
                if _CONF_RANK.get(entry.confidence, 0) < _CONF_RANK.get(row.confidence, 0):
                    continue  # nao rebaixa
                _apply(row, entry)
                updated += 1
            s.commit()
        return added, updated


def _apply(row: orm.Glossary, entry: GlossaryEntry) -> None:
    row.canonical_pt = entry.canonical_pt
    row.kind = entry.kind
    row.gender = entry.gender
    row.notes = entry.notes or ""
    row.confidence = entry.confidence
    row.source = entry.source
