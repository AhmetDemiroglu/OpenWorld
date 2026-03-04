import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_ERROR

from app.services.email_monitor import EmailMonitor
from app.services.smart_assistant import SmartAssistant
from app.config import settings

logger = logging.getLogger(__name__)

# Global registry for background services so we can query status
bg_services = {
    "email_monitor": EmailMonitor(),
    "smart_assistant": SmartAssistant()
}

scheduler = AsyncIOScheduler()

def job_error_listener(event):
    if event.exception:
        logger.error(f"Scheduler job {event.job_id} crashed: {event.exception}")

scheduler.add_listener(job_error_listener, EVENT_JOB_ERROR)

async def _email_monitor_tick():
    m = bg_services["email_monitor"]
    if getattr(settings, "bg_email_monitor", True):
        # We manually trigger scan here instead of a while loop in the monitor itself
        await m._scan()

async def _smart_assistant_tick():
    s = bg_services["smart_assistant"]
    if getattr(settings, "bg_smart_assistant", True):
        # We hook directly to the check routines, managing interval internally or here
        from app.services.smart_assistant import _load_state, _check_weather, _check_github_trending, _check_tech_news, _check_custom_alerts
        import time
        state = _load_state()
        await _check_weather(state)
        await _check_github_trending(state)
        await _check_tech_news(state)
        await _check_custom_alerts(state)
        s._last_run = time.time()
        s._running = True

def start_scheduler():
    if not scheduler.running:
        email_interval = getattr(settings, "bg_email_interval_min", 15)
        
        # Email monitor job
        scheduler.add_job(
            _email_monitor_tick,
            trigger=IntervalTrigger(minutes=email_interval),
            id="email_monitor_job",
            replace_existing=True,
            next_run_time=None # will run after 1 interval, or we can set it to run immediately
        )
        
        # Smart assistant wrapper (runs every 10 mins, underlying functions have their own 6h/4h limits)
        scheduler.add_job(
            _smart_assistant_tick,
            trigger=IntervalTrigger(minutes=10),
            id="smart_assistant_job",
            replace_existing=True,
            next_run_time=None
        )
        
        scheduler.start()
        logger.info("APScheduler started and background jobs registered.")

def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("APScheduler stopped.")
