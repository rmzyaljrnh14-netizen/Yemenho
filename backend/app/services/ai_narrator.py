"""Optional language-model narrator for the assistant (v0.8).

This is deliberately the *smallest* possible piece. The analysis is done by
``insights`` with plain arithmetic; this module only asks a language model to
turn those already-computed findings into a smoother paragraph. Consequences:

  * it is **off by default** (``YHQ_AI_ENABLED`` must be set true and a key
    supplied). With no model the assistant still works and returns the computed
    findings verbatim;
  * it only ever receives the finished finding texts and their basis numbers —
    never raw tables — so it cannot introduce a fact that is not already there;
  * its system prompt forbids inventing numbers, causes or medical claims;
  * any network error, timeout or unexpected shape returns ``None`` and the
    caller falls back to the deterministic Arabic text. It never raises.
"""
from __future__ import annotations

import json

import httpx

from app.core.config import get_settings

SYSTEM_PROMPT_AR = (
    "أنت مُحرِّر تقارير صحية. مهمتك الوحيدة إعادة صياغة النتائج الجاهزة أدناه في فقرات عربية واضحة. "
    "قواعد صارمة: (١) استخدم فقط الأرقام والحقائق الواردة في المدخل ولا تضف أي رقم جديد؛ "
    "(٢) لا تختلق أسباباً طبية ولا تشخيصاً ولا حكماً؛ (٣) لا تذكر أي مستشفى أو مؤشر غير موجود في المدخل؛ "
    "(٤) إن كانت المعلومة ناقصة فقل ذلك صراحة؛ (٥) أبقِ الجملة التنبيهية في النهاية. "
    "أعد النص العربي فقط دون أي مقدمات."
)


def is_configured() -> bool:
    s = get_settings()
    return bool(s.ai_enabled and s.ai_api_key and s.ai_model and s.ai_base_url)


def _build_user_message(payload: dict) -> str:
    return (
        "هذه نتائج محسوبة آلياً بصيغة JSON. أعد صياغتها في فقرات عربية منظمة دون إضافة أي معلومة:\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def narrate(payload: dict, *, client: httpx.Client | None = None) -> str | None:
    """Return an Arabic narrative, or None when no model is available/failed.

    ``client`` is injectable so tests can exercise the request/response handling
    without any network. Never raises.
    """
    if not is_configured():
        return None
    s = get_settings()
    body = {
        "model": s.ai_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT_AR},
            {"role": "user", "content": _build_user_message(payload)},
        ],
        "temperature": 0.2,
    }
    headers = {"Authorization": f"Bearer {s.ai_api_key}", "Content-Type": "application/json"}
    url = f"{s.ai_base_url.rstrip('/')}/chat/completions"
    owned = client is None
    http = client or httpx.Client(timeout=s.ai_timeout_seconds)
    try:
        resp = http.post(url, json=body, headers=headers)
        if resp.status_code != 200:
            return None
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        if not isinstance(text, str) or not text.strip():
            return None
        return text.strip()
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
        return None
    finally:
        if owned:
            http.close()
