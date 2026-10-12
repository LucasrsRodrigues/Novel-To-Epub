"""Custos/uso de IA e diagnostico da traducao."""

from __future__ import annotations


from fastapi import APIRouter

from app.api.schemas import (
    RecentUsageInfo,
    TranslationDebugStatus,
    UsageByNovel,
    UsageByProvider,
    UsageDay,
    UsageSummary,
    VolumePinInfo,
)
from app.db.database import get_session
from app.db import models as orm
from sqlalchemy import select
from app.db.settings_store import SettingsStore
from app.db.usage_store import UsageStore

router = APIRouter()


@router.get("/usage/summary", response_model=UsageSummary)
def usage_summary() -> dict:
    return UsageStore().summary()


@router.get("/usage/by-day", response_model=list[UsageDay])
def usage_by_day(days: int = 30) -> list[dict]:
    return UsageStore().by_day(days=max(1, min(days, 365)))


@router.get("/usage/by-novel", response_model=list[UsageByNovel])
def usage_by_novel() -> list[dict]:
    return UsageStore().by_novel()


@router.get("/usage/by-provider", response_model=list[UsageByProvider])
def usage_by_provider() -> list[dict]:
    return UsageStore().by_provider()


@router.get("/debug/translation-status", response_model=TranslationDebugStatus)
def translation_debug_status() -> TranslationDebugStatus:
    """Snapshot do estado: quais providers estão configurados, qual ordem,
    quais pins existem (volume → provider gravado), e últimas 20 chamadas
    de tradução. Usado pra diagnosticar 'meu cascade só usa Gemini'."""
    from app.translation.factory import _read_keys

    cfg = SettingsStore().get()
    keys = _read_keys(cfg)
    active = [name for name, key in keys.items() if key]
    inactive = [name for name, key in keys.items() if not key]

    raw_order = cfg.get("cascade_order") or "groq,openrouter,cerebras,gemini"
    order = (
        [p.strip() for p in raw_order.split(",") if p.strip()]
        if isinstance(raw_order, str)
        else list(raw_order)
    )

    # Pins
    with get_session() as s:
        pin_rows = s.execute(
            select(orm.VolumeTranslatorPin, orm.Novel.title)
            .outerjoin(orm.Novel, orm.Novel.id == orm.VolumeTranslatorPin.novel_id)
            .order_by(orm.VolumeTranslatorPin.created_at.desc())
        ).all()
    pins = [
        VolumePinInfo(
            novel_id=p.novel_id, novel_title=t or "(desconhecida)",
            volume_title=p.volume_title or None, language=p.language,
            provider=p.provider, model=p.model, created_at=p.created_at,
        )
        for (p, t) in pin_rows
    ]

    # Últimas 20 chamadas
    with get_session() as s:
        recent_rows = s.scalars(
            select(orm.GeminiUsage)
            .order_by(orm.GeminiUsage.created_at.desc())
            .limit(20)
        ).all()
    recent = [
        RecentUsageInfo(
            op=r.op, provider=r.provider, model=r.model,
            novel_id=r.novel_id, chapter_index=r.chapter_index,
            cost_usd=r.cost_usd, error_message=r.error_message,
            created_at=r.created_at,
        )
        for r in recent_rows
    ]

    return TranslationDebugStatus(
        active_providers=active, inactive_providers=inactive,
        cascade_order=order, pins=pins, recent_usage=recent,
    )
