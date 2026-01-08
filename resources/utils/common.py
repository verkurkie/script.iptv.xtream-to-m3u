import os
import xbmc
import xbmcgui
import xbmcaddon
import xbmcvfs
import urllib.request
import json
from datetime import datetime


ADDON = xbmcaddon.Addon()


def log(message, level=xbmc.LOGINFO):
    xbmc.log(f"[script.iptv.xtream-to-m3u] {message}", level)


def get_settings():
    return {
        "host": ADDON.getSetting("xtream_host"),
        "port": ADDON.getSetting("xtream_port"),
        "username": ADDON.getSetting("username"),
        "password": ADDON.getSetting("password"),
        "m3u_filename": ADDON.getSetting("m3u_filename") or "xtream.m3u",
    }


def get_api_url():
    settings = get_settings()
    host = settings["host"].rstrip("/")
    port = settings["port"]
    user = settings["username"]
    password = settings["password"]

    if not host or not user or not password:
        log("Missing account details", xbmc.LOGERROR)
        xbmcgui.Dialog().ok(
            "Xtream to M3U", "Please configure your account details first."
        )
        return None

    return f"{host}:{port}/player_api.php?username={user}&password={password}"


def system_check():
    system_checks = {
        "last_checked": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "provider": "",
        "live_categories": "",
        "live_streams": "",
        "playlist": "",
        "pvr": "",
    }

    api_url = get_api_url()
    if not api_url:
        return

    # Test provider connection
    log(f"Testing provider connection: {api_url}")

    try:
        req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as response:
            data = response.read().decode("utf-8", errors="ignore")

        data = json.loads(data)
        user_info = data.get("user_info", {})
        status = user_info.get("status", "Unknown")
        expiry = user_info.get("exp_date", "0")

        # Format expiry (Xtream uses unix timestamp)
        if expiry and expiry != "null":
            expiry_str = datetime.fromtimestamp(int(expiry)).strftime("%Y-%m-%d")
        else:
            expiry_str = "Never"

        system_checks["provider"] = {
            "status": "ok" if status == "Active" else "error",
            "expiry": expiry_str,
            "user_info": user_info,
        }

    except urllib.error.URLError as e:
        log(f"Failed to test server: {str(e)}", xbmc.LOGERROR)
        system_checks["provider"] = {
            "status": "error",
            "expiry": "N/A",
            "user_info": "N/A",
        }
    except Exception as e:
        log(f"Unexpected error: {str(e)}", xbmc.LOGERROR)
        system_checks["provider"] = {
            "status": "error",
            "expiry": "N/A",
            "user_info": "N/A",
        }

    # Live categories & streams
    user_profile_path = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
    live_categories_path = os.path.join(user_profile_path, "live_categories.json")
    live_streams_path = os.path.join(user_profile_path, "live_streams.json")

    if xbmcvfs.exists(live_categories_path):
        last_modified = xbmcvfs.Stat(live_categories_path).st_mtime()
        with xbmcvfs.File(live_categories_path, "r") as f:
            categories = json.loads(f.read())

        if not categories or not isinstance(categories, list):
            system_checks["live_categories"] = {
                "status": "error",
                "count": 0,
                "last_modified": datetime.fromtimestamp(last_modified).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            }
        else:
            item_count = len(categories)
            system_checks["live_categories"] = {
                "status": "ok",
                "count": item_count,
                "last_modified": datetime.fromtimestamp(last_modified).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            }
    else:
        system_checks["live_categories"] = {
            "status": "error",
            "count": None,
            "last_modified": None,
        }

    if xbmcvfs.exists(live_streams_path):
        last_modified = xbmcvfs.Stat(live_streams_path).st_mtime()

        with xbmcvfs.File(live_streams_path, "r") as f:
            streams = json.loads(f.read())

        if not streams or not isinstance(streams, list):
            system_checks["live_streams"] = {
                "status": "error",
                "count": 0,
                "last_modified": datetime.fromtimestamp(last_modified).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            }
        else:
            item_count = len(streams)
            system_checks["live_streams"] = {
                "status": "ok",
                "count": item_count,
                "last_modified": datetime.fromtimestamp(last_modified).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            }
    else:
        system_checks["live_streams"] = {
            "status": "error",
            "count": None,
            "last_modified": None,
        }

    # Playlist status
    user_home_path = xbmcvfs.translatePath("special://home")
    playlists_path = os.path.join(user_home_path, "userdata", "playlists")
    m3u_file_path = os.path.join(playlists_path, ADDON.getSetting("m3u_filename"))

    if xbmcvfs.exists(m3u_file_path):
        last_modified = xbmcvfs.Stat(m3u_file_path).st_mtime()
        # Get the channel count from the m3u file
        channel_count = 0
        with xbmcvfs.File(m3u_file_path, "r") as f:
            content = f.read()
            channel_count = content.count("#EXTINF")

        system_checks["playlist"] = {
            "status": "ok",
            "count": channel_count,
            "last_modified": datetime.fromtimestamp(last_modified).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        }
    else:
        system_checks["playlist"] = {
            "status": "error",
            "count": None,
            "last_modified": None,
        }

    # IPTV Simple Client
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

        system_checks["pvr"] = {
            "status": "ok" if is_enabled else "error",
            "version": pvr_version,
        }
    except RuntimeError:
        # Not installed
        system_checks["pvr"] = {
            "status": "error",
            "version": "pvr.iptvsimple not found - please install it from the Kodi Addon repository",
        }

    # write system checks to file
    with xbmcvfs.File(os.path.join(user_profile_path, "system_checks.json"), "w") as f:
        f.write(json.dumps(system_checks, indent=2))

    # Create a human-readable report for the text viewer
    report = []

    # Header
    report.append("SYSTEM STATUS REPORT")
    report.append("=" * 30)
    report.append("")

    # Helper to add colored lines (colors only the status tag)
    def add_line(label, check_data, detail):
        status = check_data.get("status", "error").upper()
        color = "green" if status == "OK" else "red"

        # Color only the status part, wrapped in brackets for visibility
        colored_status = f"[[COLOR {color}]{status}[/COLOR]]"

        # Use a simpler layout that works better with proportional fonts
        report.append(f"{colored_status} {label}: {detail}")

    # Sections
    p_info = system_checks.get("provider", {})
    add_line("Provider", p_info, f"Exp: {p_info.get('expiry', 'N/A')}")

    lc = system_checks.get("live_categories", {})
    if lc.get("count") is not None:
        add_line("Categories", lc, f"{lc['count']} items (Mod: {lc['last_modified']})")
    else:
        add_line("Categories", lc, "File missing or empty")

    ls = system_checks.get("live_streams", {})
    if ls.get("count") is not None:
        add_line("Streams", ls, f"{ls['count']} items (Mod: {ls['last_modified']})")
    else:
        add_line("Streams", ls, "File missing or empty")

    pl = system_checks.get("playlist", {})
    if pl.get("count") is not None:
        add_line(
            "Playlist", pl, f"{pl['count']} channels (Built: {pl['last_modified']})"
        )
    else:
        add_line("Playlist", pl, "M3U file not found")

    # PVR
    pvr = system_checks.get("pvr", {})
    add_line("PVR Client", pvr, f"v{pvr.get('version', '?.?')}")

    add_line(
        "PVR Instance",
        {"status": "ok" if ADDON.getSetting("pvr_instance_id") != "" else "error"},
        f"{ADDON.getSetting('pvr_instance_name')} (ID:{ADDON.getSetting('pvr_instance_id')})",
    )

    # Footer
    report.append("")
    report.append("-" * 30)
    report.append(f"Last Checked: {system_checks['last_checked']}")

    report_str = "\n".join(report)

    # Show results in a proper scrollable text viewer
    xbmcgui.Dialog().textviewer("System Status Report", report_str, True)
