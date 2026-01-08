import os
import re
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs
import json

from .common import log, get_settings

ADDON = xbmcaddon.Addon()
WINDOW = xbmcgui.Window()


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
            ADDON.setSetting("pvr_status", "Installation Requested")
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
        ADDON.setSetting("pvr_status", f"Ready (v.{pvr_version})")
        WINDOW.setProperty(
            "script.iptv.xtream-to-m3u.pvr_status", f"Ready (v.{pvr_version})"
        )

    except Exception as e:
        log(f"Error in setup_pvr: {str(e)}", xbmc.LOGERROR)
        ADDON.setSetting("pvr_status", f"Error: {str(e)}")


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
    WINDOW.setProperty("script.iptv.xtream-to-m3u.pvr_instance_id", str(selected["id"]))
    WINDOW.setProperty(
        "script.iptv.xtream-to-m3u.pvr_instance_name", str(selected["name"])
    )

    log(f"Instance selected: {selected['name']} (ID: {selected['id']})")


def sync_to_pvr():
    """Updates the targeted PVR instance XML with M3U and EPG details."""
    try:
        # Get target ID (check memory property first, then fallback to disk)
        instance_id = WINDOW.getProperty(
            "script.iptv.xtream-to-m3u.pvr_instance_id"
        ) or ADDON.getSetting("pvr_instance_id")
        instance_name = WINDOW.getProperty(
            "script.iptv.xtream-to-m3u.pvr_instance_name"
        ) or ADDON.getSetting("pvr_instance_name")

        if not instance_id:
            xbmcgui.Dialog().ok(
                "Xtream to M3U", "Please select a target configuration first."
            )
            return

        settings = get_settings()
        m3u_filename = settings["m3u_filename"]
        host = settings["host"].rstrip("/")
        port = settings["port"]
        user = settings["username"]
        password = settings["password"]

        # Determine XML path
        pvr_data_path = xbmcvfs.translatePath(
            "special://profile/addon_data/pvr.iptvsimple/"
        )
        if instance_id == "0":
            xml_path = os.path.join(pvr_data_path, "settings.xml")
        else:
            xml_path = os.path.join(
                pvr_data_path, f"instance-settings-{instance_id}.xml"
            )

        if not xbmcvfs.exists(xml_path):
            xbmcgui.Dialog().ok(
                "Xtream to M3U", f"PVR Config file not found:\n{xml_path}"
            )
            return

        # Prepare values
        m3u_url = f"special://home/userdata/playlists/{m3u_filename}"
        epg_url = f"{host}:{port}/xmltv.php?username={user}&password={password}"

        # Read and update XML
        with xbmcvfs.File(xml_path, "r") as f:
            xml_content = f.read()

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

        with xbmcvfs.File(xml_path, "w") as f:
            f.write(xml_content)

        log(f"Successfully synced settings to PVR instance {instance_id}")

        # Trigger PVR update: Toggle the addon to force a re-read of the modified settings.xml
        log("Toggling pvr.iptvsimple to force settings reload...")
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
        # Sleep for a moment to ensure the addon is disabled
        xbmc.sleep(1000)
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

        # Give Kodi a moment to restart the PVR manager, then trigger a refresh
        xbmc.executebuiltin("PVR.TriggerUpdate")

        status_msg = f"Synced to {instance_name}"
        ADDON.setSetting("pvr_status", status_msg)
        WINDOW.setProperty("script.iptv.xtream-to-m3u.pvr_status", status_msg)
        xbmcgui.Dialog().ok(
            "Xtream to M3U",
            f"Configuration synced successfully to:\n{instance_name}\n\nPVR reload triggered.",
        )

    except Exception as e:
        log(f"Error in sync_to_pvr: {str(e)}", xbmc.LOGERROR)
        xbmcgui.Dialog().ok("Xtream to M3U Error", f"Sync failed:\n{str(e)}")
