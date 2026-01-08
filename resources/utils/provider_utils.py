import os
import xbmc
import xbmcgui
import xbmcvfs
import xbmcaddon
import urllib.request
import json
from datetime import datetime

from .common import log, get_api_url

ADDON = xbmcaddon.Addon()


def get_live_categories():
    api_url = get_api_url()
    if not api_url:
        return

    api_url += "&action=get_live_categories"
    log(f"Fetching xtream live categories from: {api_url}")

    try:
        req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as response:
            raw_data = response.read().decode("utf-8", errors="ignore")

        # Parse JSON and count items
        categories = json.loads(raw_data)
        item_count = len(categories) if isinstance(categories, list) else 0

        log(f"Successfully fetched {item_count} live categories")

        profile_path = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
        if not xbmcvfs.exists(profile_path):
            xbmcvfs.mkdir(profile_path)

        output_path = os.path.join(profile_path, "live_categories.json")

        # Save in pretty format
        with xbmcvfs.File(output_path, "w") as f:
            f.write(json.dumps(categories, indent=2))

        log(f"Live categories saved to: {output_path}")

        # Update the setting in the UI
        ADDON.setSetting(
            "category_status",
            f"[{item_count}] Categories ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})",
        )

        return categories

    except urllib.error.URLError as e:
        log(f"Failed to fetch xtream live categories: {str(e)}", xbmc.LOGERROR)
        xbmcgui.Dialog().ok(
            "Xtream to M3U Error", f"Failed to connect to server:\n{str(e)}"
        )
    except Exception as e:
        log(f"Unexpected error: {str(e)}", xbmc.LOGERROR)
        xbmcgui.Dialog().ok(
            "Xtream to M3U Error", f"An unexpected error occurred:\n{str(e)}"
        )


def get_live_streams():
    api_url = get_api_url()
    if not api_url:
        return

    api_url += "&action=get_live_streams"
    log(f"Fetching xtream live streams from: {api_url}")

    try:
        req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as response:
            raw_data = response.read().decode("utf-8", errors="ignore")

        # Parse JSON and count items
        streams = json.loads(raw_data)
        item_count = len(streams) if isinstance(streams, list) else 0

        log(f"Successfully fetched {item_count} live streams")

        profile_path = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
        if not xbmcvfs.exists(profile_path):
            xbmcvfs.mkdir(profile_path)

        output_path = os.path.join(profile_path, "live_streams.json")

        # Save in pretty format
        with xbmcvfs.File(output_path, "w") as f:
            f.write(json.dumps(streams, indent=2))

        log(f"Live streams saved to: {output_path}")

        return streams

    except urllib.error.URLError as e:
        log(f"Failed to fetch xtream live streams: {str(e)}", xbmc.LOGERROR)
        xbmcgui.Dialog().ok(
            "Xtream to M3U Error", f"Failed to connect to server:\n{str(e)}"
        )
    except Exception as e:
        log(f"Unexpected error: {str(e)}", xbmc.LOGERROR)
        xbmcgui.Dialog().ok(
            "Xtream to M3U Error", f"An unexpected error occurred:\n{str(e)}"
        )
