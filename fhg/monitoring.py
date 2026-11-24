"""Error tracking that never sends health data.

With FHG_SENTRY_DSN set, unhandled errors go to Sentry (or any Sentry-compatible service, e.g. GlitchTip) with the
stack trace only: request bodies, headers, cookies, query strings, user details, local variables and breadcrumbs are
removed before anything leaves the server.
"""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger(__name__)


def scrub(event: dict, hint: Optional[dict] = None) -> dict:
    """Keep what's needed to fix a bug (exception type, message, stack, route) and drop anything personal."""
    request = event.get("request") or {}
    event["request"] = {"method": request.get("method"), "url": (request.get("url") or "").split("?")[0]}
    for key in ("user", "breadcrumbs", "extra", "contexts_user"):
        event.pop(key, None)
    for exc in (event.get("exception") or {}).get("values") or []:
        for frame in (exc.get("stacktrace") or {}).get("frames") or []:
            frame.pop("vars", None)
    for thread in (event.get("threads") or {}).get("values") or []:
        for frame in (thread.get("stacktrace") or {}).get("frames") or []:
            frame.pop("vars", None)
    return event


def init(dsn: Optional[str], environment: str, release: Optional[str] = None) -> bool:
    if not dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(dsn=dsn, environment=environment, release=release, traces_sample_rate=0.0,
                    max_request_body_size="never", before_send=scrub, max_breadcrumbs=0)
    log.info("error tracking on (%s)", environment)
    return True
