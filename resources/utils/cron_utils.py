"""
This module is used to manage the cron job for the addon - it uses the 'service.cronxbmc' addon to create and manage the cron job

Example BUILT-IN:
- RunScript(script.iptv.xtream-to-m3u, action=auto_refresh)

Example JSONRPC:
- '{"jsonrpc": "2.0", "id": 1, "method": "VideoLibrary.Clean", "params": {"showdialogs": true, "content": "movies"}}'

Job "expressions" are in standard cron format, e.g. "0 0 * * *" for every day at midnight

.--------------- minute (0 - 59)
|   .------------ hour (0 - 23)
|   |   .--------- day of month (1 - 31)
|   |   |   .------ month (1 - 12) or Jan, Feb ... Dec
|   |   |   |  .---- day of week (0 - 6) or Sun(0 or 7), Mon(1) ... Sat(6)
V   V   V   V  V
*   *   *   *  *

"""

import xbmcaddon
import xbmcgui
import json
from cron import CronManager, CronJob
from resources.utils.common import log

CRON_ADDON_ID = "service.cronxbmc"
CRON_EXP = {
    "daily": "0 0 * * *",
    "weekly": "0 0 * * 0",
    "monthly": "0 0 1 * *"
}


def check_cron():
    try:
        xbmcaddon.Addon(CRON_ADDON_ID)

    except RuntimeError:
        xbmcgui.Dialog().ok("Cron not installed", "Please install Cron addon")

def get_job():
    manager = CronManager()
    jobs = manager.getJobs()
    for job in jobs:
        if job.name == 'xtream-to-m3u-cron':
            return job
    return None


def delete_job():
    job = get_job()
    if job is None:
        log("[cron_utils] Cron job [xtream-to-m3u-cron] was not found, nothing to delete.")
        return

    log("[cron_utils] Deleting cron job [xtream-to-m3u-cron]")
    manager = CronManager()
    manager.deleteJob(job.id)


def add_job(interval=None):
    job = get_job()
    manager = CronManager()
    if job is None:
        log(f"[cron_utils] Creating new cron job [xtream-to-m3u-cron] with interval: {interval}")
        job = CronJob()
    else:
        log(f"[cron_utils] Updating cron job [xtream-to-m3u-cron] to interval: {interval}")

    job.name = 'xtream-to-m3u-cron'
    job.command_type = "built-in"
    job.command = "RunScript(script.iptv.xtream-to-m3u, action=auto_refresh)"
    job.expression = CRON_EXP[interval]
    job.show_notification = "false"
    manager.addJob(job) #call this to create new or update an existing job


def manage_job(interval=None):
    # Get the jobs and find the ID for the 'xtream-to-m3u-cron' job
    if interval is None:
        log("[cron_utils] No interval provided, exiting.")
        return

    if interval == "off":
        delete_job()
    else:
        add_job(interval=interval)
