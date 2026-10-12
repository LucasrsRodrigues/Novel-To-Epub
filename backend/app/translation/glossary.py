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
    ignored: bool = False


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
        ignored=bool(row.ignored),
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


# Finais que parecem plural mas nao sao ("Sunless", "Chaos", "Nephis", "Atlas").
_NOT_PLURAL = ("ss", "us", "is", "as", "os")


def _norm_word(w: str) -> str:
    if w.endswith(("'s", "’s")):  # posse inglesa: "Sunny's" → "sunny"
        w = w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith(_NOT_PLURAL):
        w = w[:-1]  # plural simples: "Reflections" → "reflection"
    return w


def _words(text: str) -> list[str]:
    """Palavras normalizadas (minusculas, sem posse, sem plural simples)."""
    return [_norm_word(w) for w in _WORD.findall(text.lower())]


def term_key(term: str) -> tuple[str, ...]:
    """Chave de identidade de um termo: "Immortal Flame clan", "Immortal Flame
    Clans" e "immortal flame clan's" sao o MESMO termo. Usada pra casar o termo
    no texto do capitulo e pra o upsert nao criar variantes duplicadas."""
    return tuple(_words(term))


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
    keyed = [(e, term_key(e.term)) for e in entries if _usable(e.term) and not e.ignored]
    longest = min(_MAX_TERM_WORDS, max((len(k) for _, k in keyed), default=1))
    grams = {
        tuple(words[i:i + n])
        for n in range(1, longest + 1)
        for i in range(len(words) - n + 1)
    }
    matched = [e for e, k in keyed if k and k in grams]
    matched.sort(key=lambda e: (_KIND_PRIORITY.get(e.kind, 99), e.term.lower()))

    seen = {id(e) for e in matched}
    cast = [e for e in entries if e.kind == "character" and not e.ignored and id(e) not in seen]
    cast.sort(key=lambda e: (
        e.first_seen_chapter if e.first_seen_chapter is not None else 10**9,
        -_CONF_RANK.get(e.confidence, 0),
        e.term.lower(),
    ))
    return matched + cast[:core_cast]


class GlossaryStore:
    def __init__(self) -> None:
        init_db()

    def list_for_novel(
        self, novel_id: int, *, include_ignored: bool = False
    ) -> list[GlossaryEntry]:
        """Glossario da novel. Termos ``ignored`` (palavra comum/lixo) ficam de
        fora — nao vao pro prompt nem pra tela — a menos que pedidos."""
        with get_session() as s:
            q = select(orm.Glossary).where(orm.Glossary.novel_id == novel_id)
            if not include_ignored:
                q = q.where(orm.Glossary.ignored.is_not(True))
            rows = s.scalars(q.order_by(orm.Glossary.kind, orm.Glossary.term)).all()
            return [_row_to_entry(r) for r in rows]

    def upsert_many(
        self,
        novel_id: int,
        entries: list[GlossaryEntry],
        *,
        first_seen_chapter: int | None = None,
    ) -> tuple[int, int]:
        """Insere os termos novos, atualiza os existentes.

        Termos sao identificados por ``term_key`` (maiusculas/posse/plural nao
        criam entrada nova). Politica: nao rebaixa confianca. Se ja temos uma entrada `high` e o LLM
        propos `low`, mantemos a high (e ignoramos a atualizacao). Edicao manual
        do usuario (source=manual) tambem nunca eh sobrescrita pelo LLM.

        Retorna ``(adicionadas, atualizadas)``.
        """
        added = updated = 0
        with get_session() as s:
            # Casa por term_key, nao pelo texto exato: "Immortal Flame clan" ou
            # "Reflections" atualizam a entrada ja existente em vez de criar uma
            # variante (era assim que o glossario acumulava duplicatas). Termo
            # ignorado continua ignorado — o LLM nao consegue "ressuscitar".
            by_key = {
                term_key(r.term): r
                for r in s.scalars(
                    select(orm.Glossary).where(orm.Glossary.novel_id == novel_id)
                )
            }
            for entry in entries:
                key = term_key(entry.term)
                row = by_key.get(key) if key else None
                if row is None:
                    row = orm.Glossary(
                        novel_id=novel_id,
                        term=entry.term,
                        first_seen_chapter=first_seen_chapter,
                    )
                    s.add(row)
                    _apply(row, entry)
                    if key:
                        by_key[key] = row
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
