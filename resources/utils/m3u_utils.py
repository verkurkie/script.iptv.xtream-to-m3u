import os
import sys
import re
import xbmc
import xbmcgui
import xbmcvfs
import xbmcaddon
import json
from datetime import datetime

from .common import log
from .provider_utils import get_live_categories, get_live_streams

ADDON = xbmcaddon.Addon()
WINDOW = xbmcgui.Window(10000)


class M3uItem:
    def __init__(self, m3u_fields):
        self.tvg_name = None
        self.tvg_id = None
        self.tvg_logo = None
        self.group_title = None
        self.timeshift = None
        self.catchup_days = None
        self.catchup = None
        self.catchup_source = None
        self.name = None
        self.url = None
        self.is_movie = False
        self.is_series = False
        self.group_idx = 0
        self.channel_idx = sys.maxsize

        if m3u_fields is not None:
            try:
                match = re.search('tvg-name="(.*?)"', m3u_fields, re.IGNORECASE)
                if match:
                    self.tvg_name = match.group(1)
                match = re.search('tvg-id="(.*?)"', m3u_fields, re.IGNORECASE)
                if match:
                    self.tvg_id = match.group(1)
                match = re.search('tvg-logo="(.*?)"', m3u_fields, re.IGNORECASE)
                if match:
                    self.tvg_logo = match.group(1)
                match = re.search('group-title="(.*?)"', m3u_fields, re.IGNORECASE)
                if match:
                    self.group_title = match.group(1)
                match = re.search('timeshift="(.*?)"', m3u_fields, re.IGNORECASE)
                if match:
                    self.timeshift = match.group(1)
                match = re.search('catchup-days="(.*?)"', m3u_fields, re.IGNORECASE)
                if match:
                    self.catchup_days = match.group(1)
                match = re.search('catchup="(.*?)"', m3u_fields, re.IGNORECASE)
                if match:
                    self.catchup = match.group(1)
                match = re.search('catchup-source="(.*?)"', m3u_fields, re.IGNORECASE)
                if match:
                    self.catchup_source = match.group(1)
                self.name = re.search('" ?,(.*)$', m3u_fields, re.IGNORECASE).group(1)
            except AttributeError as e:
                log(f"m3u file parse AttributeError: {e}", xbmc.LOGERROR)
            except Exception as ex:
                log(f"m3u file parse Exception: {ex}", xbmc.LOGERROR)

        if self.tvg_name is None or self.tvg_name == "":
            self.tvg_name = self.name

    def is_valid(self, allow_no_tvg_id=True):
        isvalid = (
            self.tvg_name is not None
            and self.tvg_name != ""
            and self.group_title is not None
            and self.group_title != ""
        )
        if not allow_no_tvg_id:
            isvalid = isvalid and self.tvg_id is not None and self.tvg_id != ""
        return isvalid


def make_playlist(final_ids=None):
    # convert the JSON formatted live channels to M3U format
    if final_ids:
        log(f"make_playlist: Using final_ids: {','.join(map(str, final_ids))}")

    user_profile_path = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
    live_categories_path = os.path.join(user_profile_path, "live_categories.json")
    live_streams_path = os.path.join(user_profile_path, "live_streams.json")
    live_categories = (
        json.load(xbmcvfs.File(live_categories_path))
        if xbmcvfs.exists(live_categories_path)
        else get_live_categories()
    )
    user_categories_ids = (
        ",".join(map(str, final_ids))
        if final_ids
        else WINDOW.getProperty("user_categories_ids")
        or ADDON.getSetting("user_categories_ids")
    )
    live_streams = (
        json.load(xbmcvfs.File(live_streams_path))
        if xbmcvfs.exists(live_streams_path)
        else get_live_streams()
    )

    iptv_host = ADDON.getSetting("xtream_host")
    iptv_port = ADDON.getSetting("xtream_port")
    username = ADDON.getSetting("username")
    password = ADDON.getSetting("password")

    category_map = {
        str(c.get("category_id")): c.get("category_name") for c in live_categories
    }

    # Create a set from the comma-separated setting string for accurate matching
    selected_id_set = set(
        id.strip() for id in user_categories_ids.split(",") if id.strip()
    )

    if not selected_id_set:
        xbmcgui.Dialog().ok(
            "Xtream to M3U",
            "No categories selected.\nPlease select at least one category first.",
        )
        log("make_playlist: No categories selected. Aborting.")
        return

    m3u_entries = []
    for channel in live_streams:
        # Ensure category_id is a string and handle potential 'null' values from API
        category_id = str(channel.get("category_id") or "")

        # If the set is not empty, check if this channel's category is in it
        if selected_id_set and category_id not in selected_id_set:
            continue

        # Get the channel name and URL
        tvg_name = channel.get("name", "")
        stream_icon = channel.get("stream_icon", "")
        epg_channel_id = channel.get("epg_channel_id", "")

        group_title = category_map.get(category_id, "Unknown")
        # Create a new M3uItem object and add it to the list
        m3u_string = (
            f'EXTINF:-1 tvg-id="{epg_channel_id}" '
            f'tvg-name="{tvg_name}" '
            f'tvg-logo="{stream_icon}" '
            f'group-title="{group_title}",'
            f"{tvg_name}"
        )
        m3u_entry = M3uItem(m3u_string)
        m3u_entry.url = (
            f"{iptv_host}:{iptv_port}/"
            f"{username}/{password}/"
            f"{channel.get('stream_id', '')}"
        )

        if m3u_entry.is_valid():
            # This is a keeper for the playlist!
            m3u_entries.append(m3u_entry)

    log(f"Total M3U entries added: {len(m3u_entries)}")

    # Write the M3U file
    save_new_m3u(m3u_entries)


# saves the given m3u_entries into the file system
def save_new_m3u(m3u_entries):
    user_home_path = xbmcvfs.translatePath("special://home")
    playlists_path = os.path.join(user_home_path, "userdata", "playlists")
    if not xbmcvfs.exists(playlists_path):
        xbmcvfs.mkdir(playlists_path)

    m3u_file_path = os.path.join(playlists_path, ADDON.getSetting("m3u_filename"))

    if m3u_entries is not None:
        log(f"Saving new m3u file: {m3u_file_path}")
        try:
            with xbmcvfs.File(m3u_file_path, "w") as m3u_target_file:
                m3u_target_file.write("#EXTM3U\n")
                for entry in m3u_entries:
                    meta = "#EXTINF:-1"
                    logo = entry.tvg_logo
                    if entry.tvg_id is not None and entry.tvg_id != "":
                        channel_id = entry.tvg_id.lower()
                        meta += f' tvg-id="{channel_id}"'

                    meta += f' tvg-name="{entry.tvg_name}"'

                    if logo is not None and logo != "":
                        meta += f' tvg-logo="{logo}"'

                    if entry.group_title is not None and entry.group_title != "":
                        meta += f' group-title="{entry.group_title}"'

                    if entry.timeshift is not None and entry.timeshift != "":
                        meta += f' timeshift="{entry.timeshift}"'

                    if entry.catchup_days is not None and entry.catchup_days != "":
                        meta += f' catchup-days="{entry.catchup_days}"'

                    if entry.catchup is not None and entry.catchup != "":
                        meta += f' catchup="{entry.catchup}"'

                    if entry.catchup_source is not None and entry.catchup_source != "":
                        meta += f' catchup-source="{entry.catchup_source}"'

                    meta += f", {entry.name}\n"

                    m3u_target_file.write(meta)
                    m3u_target_file.write(f"{entry.url}\n")

            log(f"M3U file written to {m3u_file_path}")
            last_modified = xbmcvfs.Stat(m3u_file_path).st_mtime()
            ADDON.setSetting(
                "playlist_status",
                f"[{len(m3u_entries)}] channels ({datetime.fromtimestamp(last_modified).strftime('%Y-%m-%d %H:%M:%S')})",
            )
        except Exception as e:
            log(f"Failed to write M3U file: {str(e)}", xbmc.LOGERROR)
            ADDON.setSetting("playlist_status", "Failed to write file")
