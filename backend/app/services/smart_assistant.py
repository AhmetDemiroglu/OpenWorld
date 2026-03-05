"""
Smart Assistant Background Service
Additional life-quality monitors that run periodically.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import quote_plus

import httpx

from ..config import settings
from .email_monitor import _send_telegram
from ..database import save_assistant_state, load_assistant_state

logger = logging.getLogger(__name__)


def _load_state() -> Dict[str, Any]:
    return load_assistant_state("smart_assistant_main")


def _save_state(state: Dict[str, Any]) -> None:
    save_assistant_state("smart_assistant_main", state)


# ---------------------------------------------------------------------------
# Weather briefing (daily, via wttr.in - no API key needed)
# ---------------------------------------------------------------------------

async def _check_weather(state: Dict[str, Any]) -> None:
    city = getattr(settings, "bg_weather_city", "Izmir")
    now = datetime.now()
    now_hour = now.hour
    today = now.strftime("%Y-%m-%d")
    daily_key = "last_weather_daily"

    # Determine period: morning (7-9), noon (12-13), evening (18-19)
    if 7 <= now_hour <= 9:
        period = "morning"
    elif 12 <= now_hour <= 13:
        period = "noon"
    elif 18 <= now_hour <= 19:
        period = "evening"
    else:
        # If strict windows were missed, still send one fallback daily briefing.
        if state.get(daily_key) == today:
            return
        if not (9 <= now_hour <= 23):
            return
        period = "daily"

    period_key = f"last_weather_{period}"
    if state.get(period_key) == today:
        return  # Already sent for this period today

    try:
        url = f"https://wttr.in/{quote_plus(city)}?format=j1"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        current = data.get("current_condition", [{}])[0]
        weather_desc = current.get("lang_tr", [{}])
        if weather_desc:
            desc = weather_desc[0].get("value", current.get("weatherDesc", [{}])[0].get("value", ""))
        else:
            desc = current.get("weatherDesc", [{}])[0].get("value", "")

        temp = current.get("temp_C", "?")
        feels = current.get("FeelsLikeC", "?")
        humidity = current.get("humidity", "?")

        # Today's forecast
        forecast = data.get("weather", [{}])[0]
        max_t = forecast.get("maxtempC", "?")
        min_t = forecast.get("mintempC", "?")

        # Clothing advice
        temp_int = int(temp) if temp != "?" else 20
        if temp_int < 5:
            advice = "Kalin mont, atki ve eldiven sart."
        elif temp_int < 12:
            advice = "Mont veya kalin ceket onerilir."
        elif temp_int < 18:
            advice = "Hafif bir ceket/hirka yeterli."
        elif temp_int < 25:
            advice = "T-shirt ve hafif giyim yeterli."
        else:
            advice = "Cok sicak - hafif giyinin, su icin."

        text = (
            f"<b>Gunluk Hava Durumu - {city}</b>\n\n"
            f"<b>Sicaklik:</b> {temp} C (hissedilen: {feels} C)\n"
            f"<b>Min/Max:</b> {min_t} C / {max_t} C\n"
            f"<b>Nem:</b> %{humidity}\n"
            f"<b>Durum:</b> {desc}\n\n"
            f"{advice}"
        )
        await _send_telegram(text)
        state[period_key] = today
        state[daily_key] = today
        _save_state(state)
        logger.info(f"SmartAssistant: weather briefing sent for {city} ({period})")

    except Exception as exc:
        logger.warning(f"SmartAssistant: weather check failed: {exc}")


# ---------------------------------------------------------------------------
# GitHub Trending (every 6h)
# ---------------------------------------------------------------------------

async def _check_github_trending(state: Dict[str, Any]) -> None:
    last_check = state.get("last_github", 0)
    if time.time() - last_check < 6 * 3600:
        return

    languages = ["javascript", "typescript", "python", "vue", "c%23"]
    all_repos: List[str] = []

    try:
        seen_repos: Set[str] = set(state.get("github_seen", []))
        new_repos: List[Dict[str, str]] = []

        for lang in languages[:3]:  # Limit to 3 to avoid rate limiting
            url = f"https://api.github.com/search/repositories?q=created:>{(datetime.utcnow() - timedelta(days=7)).strftime('%Y-%m-%d')}+language:{lang}&sort=stars&order=desc&per_page=3"
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, headers={"Accept": "application/vnd.github.v3+json"})
                if resp.status_code != 200:
                    continue
                items = resp.json().get("items", [])

            for item in items:
                full_name = item.get("full_name", "")
                if full_name in seen_repos:
                    continue
                new_repos.append({
                    "name": full_name,
                    "desc": (item.get("description") or "")[:100],
                    "stars": str(item.get("stargazers_count", 0)),
                    "lang": item.get("language", ""),
                    "url": item.get("html_url", ""),
                })
                seen_repos.add(full_name)

        if new_repos:
            lines = ["<b>GitHub Trending Repolar</b>\n"]
            for r in new_repos[:5]:
                lines.append(
                    f"* <b>{r['stars']}</b> | <a href=\"{r['url']}\">{r['name']}</a>\n"
                    f"  {r['lang']} - {r['desc']}"
                )
            await _send_telegram("\n".join(lines))

        # Keep seen list manageable
        if len(seen_repos) > 200:
            seen_repos = set(list(seen_repos)[-100:])
        state["github_seen"] = list(seen_repos)
        state["last_github"] = time.time()
        _save_state(state)
        logger.info(f"SmartAssistant: GitHub trending check done, {len(new_repos)} new repos")

    except Exception as exc:
        logger.warning(f"SmartAssistant: GitHub trending failed: {exc}")


# ---------------------------------------------------------------------------
# News Digest (every 2h via Google News RSS)
# ---------------------------------------------------------------------------

async def _check_tech_news(state: Dict[str, Any]) -> None:
    last_check = state.get("last_tech_news", 0)
    if time.time() - last_check < 2 * 3600:
        return

    import xml.etree.ElementTree as ET

    owner_profile = (getattr(settings, "owner_profile", "") or "").lower()
    query_plan: List[Dict[str, str]] = [
        {"tag": "Teknoloji", "q": "AI model deprecation OR API change OR breaking change"},
        {"tag": "Teknoloji", "q": "Gemini OR Claude OR OpenAI model release"},
        {"tag": "Piyasa", "q": "Turkiye ekonomi enflasyon faiz borsa"},
        {"tag": "Jeopolitik", "q": "middle east conflict energy oil market impact"},
    ]
    if any(k in owner_profile for k in ("yazilim", "developer", "frontend", "react", "vue")):
        query_plan.append({"tag": "Yazilim", "q": "React OR Vue.js OR frontend framework update"})
    if any(k in owner_profile for k in ("yapay zeka", "ai", "ml")):
        query_plan.append({"tag": "AI", "q": "LLM benchmark release open source model"})

    seen_titles: Set[str] = set(state.get("tech_news_seen", []))
    new_items: List[Dict[str, str]] = []

    for qp in query_plan:
        query = qp.get("q", "")
        tag = qp.get("tag", "Gundem")
        try:
            feed_url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en&gl=US&ceid=US:en"
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(feed_url)
                if resp.status_code != 200:
                    continue
                root = ET.fromstring(resp.text)

            for item in root.findall(".//item")[:3]:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                title_key = title.lower()[:60]

                if not title or title_key in seen_titles:
                    continue

                new_items.append({"title": title, "link": link, "tag": tag})
                seen_titles.add(title_key)

        except Exception as exc:
            logger.debug(f"SmartAssistant: tech news query failed: {exc}")

    if new_items:
        lines = ["📰 <b>Kisisel Gundem Ozeti</b>\n"]
        for item in new_items[:8]:
            tag = item.get("tag", "Gundem")
            lines.append(f"• <b>[{tag}]</b> <a href=\"{item['link']}\">{item['title']}</a>")
        await _send_telegram("\n".join(lines))

    # Keep seen list manageable
    if len(seen_titles) > 300:
        seen_titles = set(list(seen_titles)[-150:])
    state["tech_news_seen"] = list(seen_titles)
    state["last_tech_news"] = time.time()
    _save_state(state)
    logger.info(f"SmartAssistant: tech news check done, {len(new_items)} new items")


# ---------------------------------------------------------------------------
# Custom Alerts (every 30 min - user-defined search terms)
# ---------------------------------------------------------------------------

async def _check_custom_alerts(state: Dict[str, Any]) -> None:
    alerts_str = getattr(settings, "bg_custom_alerts", "").strip()
    if not alerts_str:
        return

    last_check = state.get("last_custom_alerts", 0)
    if time.time() - last_check < 30 * 60:
        return

    import xml.etree.ElementTree as ET

    terms = [t.strip() for t in alerts_str.split(",") if t.strip()]
    seen_keys: Set[str] = set(state.get("custom_alerts_seen", []))
    new_items: List[Dict[str, str]] = []

    for term in terms:
        try:
            feed_url = f"https://news.google.com/rss/search?q={quote_plus(term)}&hl=tr&gl=TR&ceid=TR:tr"
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(feed_url)
                if resp.status_code != 200:
                    continue
                root = ET.fromstring(resp.text)

            for item in root.findall(".//item")[:2]:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                key = title.lower()[:60]
                if not title or key in seen_keys:
                    continue
                new_items.append({"title": title, "link": link, "term": term})
                seen_keys.add(key)

        except Exception:
            pass

    if new_items:
        lines = ["<b>Ozel Uyarilar</b>\n"]
        for item in new_items[:5]:
            lines.append(f"* <b>{item['term']}</b>\n- <a href=\"{item['link']}\">{item['title']}</a>")
        await _send_telegram("\n".join(lines))

    if len(seen_keys) > 200:
        seen_keys = set(list(seen_keys)[-100:])
    state["custom_alerts_seen"] = list(seen_keys)
    state["last_custom_alerts"] = time.time()
    _save_state(state)


# ---------------------------------------------------------------------------
# Main assistant class
# ---------------------------------------------------------------------------

class SmartAssistant:
    def __init__(self) -> None:
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_run: Optional[float] = None

    async def start(self) -> None:
        if self._running:
            return
        if not getattr(settings, "bg_smart_assistant", True):
            logger.info("SmartAssistant: disabled by config")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("SmartAssistant started")

    def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("SmartAssistant stopped")

    @property
    def status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "last_run": self._last_run,
            "features": ["weather", "github_trending", "tech_news", "custom_alerts"],
        }

    async def _loop(self) -> None:
        await asyncio.sleep(30)  # let app stabilize
        while self._running:
            try:
                state = _load_state()
                await _check_weather(state)
                await _check_github_trending(state)
                await _check_tech_news(state)
                await _check_custom_alerts(state)
                self._last_run = time.time()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception(f"SmartAssistant error: {exc}")
            # Check every 10 minutes, individual features have their own intervals
            await asyncio.sleep(600)

