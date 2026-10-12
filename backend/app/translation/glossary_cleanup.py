"""Limpeza do glossario de uma novel: duplicatas, palavras comuns e lixo.

O glossario e alimentado pelo LLM a cada capitulo (``new_glossary_entries``) e,
ate a selecao por capitulo existir, o modelo quase nunca via os termos ja
cadastrados — entao re-cadastrava variantes e qualquer palavra com maiuscula.
Resultado medido: milhares de entradas, com centenas de duplicatas
("Reflection"/"Reflections", "Aina"/"AIna") e palavras comuns ("Time", "Body",
"Feel") que, agora que o glossario e respeitado, seriam mantidas em ingles.

Tres regras, todas conservadoras:

1. **Duplicatas** — entradas com o mesmo ``term_key`` (maiusculas, posse e
   plural simples) viram uma so. Fica a de origem manual > wiki > llm; empate
   → a grafia que mais aparece no texto da novel; depois maior confianca e a
   vista primeiro. As outras sao apagadas (o upsert ja casa por ``term_key``,
   entao nao voltam).
2. **Palavras comuns** — termo de UMA palavra, nao-personagem, de origem llm,
   que no texto da novel aparece em minuscula >= 20 vezes e com maiuscula NO
   MEIO da frase em no maximo 5% disso ("time" 10k vezes, "Time" no meio da
   frase 153). Personagem fica de fora de proposito: "Rain", "Hope", "Silence"
   sao nomes e palavras — ignorar um personagem perderia o genero dele.
   Viram ``ignored`` (nao apagadas): o LLM nao consegue re-adicionar.
3. **Lixo** — termo sem letra nenhuma ou curto demais pra casar com seguranca
   ("A", "Am"; siglas como "AI" ficam). Tambem ``ignored``.

Entradas ``manual`` e ``wiki`` nunca sao ignoradas nem apagadas por 2/3.
"""

from __future__ import annotations

import html
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from sqlalchemy import delete, select

from app.db import models as orm
from app.db.database import get_session, init_db
from app.translation.glossary import _CONF_RANK, _usable, term_key

_TAG = re.compile(r"<[^>]+>")
_CAP_WORD = re.compile(r"(?<![\w’'])([A-Za-z][a-z]+)(?!\w)")
# Antes destes, maiuscula e so inicio de frase/fala — nao conta como nome.
_SENTENCE_START = set('.!?"“”—:;…\'‘’(')
_SOURCE_RANK = {"manual": 3, "wiki": 2, "llm": 1}

MIN_LOWER = 20
MAX_CAP_RATIO = 0.05


@dataclass
class CleanupPlan:
    novel_id: int
    total: int = 0
    # (termo que fica, [termos apagados])
    merges: list[tuple[str, list[str]]] = field(default_factory=list)
    common: list[str] = field(default_factory=list)
    junk: list[str] = field(default_factory=list)
    already_ignored: int = 0  # de limpezas anteriores
    # ids por acao (pra aplicar sem reconsultar)
    _delete_ids: list[int] = field(default_factory=list, repr=False)
    _ignore_ids: list[int] = field(default_factory=list, repr=False)
    # id que fica → campos herdados das variantes apagadas (genero/notes vazios)
    _fill: dict[int, dict] = field(default_factory=dict, repr=False)

    @property
    def removed(self) -> int:
        return sum(len(dropped) for _, dropped in self.merges)

    def summary(self) -> dict:
        return {
            "novel_id": self.novel_id,
            "total": self.total,
            "duplicates_removed": self.removed,
            "common_words_ignored": len(self.common),
            "junk_ignored": len(self.junk),
            "already_ignored": self.already_ignored,
            "remaining_active": (
                self.total - self.removed - len(self.common) - len(self.junk)
                - self.already_ignored
            ),
            "merges": [{"kept": k, "removed": d} for k, d in self.merges],
            "common_words": self.common,
            "junk": self.junk,
        }


def _corpus_counts(novel_id: int) -> tuple[Counter, Counter, Counter]:
    """(minusculas, maiuscula no meio da frase, grafia exata) no texto da novel."""
    lower: Counter = Counter()
    cap_mid: Counter = Counter()
    exact: Counter = Counter()
    with get_session() as s:
        htmls = s.scalars(select(orm.Chapter.html).where(orm.Chapter.novel_id == novel_id))
        for raw in htmls:
            text = html.unescape(_TAG.sub(" ", raw))
            for m in _CAP_WORD.finditer(text):
                w = m.group(1)
                exact[w] += 1
                if w[0].islower():
                    lower[w] += 1
                    continue
                prev = text[: m.start()].rstrip()[-1:]
                if prev and prev not in _SENTENCE_START:
                    cap_mid[w] += 1
    return lower, cap_mid, exact


def _is_common_word(row: orm.Glossary, lower: Counter, cap_mid: Counter) -> bool:
    term = row.term.strip()
    if row.source != "llm" or row.kind == "character":
        return False
    if " " in term or not term.isalpha() or not term[0].isupper():
        return False
    lo = lower[term.lower()]
    return lo >= MIN_LOWER and cap_mid[term] <= MAX_CAP_RATIO * lo


def _is_junk(row: orm.Glossary) -> bool:
    if row.source != "llm":
        return False
    term = row.term.strip()
    return not _usable(term) or not any(ch.isalpha() for ch in term)


def plan_cleanup(novel_id: int) -> CleanupPlan:
    """Calcula o que a limpeza faria, sem alterar nada."""
    init_db()
    lower, cap_mid, exact = _corpus_counts(novel_id)
    with get_session() as s:
        rows = list(s.scalars(select(orm.Glossary).where(orm.Glossary.novel_id == novel_id)))
    plan = CleanupPlan(novel_id=novel_id, total=len(rows))

    groups: dict[tuple, list[orm.Glossary]] = defaultdict(list)
    for r in rows:
        groups[term_key(r.term) or (r.term,)].append(r)

    survivors: list[orm.Glossary] = []
    for group in groups.values():
        if len(group) == 1:
            survivors.append(group[0])
            continue
        group.sort(
            key=lambda r: (
                -_SOURCE_RANK.get(r.source, 0),
                -exact[r.term],
                -_CONF_RANK.get(r.confidence, 0),
                r.first_seen_chapter if r.first_seen_chapter is not None else 10**9,
                r.id,
            )
        )
        keep, *drop = group
        survivors.append(keep)
        plan.merges.append((keep.term, [d.term for d in drop]))
        plan._delete_ids.extend(d.id for d in drop)
        # Nao perde informacao: genero/notes que so a variante apagada tinha
        # passam pra entrada que fica.
        fill = {}
        if keep.gender in ("unknown", "n/a", None, ""):
            g = next((d.gender for d in drop if d.gender in ("male", "female", "non-binary")), None)
            if g and keep.kind == "character":
                fill["gender"] = g
        if not (keep.notes or "").strip():
            n = next((d.notes for d in drop if (d.notes or "").strip()), None)
            if n:
                fill["notes"] = n
        if fill:
            plan._fill[keep.id] = fill

    for r in survivors:
        if r.ignored:
            plan.already_ignored += 1
            continue
        if _is_junk(r):
            plan.junk.append(r.term)
            plan._ignore_ids.append(r.id)
        elif _is_common_word(r, lower, cap_mid):
            plan.common.append(r.term)
            plan._ignore_ids.append(r.id)

    plan.merges.sort(key=lambda m: m[0].lower())
    plan.common.sort(key=lambda t: -lower[t.lower()])
    return plan


def apply_cleanup(plan: CleanupPlan) -> None:
    """Aplica um plano de ``plan_cleanup`` (apaga duplicatas, marca ignored)."""
    with get_session() as s:
        if plan._delete_ids:
            s.execute(delete(orm.Glossary).where(orm.Glossary.id.in_(plan._delete_ids)))
        for row_id, fields in plan._fill.items():
            row = s.get(orm.Glossary, row_id)
            if row is not None:
                for k, v in fields.items():
                    setattr(row, k, v)
        if plan._ignore_ids:
            for r in s.scalars(select(orm.Glossary).where(orm.Glossary.id.in_(plan._ignore_ids))):
                r.ignored = True
        s.commit()
