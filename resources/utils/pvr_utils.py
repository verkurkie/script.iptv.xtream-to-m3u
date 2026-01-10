import os
import re
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs
import json
import sqlite3
import glob

from .common import log, get_settings
from .m3u_utils import make_playlist

ADDON = xbmcaddon.Addon()
WINDOW = xbmcgui.Window(10140)


def setup_pvr():
    log("Starting PVR Setup...")
    addon_id = "pvr.iptvsimple"

    try:
        # Check if addon is already present
        try:
            # We use xbmcaddon.Addon just to check if it exists in the system
            # Note: This may fail if it's completely missing
            xbmcaddon.Addon(addon_id)
            log("pvr.iptvsimple is installed.")
        except RuntimeError:
            # Not installed
            log("pvr.iptvsimple not found. Requesting installation...")
            # InstallAddon builtin will prompt user to install
            xbmc.executebuiltin(f"InstallAddon({addon_id})")
            return

        # Check if it's enabled via JSON-RPC (and get version)
        rpc_query = {
            "jsonrpc": "2.0",
            "method": "Addons.GetAddonDetails",
            "params": {"addonid": addon_id, "properties": ["enabled", "version"]},
            "id": 1,
        }
        response = xbmc.executeJSONRPC(json.dumps(rpc_query))
        result = json.loads(response)

        addon_data = result.get("result", {}).get("addon", {})
        is_enabled = addon_data.get("enabled", False)
        pvr_version = addon_data.get("version", "")

        # Fallback if RPC failed to get version (happens on some older Kodi versions)
        if not pvr_version:
            try:
                pvr_version = xbmcaddon.Addon(addon_id).getAddonInfo("version")
            except RuntimeError:
                pvr_version = "Unknown"

        if not is_enabled:
            log("pvr.iptvsimple is disabled. Enabling...")
            rpc_enable = {
                "jsonrpc": "2.0",
                "method": "Addons.SetAddonEnabled",
                "params": {"addonid": addon_id, "enabled": True},
                "id": 1,
            }
            xbmc.executeJSONRPC(json.dumps(rpc_enable))

        log(f"pvr.iptvsimple v.{pvr_version} is installed and enabled.")
        xbmcgui.Dialog().ok(
            "Xtream to M3U", f"pvr.iptvsimple v.{pvr_version} is installed and enabled!"
        )

    except Exception as e:
        log(f"Error in setup_pvr: {str(e)}", xbmc.LOGERROR)


def get_pvr_instances():
    """Lists all pvr.iptvsimple instances from userdata."""
    instances = []
    pvr_data_path = xbmcvfs.translatePath(
        "special://profile/addon_data/pvr.iptvsimple/"
    )

    # Check for the primary settings.xml (Instance 0)
    primary_settings = os.path.join(pvr_data_path, "settings.xml")
    if xbmcvfs.exists(primary_settings):
        instances.append(
            {"id": "0", "name": "Default Instance", "path": primary_settings}
        )

    # Check for additional instances (instance-settings-N.xml)
    if xbmcvfs.exists(pvr_data_path):
        files = xbmcvfs.listdir(pvr_data_path)[1]
        for f in files:
            if f.startswith("instance-settings-") and f.endswith(".xml"):
                instance_id = f.replace("instance-settings-", "").replace(".xml", "")
                path = os.path.join(pvr_data_path, f)

                # Extract the custom name if set
                name = f"Instance {instance_id}"
                try:
                    with xbmcvfs.File(path, "r") as xml_file:
                        content = xml_file.read()
                        match = re.search(
                            r'<setting id="kodi_addon_instance_name">(.*?)</setting>',
                            content,
                        )
                        if match and match.group(1):
                            name = match.group(1)
                except RuntimeError:
                    pass

                instances.append({"id": instance_id, "name": name, "path": path})

    return sorted(instances, key=lambda x: int(x["id"]))


def select_pvr_instance():
    """Shows a dialog to select which PVR instance to target."""
    current_instance_id = ADDON.getSetting("pvr_instance_id")
    instances = get_pvr_instances()

    options = [f"{i['name']} (ID: {i['id']})" for i in instances]
    options.append("[+] Create New Instance")

    sel = xbmcgui.Dialog().select("Select IPTV Simple Client Instance", options)

    if sel == -1:
        return

    if sel == len(instances):
        # Create New Instance logic (will implement template copying in Step 3)
        xbmcgui.Dialog().ok(
            "Xtream to M3U",
            "Multi-instance creation is coming in Step 3.\nFor now, please add a configuration manually in the IPTV Simple Client settings.",
        )
        return

    selected = instances[sel]

    # Update UI (lazy save) and shared memory (instant)
    ADDON.setSetting("pvr_instance_id", str(selected["id"]))
    ADDON.setSetting("pvr_instance_name", str(selected["name"]))

    # Set properties to the window so they can be used BEFORE the user saves the settings!
    WINDOW.setProperty("script.iptv.xtream-to-m3u.pvr_instance_id", str(selected["id"]))
    WINDOW.setProperty(
        "script.iptv.xtream-to-m3u.pvr_instance_name", str(selected["name"])
    )

    log(f"Instance selected: {selected['name']} (ID: {selected['id']})")

    current_playlist_path = ADDON.getSetting("playlist_path")
    has_playlist = xbmcvfs.exists(current_playlist_path)

    if has_playlist and selected["id"] != current_instance_id:
        # Sync playlist and EPG to the new instance but only if the instance is different and there is an existing playlist!
        sync_to_pvr()


def sync_to_pvr():
    """Updates the targeted PVR instance XML with M3U and EPG details."""
    try:
        make_playlist()
        pvr_instance_id, pvr_instance_name, xml_content = get_pvr_instance_info()

        if not xml_content:
            xbmcgui.Dialog().ok("Xtream to M3U", "Failed to get PVR instance XML.")
            return

        settings = get_settings()
        m3u_filename = settings["m3u_filename"]
        host = settings["host"].rstrip("/")
        port = settings["port"]
        user = settings["username"]
        password = settings["password"]
        user_categories_ids = settings["user_categories_ids"]

        if not user_categories_ids or user_categories_ids.strip() == "":
            xbmcgui.Dialog().ok(
                "Xtream to M3U",
                "No categories selected.\nPlease select at least one category first.",
            )
            log("sync_to_pvr: No categories selected. Aborting.")
            return

        # Prepare values
        m3u_url = f"special://home/userdata/playlists/{m3u_filename}"
        # Build the EPG URL with the username and password and limit the data to the user's selected categories
        epg_url = f"{host}:{port}/xmltv.php?username={user}&password={password}&categories={user_categories_ids}"

        # Helper to replace or add settings (handles default="true" attributes and self-closing tags)
        def update_xml_setting(content, setting_id, value):
            import html

            # XML requires escaping special characters like &
            escaped_val = html.escape(str(value))

            # Pattern to match both <setting id="x">...</setting> and <setting id="x" />
            # [^>]*? handles any attributes like default="true"
            pattern = rf'<setting id="{setting_id}"[^>]*?(?:/>|>(?:.*?)</setting>)'

            replacement = f'<setting id="{setting_id}">{escaped_val}</setting>'

            if re.search(pattern, content, re.DOTALL):
                # Replace the entire existing tag (first match)
                content = re.sub(
                    pattern, replacement, content, count=1, flags=re.DOTALL
                )
            else:
                # Add if missing
                content = content.replace(
                    "</settings>", f"    {replacement}\n</settings>"
                )
            return content

        xml_content = update_xml_setting(
            xml_content, "m3uPathType", "1"
        )  # 1 = Remote/Special URL
        xml_content = update_xml_setting(xml_content, "m3uUrl", m3u_url)
        xml_content = update_xml_setting(
            xml_content, "epgPathType", "1"
        )  # 1 = Remote URL
        xml_content = update_xml_setting(xml_content, "epgUrl", epg_url)
        xml_content = update_xml_setting(
            xml_content, "m3uCache", "false"
        )  # Disable cache to ensure fresh loads
        xml_content = update_xml_setting(xml_content, "epgCache", "false")

        set_pvr_instance_xml(pvr_instance_id, xml_content)

        # Trigger PVR reload
        refresh_pvr(silent=True)

        xbmcgui.Dialog().ok(
            "Xtream to M3U",
            f"Configuration synced successfully to:\n{pvr_instance_name}\n\nPVR reload triggered.",
        )

    except Exception as e:
        log(f"Error in sync_to_pvr: {str(e)}", xbmc.LOGERROR)
        xbmcgui.Dialog().ok("Xtream to M3U Error", f"Sync failed:\n{str(e)}")


def get_pvr_instance_info(pvr_instance_id=None):
    # Get target ID (check memory property first, then fallback to disk)
    pvr_instance_id = (
        pvr_instance_id
        or WINDOW.getProperty("script.iptv.xtream-to-m3u.pvr_instance_id")
        or ADDON.getSetting("pvr_instance_id")
    )

    if not pvr_instance_id:
        log(
            "Cannot determine PVR instance ID: No PVR Instance ID provided/configured.",
            xbmc.LOGERROR,
        )
        return None, None, None

    pvr_instance_name = WINDOW.getProperty(
        "script.iptv.xtream-to-m3u.pvr_instance_name"
    ) or ADDON.getSetting("pvr_instance_name")

    # Determine XML path
    pvr_data_path = xbmcvfs.translatePath(
        "special://profile/addon_data/pvr.iptvsimple/"
    )

    if pvr_instance_id == "0":
        xml_path = os.path.join(pvr_data_path, "settings.xml")
    else:
        xml_path = os.path.join(
            pvr_data_path, f"instance-settings-{pvr_instance_id}.xml"
        )

    if not xbmcvfs.exists(xml_path):
        log(f"PVR Config file not found:\n{xml_path}", xbmc.LOGERROR)
        return None, None, None

    with xbmcvfs.File(xml_path, "r") as f:
        xml_content = f.read()

    # Return tuple of (instance_id, pvr_instance_name)
    return pvr_instance_id, pvr_instance_name, xml_content


def set_pvr_instance_xml(pvr_instance_id=None, xml_content=None):
    if xml_content is None:
        return

    pvr_instance_id, pvr_instance_name, _ = get_pvr_instance_info(pvr_instance_id)

    if not pvr_instance_id:
        return

    # Determine XML path
    pvr_data_path = xbmcvfs.translatePath(
        "special://profile/addon_data/pvr.iptvsimple/"
    )
    if pvr_instance_id == "0":
        xml_path = os.path.join(pvr_data_path, "settings.xml")
    else:
        xml_path = os.path.join(
            pvr_data_path, f"instance-settings-{pvr_instance_id}.xml"
        )

    if not xbmcvfs.exists(xml_path):
        log(f"PVR Config file not found:\n{xml_path}", xbmc.LOGERROR)
        return

    with xbmcvfs.File(xml_path, "w") as f:
        f.write(xml_content)


def refresh_pvr(pvr_instance_id=None, silent=False, categories=None):
    """
    Clears channel groups for a specific PVR instance to force a structural reload and
    forces pvr.iptvsimple to reload by toggling it off and on.
    """
    pvr_instance_id, pvr_instance_name, _ = get_pvr_instance_info(pvr_instance_id)

    if not pvr_instance_id:
        return False

    # Use passed categories or fallback to settings/properties
    user_categories_ids = categories
    if not user_categories_ids:
        settings = get_settings()
        user_categories_ids = settings["user_categories_ids"]

    if not user_categories_ids or user_categories_ids.strip() == "":
        if not silent:
            xbmcgui.Dialog().ok(
                "Xtream to M3U",
                "No categories selected.\nPlease select at least one category first.",
            )
        log("refresh_pvr: No categories selected. Aborting.")
        return False

    # Database manipulation - removing the channel-groups will cause the PVR toggle (below) to re-process the M3U file
    db_name = "TV*.db"
    path_db = "special://profile/Database/%s" % db_name
    try:
        filelist = sorted(glob.glob(xbmcvfs.translatePath(path_db)))
    except AttributeError:
        sorted(glob(xbmcvfs.translatePath(path_db)))

    if filelist:
        path = filelist[-1]
    else:
        log("Refresh PVR failed: TV database (TV*.db) not found.", xbmc.LOGERROR)
        return

    log(f"Refreshing PVR (Client ID: {pvr_instance_id}) in {path}...")

    try:
        # Use context manager to ensure connection is closed properly
        with sqlite3.connect(path) as conn:
            cursor = conn.cursor()
            # Use parameterized query (?) for safety
            cursor.execute(
                "DELETE FROM channelgroups WHERE iClientId = ?", (pvr_instance_id,)
            )
            log(f"Database Reset: Deleted {cursor.rowcount} groups.")
            conn.commit()

    except Exception as e:
        log(f"Error during PVR group reset: {str(e)}", xbmc.LOGERROR)

    toggle_pvr(silent)
    return True


def toggle_pvr(silent=None):
    # Toggle PVR to force settings reload after DB manipulation
    try:
        log("Toggling pvr.iptvsimple to force settings reload...")
        # Disable
        xbmc.executeJSONRPC(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "Addons.SetAddonEnabled",
                    "params": {"addonid": "pvr.iptvsimple", "enabled": False},
                    "id": 1,
                }
            )
        )

        # Small sleep to allow Kodi to process the disable command
        xbmc.sleep(1000)

        # Enable
        xbmc.executeJSONRPC(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": "Addons.SetAddonEnabled",
                    "params": {"addonid": "pvr.iptvsimple", "enabled": True},
                    "id": 1,
                }
            )
        )

        # Small sleep then trigger the PVR manager update
        xbmc.sleep(1000)

        xbmc.executebuiltin("PVR.TriggerUpdate")

        if not silent:
            xbmcgui.Dialog().notification(
                "Xtream to M3U", "PVR Reloaded", xbmcgui.NOTIFICATION_INFO, 2000
            )

    except Exception as e:
        log(f"Error refreshing PVR: {str(e)}", xbmc.LOGERROR)
