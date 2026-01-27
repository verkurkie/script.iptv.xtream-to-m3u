import os
import re
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs
import json
import sqlite3
import glob

from .common import log, get_setting, set_setting, get_m3u_file_path, check_selected
from .m3u_utils import make_playlist

ADDON = xbmcaddon.Addon()


def config_pvr_client():
    """Closes current settings (clicks the OK button), opens PVR settings, then re-opens current settings."""
    # 1. Close our current settings dialog
    xbmc.executebuiltin('SendClick(10140, 28)')
    xbmc.sleep(400)  # Short sleep to allow Kodi to process the closure

    # 2. Open PVR settings (this is a blocking call)
    try:
        xbmcaddon.Addon('pvr.iptvsimple').openSettings()
    except Exception as e:
        log(f"Could not open PVR settings: {e}")

    # 3. Once PVR settings is closed, re-open our addon's settings
    # We use executebuiltin here so the script can finish terminating
    xbmc.executebuiltin('Addon.OpenSettings(script.iptv.xtream-to-m3u, 2)')


def check_pvr(check_instance=True):
    # Check if addon is already present
    try:
        # We use xbmcaddon.Addon just to check if it exists in the system
        # Note: This may fail if it's completely missing
        xbmcaddon.Addon("pvr.iptvsimple")

        # Check if an instance has been selected
        if check_instance:
            pvr_instance_id = get_setting("pvr_instance_id")
            if not pvr_instance_id:
                xbmcgui.Dialog().ok(
                    "Xtream to M3U",
                    "Please select a PVR instance first.",
                )
                return False
        return True
    except RuntimeError:
        # Not installed
        log("[check_pvr] Addon [pvr.iptvsimple] not found. Requesting installation...")
        # InstallAddon builtin will prompt user to install
        pvr_installed = xbmc.executebuiltin("InstallAddon(pvr.iptvsimple)")
        return pvr_installed


def setup_pvr(silent=False):
    log("[setup_pvr] starting PVR Setup...")
    try:
        if not check_pvr(check_instance=False):
            return

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

        # Fallback if RPC failed to get version (happens on some older Kodi versions)
        if not pvr_version:
            try:
                pvr_version = xbmcaddon.Addon("pvr.iptvsimple").getAddonInfo("version")
            except RuntimeError:
                pvr_version = "Unknown"

        if not is_enabled:
            log("[setup_pvr] Addon [pvr.iptvsimple] is disabled. Enabling...")
            rpc_enable = {
                "jsonrpc": "2.0",
                "method": "Addons.SetAddonEnabled",
                "params": {"addonid": "pvr.iptvsimple", "enabled": True},
                "id": 1,
            }
            xbmc.executeJSONRPC(json.dumps(rpc_enable))

        log(
            f"[setup_pvr] Addon [pvr.iptvsimple] v.{pvr_version} is installed and enabled."
        )

        if not silent:
            xbmcgui.Dialog().ok(
                "Xtream to M3U",
                f"Addon [pvr.iptvsimple] v.{pvr_version} is installed and enabled!",
            )

    except Exception as e:
        log(f"[setup_pvr] unexpected error: {str(e)}", xbmc.LOGERROR)


def create_pvr_instance():
    """
    Creates a new PVR instance in IPTV Simple Client by copying an existing one.
    This ensures we have a valid XML structure for the current IPTV Simple version.
    """
    pvr_data_path = xbmcvfs.translatePath(
        "special://profile/addon_data/pvr.iptvsimple/"
    )

    # 1. Find existing instances to determine the next ID
    existing_ids = [0]
    if xbmcvfs.exists(pvr_data_path):
        files = xbmcvfs.listdir(pvr_data_path)[1]
        for f in files:
            if f.startswith("instance-settings-") and f.endswith(".xml"):
                try:
                    instance_id = int(
                        f.replace("instance-settings-", "").replace(".xml", "")
                    )
                    existing_ids.append(instance_id)
                except ValueError:
                    continue

    next_id = max(existing_ids) + 1
    new_filename = f"instance-settings-{next_id}.xml"
    new_path = os.path.join(pvr_data_path, new_filename)

    # 2. Pick a source template (Instance 1 preferred, then Instance 0, then any)
    source_path = None
    if next_id > 1:
        # Check instance-settings-1.xml
        test_path = os.path.join(pvr_data_path, "instance-settings-1.xml")
        if xbmcvfs.exists(test_path):
            source_path = test_path
        else:
            # Fallback to Instance 0 (settings.xml)
            test_path = os.path.join(pvr_data_path, "settings.xml")
            if xbmcvfs.exists(test_path):
                source_path = test_path

    if not source_path:
        xbmcgui.Dialog().ok(
            "Xtream to M3U",
            "Could not find an existing instance to use as a template. Please create one manually in IPTV Simple Client first.",
        )
        return None

    # 3. Ask for a name
    new_name = xbmcgui.Dialog().input(
        "Enter name for the new PVR instance", defaultt="xtream-to-m3u"
    )
    if not new_name:
        return None

    log(
        f"[create_pvr_instance] creating new PVR instance {next_id} ('{new_name}') using template: {source_path}"
    )

    try:
        # 4. Read source and modify
        content = ""
        with xbmcvfs.File(source_path, "r") as f:
            content = f.read()

        # Helper to reset settings
        def reset_val(xml, setting_id, new_val):
            pattern = rf'<setting id="{setting_id}"[^>]*?(?:/>|>(?:.*?)</setting>)'
            replacement = f'<setting id="{setting_id}">{new_val}</setting>'
            if re.search(pattern, xml, re.DOTALL):
                return re.sub(pattern, replacement, xml, count=1, flags=re.DOTALL)
            return xml

        content = reset_val(content, "kodi_addon_instance_name", new_name)
        content = reset_val(content, "kodi_addon_instance_enabled", "true")
        content = reset_val(content, "m3uPath", "")
        content = reset_val(content, "m3uUrl", "")
        content = reset_val(content, "epgPath", "")
        content = reset_val(content, "epgUrl", "")

        # 5. Write new file
        with xbmcvfs.File(new_path, "w") as f:
            f.write(content)

        log(f"[create_pvr_instance] successfully created: {new_path}")

        xbmcgui.Dialog().notification(
            f"New PVR instance '{new_name}' (ID: {next_id}) created"
        )
        return {"id": str(next_id), "name": new_name, "path": new_path}

    except Exception as e:
        log(
            f"[create_pvr_instance] failed to create PVR instance: {str(e)}",
            xbmc.LOGERROR,
        )
        xbmcgui.Dialog().ok("Error", f"Failed to create instance: {str(e)}")
        return None


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


def select_pvr_instance(sync=True):
    """Shows a dialog to select which PVR instance to target."""
    current_instance_id = get_setting("pvr_instance_id")
    instances = get_pvr_instances()
    if not instances:
        xbmcgui.Dialog().ok(
            "IPTV Simple Client",
            "No instances found!\nPlease create one in IPTV Simple Client first.",
        )
        return

    options = [f"{i['name']} (ID: {i['id']})" for i in instances]
    options.append("[+] Create New Instance")

    sel = xbmcgui.Dialog().select("Select IPTV Simple Client Instance", options)

    if sel == -1:
        return

    if sel == len(instances):
        new_instance = create_pvr_instance()
        if new_instance:
            # Recursively call to show the new list (after prompting for restart)
            select_pvr_instance()
        return

    selected = instances[sel]

    # Update UI (lazy save) and shared memory (instant)
    set_setting("pvr_instance_id", str(selected["id"]))
    set_setting("pvr_instance_name", str(selected["name"]))

    log(
        f"[select_pvr_instance] instance selected: {selected['name']} (ID: {selected['id']})"
    )

    if sync and selected["id"] != current_instance_id:
        # Sync playlist and EPG to the new instance but only if the instance is different and there is an existing playlist!
        sync_to_pvr()

    return selected


def sync_to_pvr(cron=False, silent=False):
    """Updates the targeted PVR instance XML with M3U and EPG details."""
    if cron:
        log("[cron_main] Starting cron job - auto_refresh")

    if not check_pvr():
        return

    try:
        host = get_setting("xtream_host").rstrip("/")
        port = get_setting("xtream_port")
        user = get_setting("username")
        password = get_setting("password")

        if not user or not password:
            if not cron:
                xbmcgui.Dialog().ok(
                    "Xtream to M3U",
                    "No credentials found.\nPlease enter & save your IPTV Provider credentials first.",
                )
            return

        if not make_playlist(cron=cron, silent=silent):
            return

        pvr_instance_id, pvr_instance_name, xml_content = get_pvr_instance_info()

        if not xml_content:
            if not cron:
                xbmcgui.Dialog().ok("Xtream to M3U", "Failed to get PVR instance XML.")
            return

        if not check_selected(cron=cron):
            return

        if not cron:
            xbmcgui.Dialog().notification("Xtream to M3U", "Syncing to PVR...")

        # Prepare values
        m3u_url = get_m3u_file_path()
        # Build the EPG URL with the username and password and limit the data to the user's selected categories
        epg_url = f"{host}:{port}/xmltv.php?username={user}&password={password}"

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
                # We must escape backslashes in the replacement string because re.sub
                # interprets them as escape sequences (e.g., \U in Windows paths)
                safe_replacement = replacement.replace("\\", "\\\\")
                content = re.sub(
                    pattern, safe_replacement, content, count=1, flags=re.DOTALL
                )
            else:
                # Add if missing
                content = content.replace(
                    "</settings>", f"    {replacement}\n</settings>"
                )
            return content

        # Update M3U playlist path - translated to full path by get_m3u_file_path()
        xml_content = update_xml_setting(xml_content, "m3uPathType", "0")
        xml_content = update_xml_setting(xml_content, "m3uPath", m3u_url)

        # Update EPG URL - always remote URL
        xml_content = update_xml_setting(xml_content, "epgPathType", "1")
        xml_content = update_xml_setting(xml_content, "epgUrl", epg_url)

        # Other settings - Disable M3U playlist cache to ensure fresh loads
        xml_content = update_xml_setting(xml_content, "m3uCache", "false")
        xml_content = update_xml_setting(xml_content, "catchupEnabled", "true")
        xml_content = update_xml_setting(xml_content, "allChannelsCatchupMode", "5")
        xml_content = update_xml_setting(xml_content, "catchupOverrideMode", "1")
        xml_content = update_xml_setting(xml_content, "catchupOnlyOnFinishedProgrammes", "false")

        set_pvr_instance_xml(pvr_instance_id, xml_content)

        # Trigger PVR reload
        reset_pvr(silent=True)

        if not cron:
            xbmcgui.Dialog().ok(
                "Xtream to M3U",
                f"Configuration synced successfully to:\n{pvr_instance_name}\n\nPVR reload triggered.",
            )
        else:
            log("[cron_main] Finished cron job - auto_refresh")

    except Exception as e:
        log(f"[sync_to_pvr] unexpected error: {str(e)}", xbmc.LOGERROR)
        if not cron:
            xbmcgui.Dialog().ok("Xtream to M3U Error", f"Sync failed:\n{str(e)}")


def get_pvr_instance_info(pvr_instance_id=None):
    # Get target ID (check memory property first, then fallback to disk)
    pvr_instance_id = pvr_instance_id or get_setting("pvr_instance_id")

    if not pvr_instance_id:
        log(
            "[get_pvr_instance_info] cannot determine PVR instance ID: No PVR Instance ID provided/configured.",
            xbmc.LOGERROR,
        )
        return None, None, None

    pvr_instance_name = get_setting("pvr_instance_name")

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
        log(
            f"[get_pvr_instance_info] PVR Config file not found:\n{xml_path}",
            xbmc.LOGERROR,
        )
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
        log(
            f"[set_pvr_instance_xml] PVR Config file not found:\n{xml_path}",
            xbmc.LOGERROR,
        )
        return

    with xbmcvfs.File(xml_path, "w") as f:
        f.write(xml_content)


def reset_pvr(pvr_instance_id=None, silent=False, categories=[]):
    """
    Clears channel groups for a specific PVR instance to force a structural reload and
    forces pvr.iptvsimple to reload by toggling it off and on.
    """
    if not check_pvr():
        return

    pvr_instance_id, pvr_instance_name, _ = get_pvr_instance_info(pvr_instance_id)

    if not pvr_instance_id:
        xbmcgui.Dialog().ok(
            "Xtream to M3U",
            "Failed to get PVR instance ID.\nPlease select a PVR instance first",
        )
        return False

    if not check_selected(categories=categories, silent=silent):
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
        log(
            "[reset_pvr] PVR reset failed: TV database (TV*.db) not found.",
            xbmc.LOGERROR,
        )
        return

    log(f"[reset_pvr] resetting PVR (Client ID: {pvr_instance_id}) in {path}...")

    try:
        # Use context manager to ensure connection is closed properly
        with sqlite3.connect(path) as conn:
            cursor = conn.cursor()
            # Use parameterized query (?) for safety
            cursor.execute(
                "DELETE FROM channelgroups WHERE iClientId = ?", (pvr_instance_id,)
            )
            log(f"[reset_pvr] database Reset: Deleted {cursor.rowcount} groups.")
            conn.commit()

    except Exception as e:
        log(f"[reset_pvr] error during PVR DB group reset: {str(e)}", xbmc.LOGERROR)

    toggle_pvr(silent)
    return True


def toggle_pvr(silent=None):
    # Toggle PVR to force settings reload after DB manipulation
    try:
        log("[toggle_pvr] toggling Addon [pvr.iptvsimple] to force settings reload...")
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
        log(
            f"[toggle_pvr] error toggling Addon [pvr.iptvsimple]: {str(e)}",
            xbmc.LOGERROR,
        )
