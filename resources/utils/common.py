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
    # Create a human-readable report for the text viewer
    report = []

    # Header
    report.append("SYSTEM STATUS REPORT")
    report.append("=" * 30)
    report.append("")

    # Helper to add colored lines (colors only the status tag)
    def add_line(label, status="ok", detail=""):
        color = "green" if status == "ok" else "red"

        # Color only the status part, wrapped in brackets for visibility
        colored_status = f"[[COLOR {color}]{status.upper()}[/COLOR]]"

        # Use a simpler layout that works better with proportional fonts
        report.append(f"{colored_status} {label}: {detail}")

    # Test provider connection
    api_url = get_api_url()
    if not api_url:
        return

    log(f"Testing provider connection: {api_url}")

    try:
        from .provider_utils import test_provider

        data = test_provider()
        user_info = data.get("user_info", {})
        status = user_info.get("status", "Unknown")
        expiry = user_info.get("exp_date", "0")

        # Format expiry (Xtream uses unix timestamp)
        if expiry and expiry != "null":
            expiry_str = datetime.fromtimestamp(int(expiry)).strftime("%Y-%m-%d")
        else:
            expiry_str = "Never"

        add_line(
            "Account status",
            "ok" if status == "Active" else "error",
            f"Exp: {expiry_str}\n",
        )

    except urllib.error.URLError as e:
        log(f"Failed to test server: {str(e)}", xbmc.LOGERROR)
        add_line("Provider", "error", "Exp: N/A")
    except Exception as e:
        log(f"Unexpected error: {str(e)}", xbmc.LOGERROR)
        add_line("Provider", "error", "Exp: N/A")

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

    # User selected categories
    user_categories_ids = get_setting("user_categories_ids") or None
    # Strip whitespace and split
    raw_ids = user_categories_ids.strip() if user_categories_ids else ""
    # Filter out empty strings from the list
    user_category_list = [i for i in raw_ids.split(",") if i]

    user_category_count = len(user_category_list)

    log(f"user categories: {user_categories_ids}")
    log(f"user category count: {user_category_count}")

    add_line(
        label="User Categories",
        status="ok" if user_category_count > 0 else "error",
        detail=f"{user_category_count} selected\n",
    )

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
        add_line("PVR Client", "ok" if is_enabled else "error", f"v{pvr_version}")
        add_line(
            "PVR Instance",
            "ok" if get_setting("pvr_instance_id") != "" else "error",
            f"{get_setting('pvr_instance_name')} (ID:{get_setting('pvr_instance_id')})",
        )
    except RuntimeError:
        add_line("PVR Client", "error", "Not installed")

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
        add_line(
            "Playlist",
            "ok",
            f"{channel_count} channels ({datetime.fromtimestamp(last_modified).strftime('%Y-%m-%d %H:%M:%S')})\n",
        )
    else:
        add_line("Playlist", "error", "Count: 0\n")

    # Footer
    report.append("-" * 30)

    report_str = "\n".join(report)

    # Show results in a proper scrollable text viewer
    xbmcgui.Dialog().textviewer("System Status Report", report_str, True)
