from __future__ import annotations

import json
import inspect
import html as html_lib
import ipaddress
import os
import platform
import psutil
import re
import shutil
import socket
import subprocess
import uuid
from urllib.parse import quote_plus, urlparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple, Optional
import xml.etree.ElementTree as ET

import httpx

from app.config import settings
from app.secrets import decrypt_text
from app.database import memory_store, memory_recall, get_tool_stats

import logging
import asyncio
logger = logging.getLogger(__name__)


import os
import re
import json


from datetime import datetime




def tool_create_email_draft(to: str, subject: str, body: str) -> Dict[str, Any]:
    draft_id = str(uuid.uuid4())[:8]
    draft_path = _resolve_inside_workspace(f"mail/drafts/{draft_id}.txt")
    content = f"To: {to}\nSubject: {subject}\n\n{body}\n"
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(content, encoding="utf-8")
    return {"draft_id": draft_id, "path": str(draft_path)}

def tool_check_gmail_messages(max_results: int = 10, query: str = "", **kwargs: Any) -> Dict[str, Any]:
    token = _get_secret_token(settings.gmail_access_token, settings.gmail_access_token_enc)
    if not token:
        token = _refresh_gmail_access_token()
    if not token:
        raise ValueError("Gmail token missing. Set access token or configure OAuth refresh token + client id.")
    limit = max(1, min(max_results, 20))
    today_query = _gmail_today_query()
    custom_query = (query or "").strip()
    if not custom_query:
        effective_query = today_query
    elif "after:" in custom_query.lower() or "before:" in custom_query.lower():
        effective_query = custom_query
    else:
        # Varsayilan olarak daima bugune kilitle.
        effective_query = f"({custom_query}) {today_query}"
    ignored_kwargs = {k: v for k, v in kwargs.items() if k not in {"query", "max_results"}}
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=30) as client:
        list_resp = client.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            params={"q": effective_query, "maxResults": limit},
            headers=headers,
        )
        if list_resp.status_code == 401:
            refreshed = _refresh_gmail_access_token()
            if refreshed:
                token = refreshed
                headers = {"Authorization": f"Bearer {token}"}
                list_resp = client.get(
                    "https://gmail.googleapis.com/gmail/v1/users/me/messages",
                    params={"q": effective_query, "maxResults": limit},
                    headers=headers,
                )
        if list_resp.status_code == 401:
            body_preview = list_resp.text[:300]
            raise ValueError(
                "Gmail 401 Unauthorized. Access token gecersiz/suresi dolmus olabilir. "
                f"API cevabi: {body_preview}"
            )
        list_resp.raise_for_status()
        ids = [m["id"] for m in list_resp.json().get("messages", [])]
        results = []
        for mid in ids:
            msg_resp = client.get(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{mid}",
                params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
                headers=headers,
            )
            msg_resp.raise_for_status()
            payload = msg_resp.json()
            headers_list = payload.get("payload", {}).get("headers", [])
            hmap = {h.get("name", "").lower(): h.get("value", "") for h in headers_list}
            results.append(
                {
                    "id": mid,
                    "from": hmap.get("from", ""),
                    "subject": hmap.get("subject", ""),
                    "date": hmap.get("date", ""),
                    "snippet": payload.get("snippet", ""),
                }
            )
    payload: Dict[str, Any] = {"count": len(results), "messages": results, "query": effective_query}
    if ignored_kwargs:
        payload["ignored_arguments"] = sorted(ignored_kwargs.keys())
    return payload

def tool_check_outlook_messages(
    max_results: int = 10,
    unread_only: bool = True,
    today_only: bool = True,
    **kwargs: Any,
) -> Dict[str, Any]:
    token = _get_secret_token(settings.outlook_access_token, settings.outlook_access_token_enc)
    if not token:
        token = _refresh_outlook_access_token()
    if not token:
        raise ValueError("Outlook token missing. Set access token or configure OAuth refresh token + client id.")
    limit = max(1, min(max_results, 20))
    params = {
        "$top": str(limit),
        "$select": "subject,from,receivedDateTime,importance,isRead,webLink",
        "$orderby": "receivedDateTime DESC",
    }
    filters: List[str] = []
    if unread_only:
        filters.append("isRead eq false")
    if today_only:
        filters.append(_outlook_today_filter_utc())
    if filters:
        params["$filter"] = " and ".join(filters)
    ignored_kwargs = {k: v for k, v in kwargs.items() if k not in {"max_results", "unread_only", "today_only"}}
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=30) as client:
        resp = client.get("https://graph.microsoft.com/v1.0/me/messages", params=params, headers=headers)
        if resp.status_code == 401:
            refreshed = _refresh_outlook_access_token()
            if refreshed:
                token = refreshed
                headers = {"Authorization": f"Bearer {token}"}
                resp = client.get("https://graph.microsoft.com/v1.0/me/messages", params=params, headers=headers)
        if resp.status_code == 401:
            body_preview = resp.text[:300]
            raise ValueError(
                "Outlook 401 Unauthorized. Access token gecersiz/suresi dolmus olabilir. "
                f"API cevabi: {body_preview}"
            )
        resp.raise_for_status()
    items = []
    for m in resp.json().get("value", []):
        sender = (m.get("from", {}) or {}).get("emailAddress", {}) or {}
        items.append(
            {
                "subject": m.get("subject", ""),
                "from": sender.get("address", ""),
                "from_name": sender.get("name", ""),
                "received": m.get("receivedDateTime", ""),
                "importance": m.get("importance", ""),
                "is_read": m.get("isRead", True),
                "web_link": m.get("webLink", ""),
            }
        )
    payload: Dict[str, Any] = {"count": len(items), "messages": items, "filter": params.get("$filter", "")}
    if ignored_kwargs:
        payload["ignored_arguments"] = sorted(ignored_kwargs.keys())
    return payload

