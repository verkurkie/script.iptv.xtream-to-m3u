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


def get_setting(key):
    """
    Returns the value of a setting in the following priority order:
    - from the ADDON WINDOW (session memory) - this is populated by python code and does not contain "fresh" UI values
    - from the ADDON (disk) - does not contain "fresh" UI values
    """
    CURRENT_WINDOW = xbmcgui.Window(xbmcgui.getCurrentWindowId())
    session_value = CURRENT_WINDOW.getProperty(f"script.iptv.xtream-to-m3u.{key}")
    disk_value = ADDON.getSetting(key)
    if session_value and session_value != disk_value:
        return session_value
    else:
        return disk_value


def set_setting(key, value, addon=True):
    CURRENT_WINDOW = xbmcgui.Window(xbmcgui.getCurrentWindowId())
    CURRENT_WINDOW.setProperty(f"script.iptv.xtream-to-m3u.{key}", value)
    if addon:
        ADDON.setSetting(key, value)  # This won't be save until user hits OK button


def get_api_url():
    host = get_setting("xtream_host").rstrip("/")
    port = get_setting("xtream_port")
    user = get_setting("username")
    password = get_setting("password")

    if not host or not user or not password:
        log(
            f"Missing account details: {host}, {port}, {user}, {password}",
            xbmc.LOGERROR,
        )
        xbmcgui.Dialog().ok("Xtream to M3U", "Please save IPTV Provider Info first.")
        return None

    return f"{host}:{port}/player_api.php?username={user}&password={password}"


def get_m3u_file_path():
    from .pvr_utils import check_pvr

    if not check_pvr():
        return None

    m3u_path = get_setting("m3u_path").strip()
    pvr_instance_name = get_setting("pvr_instance_name").strip()

    if not m3u_path:
        m3u_path = "special://home/userdata/playlists"

    # Normalize path by translating special:// to absolute native paths
    full_path = xbmcvfs.translatePath(m3u_path)

    # Convert PVR instance name to lower-kebab case
    pvr_instance_name = pvr_instance_name.lower().replace(" ", "-")

    m3u_file_path = os.path.join(full_path, f"{pvr_instance_name}.m3u8")
    return m3u_file_path


def system_check():
    system_checks = {
        "last_checked": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "provider": "",
        "user_categories_ids": "",
        "live_categories": "",
        "live_streams": "",
        "playlist": "",
        "pvr": "",
    }

    # Use the unified settings pull (checks properties first to reflect unsaved UI changes)
    user_categories_ids = get_setting("user_categories_ids") or None
    # Strip whitespace and split
    raw_ids = user_categories_ids.strip() if user_categories_ids else ""
    # Filter out empty strings from the list
    user_category_list = [i for i in raw_ids.split(",") if i]

    user_category_count = len(user_category_list)

    log(f"user categories: {user_categories_ids}")
    log(f"user category count: {user_category_count}")

    system_checks["user_categories_ids"] = {
        "status": "ok" if user_category_count > 0 else "error",
        "count": user_category_count,
        "ids": user_category_list,
        "last_modified": None,
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
    log("Checking live categories & streams...")
    user_profile_path = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
    live_categories_path = os.path.join(user_profile_path, "live_categories.json")
    live_streams_path = os.path.join(user_profile_path, "live_streams.json")

    if xbmcvfs.exists(live_categories_path):
        last_modified = xbmcvfs.Stat(live_categories_path).st_mtime()
        with xbmcvfs.File(live_categories_path, "r") as f:
            categories = json.loads(f.read())
            log(f"Live categories read: {len(categories)} characters")

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
    log("Checking playlist status...")
    m3u_file_path = get_m3u_file_path()

    if not m3u_file_path:
        return

    if xbmcvfs.exists(m3u_file_path):
        stat = xbmcvfs.Stat(m3u_file_path)
        file_size = stat.st_size()
        last_modified = stat.st_mtime()

        log(f"Found M3U file: {m3u_file_path} (Size: {file_size} bytes)")
        content = ""
        f = xbmcvfs.File(m3u_file_path, "r")
        content = f.read()
        f.close()

        log(f"M3U file read: {len(content)} characters")

        channel_count = content.count("#EXTINF")

        system_checks["playlist"] = {
            "status": "ok",
            "count": channel_count,
            "path": m3u_file_path,
            "last_modified": datetime.fromtimestamp(last_modified).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        }
    else:
        system_checks["playlist"] = {
            "status": "error",
            "count": None,
            "path": m3u_file_path,
            "last_modified": None,
        }

    # IPTV Simple Client status
    log("Checking PVR status...")
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

    uc_info = system_checks.get("user_categories_ids", {})
    add_line(
        "User Categories",
        uc_info,
        f"{uc_info['count']} selected",
    )

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
            "Playlist",
            pl,
            f"{pl['count']} channels (Built: {pl['last_modified']})\n- Path: {pl['path']}",
        )
    else:
        add_line("Playlist", pl, f"File not found!\n- Path: {pl['path']}")

    # PVR
    pvr = system_checks.get("pvr", {})
    add_line("PVR Client", pvr, f"v{pvr.get('version', '?.?')}")

    add_line(
        "PVR Instance",
        {"status": "ok" if get_setting("pvr_instance_id") != "" else "error"},
        f"{get_setting('pvr_instance_name')} (ID:{get_setting('pvr_instance_id')})",
    )

    # Footer
    report.append("")
    report.append("-" * 30)
    report.append(f"Last Checked: {system_checks['last_checked']}")

    report_str = "\n".join(report)

    # Show results in a proper scrollable text viewer
    xbmcgui.Dialog().textviewer("System Status Report", report_str, True)
