import json
from datetime import datetime
import os
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from .common import log, get_setting, get_m3u_file_path
from .cron_utils import get_job

def system_check():
    ADDON = xbmcaddon.Addon()

    # Create a human-readable report for the text viewer
    report = []

    # Helper to add colored lines (colors only the status tag)
    def add_line(label, status="ok", detail=None):
        color = {
            "ok": "green",
            "warn": "yellow",
            "error": "red",
        }.get(status, "white") # Defaults to "white" if status is unknown

        # Color only the status part, wrapped in brackets for visibility
        colored_status = f"[[COLOR {color}]{status.upper()}[/COLOR]]" if status else "\n==="

        # Use a simpler layout that works better with proportional fonts
        report.append(f"{colored_status} {label}: {detail or '==='}")

    # IPTV Provicer info
    add_line("IPTV Info", None)
    log("[system check] checking IPTV Provider...")
    from .provider_utils import test_provider

    data = test_provider(silent=True)
    user_info = data.get("user_info", {})
    status = user_info.get("status", "Unknown")
    expiry = user_info.get("exp_date", None)

    # Format expiry and determine status tag
    # Format expiry and determine status tag
    status_tag = "error"
    if expiry:
        exp_dt = datetime.fromtimestamp(int(expiry))
        expiry_str = exp_dt.strftime("%Y-%m-%d")
        days_left = (exp_dt - datetime.now()).days

        if days_left < 0:
            status_tag = "error"  # Already expired
        elif days_left <= 14:
            status_tag = "warn"   # Expiring soon
        else:
            status_tag = "ok"
    else:
        expiry_str = "N/A"
        status_tag = "error"

    add_line(
        "IPTV Provider status",
        status_tag,
        f"{status} (expires: {expiry_str})" if expiry else "Check failed! Try again?",
    )

    # Live categories & streams
    log("[system check] checking live categories & streams...")
    user_profile_path = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
    live_categories_path = os.path.join(user_profile_path, "live_categories.json")
    live_streams_path = os.path.join(user_profile_path, "live_streams.json")

    if xbmcvfs.exists(live_categories_path):
        last_modified = xbmcvfs.Stat(live_categories_path).st_mtime()
        with xbmcvfs.File(live_categories_path, "r") as f:
            categories = json.loads(f.read())

        if not categories or not isinstance(categories, list):
            add_line(
                "Categories",
                "error",
                f"0 items ({datetime.fromtimestamp(last_modified).strftime('%Y-%m-%d %H:%M:%S')})",
            )
        else:
            item_count = len(categories)
            add_line(
                "Categories",
                "ok",
                f"{item_count} items ({datetime.fromtimestamp(last_modified).strftime('%Y-%m-%d %H:%M:%S')})",
            )
    else:
        add_line("Categories", "error", "Count: 0")

    if xbmcvfs.exists(live_streams_path):
        last_modified = xbmcvfs.Stat(live_streams_path).st_mtime()

        with xbmcvfs.File(live_streams_path, "r") as f:
            streams = json.loads(f.read())

        if not streams or not isinstance(streams, list):
            add_line(
                "Streams",
                "error",
                f"0 items ({datetime.fromtimestamp(last_modified).strftime('%Y-%m-%d %H:%M:%S')})",
            )
        else:
            item_count = len(streams)
            add_line(
                "Streams",
                "ok",
                f"{item_count} items ({datetime.fromtimestamp(last_modified).strftime('%Y-%m-%d %H:%M:%S')})",
            )
    else:
        add_line("Streams", "error", "Count: 0")

    log("[system check] checking user selected categories...")

    # User selected categories
    user_categories_ids = get_setting("user_categories_ids") or None
    # Strip whitespace and split
    raw_ids = user_categories_ids.strip() if user_categories_ids else ""
    # Filter out empty strings from the list
    user_category_list = [i for i in raw_ids.split(",") if i]

    user_category_count = len(user_category_list)

    add_line(
        label="User Categories",
        status="ok" if user_category_count > 0 else "error",
        detail=f"{user_category_count} selected",
    )

    # IPTV Simple Client status
    add_line("PVR Info", None)
    log("[system check] checking PVR status...")
    try:
        # We use xbmcaddon.Addon just to check if it exists in the system
        # Note: This may fail if it's completely missing
        xbmcaddon.Addon("pvr.iptvsimple")

        # Check if it's enabled via JSON-RPC (and get version)
        rpc_query = {
            "jsonrpc": "2.0",
            "method": "Addons.GetAddonDetails",
            "params": {
                "addonid": "pvr.iptvsimple",
                "properties": ["enabled", "version"],
            },
            "id": 1,
        }

        response = xbmc.executeJSONRPC(json.dumps(rpc_query))
        result = json.loads(response)

        addon_data = result.get("result", {}).get("addon", {})
        is_enabled = addon_data.get("enabled", False)
        pvr_version = addon_data.get("version", "")
        add_line("PVR Client", "ok" if is_enabled else "error", f"Installed (v{pvr_version})")
        add_line(
            "PVR Instance",
            "ok" if get_setting("pvr_instance_id") != "" else "error",
            f"{get_setting('pvr_instance_name')} (ID:{get_setting('pvr_instance_id')})",
        )
    except RuntimeError:
        add_line("PVR Client", "error", "Not installed")

    # Playlist status
    add_line("M3U Info", None)
    log("[system check] checking playlist status...")
    m3u_file_path = get_m3u_file_path()

    if not m3u_file_path:
        return

    if xbmcvfs.exists(m3u_file_path):
        stat = xbmcvfs.Stat(m3u_file_path)
        last_modified = stat.st_mtime()

        content = ""
        f = xbmcvfs.File(m3u_file_path, "r")
        content = f.read()
        f.close()

        channel_count = content.count("#EXTINF")
        add_line(
            "Playlist",
            "ok",
            f"{channel_count} channels ({datetime.fromtimestamp(last_modified).strftime('%Y-%m-%d %H:%M:%S')})",
        )
    else:
        add_line("Playlist", "error", "Count: 0")

    # CRON Job status
    add_line("Auto refresh Info", None)
    log("[system check] checking CRON job status...")
    try:
        # Check if it's enabled via JSON-RPC (and get version)
        rpc_query = {
            "jsonrpc": "2.0",
            "method": "Addons.GetAddonDetails",
            "params": {
                "addonid": "service.cronxbmc",
                "properties": ["enabled", "version"],
            },
            "id": 1,
        }

        response = xbmc.executeJSONRPC(json.dumps(rpc_query))
        result = json.loads(response)

        addon_data = result.get("result", {}).get("addon", {})
        is_enabled = addon_data.get("enabled", False)
        cron_version = addon_data.get("version", "")
        add_line("Cron For Kodi", "ok" if is_enabled else "error", f"Installed (v{cron_version})")

        job = get_job() if is_enabled else None
        auto_refresh = get_setting("auto_refresh")
        add_line(
            "Cron job",
            "ok" if job else "warn",
            f"{job.name} [{auto_refresh}][{job.expression}]" if job else "OFF",
        )
    except RuntimeError:
        add_line("Cron For Kodi", "error", "Not installed")

    # Footer
    add_line("Addon settings", None)

    # Dump Settings
    settings_dump = {
        "host": get_setting("xtream_host"),
        "port": get_setting("xtream_port"),
        "user": get_setting("username"),
        "password": "*******",
        "pvr": get_setting("pvr_instance_name"),
        "pvr_id": get_setting("pvr_instance_id"),
        "m3u": get_setting("m3u_path"),
        "categories": get_setting("user_categories_ids"),
        "exclude_prefixes": get_setting("exclude_prefixes"),
        "strip_prefixes": get_setting("strip_prefixes"),
        "auto_refresh": get_setting("auto_refresh"),
    }
    report.append(json.dumps(settings_dump, indent=2))

    report_str = "\n".join(report)

    # Show results in a proper scrollable text viewer
    xbmcgui.Dialog().textviewer(f"Addon Status - v{ADDON.getAddonInfo('version')}", report_str, True)
