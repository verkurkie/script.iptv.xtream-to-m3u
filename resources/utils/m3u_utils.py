import os
import sys
import re
import xbmc
import xbmcgui
import xbmcvfs
import xbmcaddon
import json
from datetime import datetime

from .common import log, get_setting, set_setting, get_m3u_file_path
from .provider_utils import get_live_categories, get_live_streams

ADDON = xbmcaddon.Addon()


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

    if not live_categories:
        return False

    user_categories_ids = (
        ",".join(map(str, final_ids))
        if final_ids
        else get_setting("user_categories_ids")
    )

    live_streams = (
        json.load(xbmcvfs.File(live_streams_path))
        if xbmcvfs.exists(live_streams_path)
        else get_live_streams()
    )

    iptv_host = get_setting("xtream_host")
    iptv_port = get_setting("xtream_port")
    username = get_setting("username")
    password = get_setting("password")
    exclude_prefixes = get_setting("exclude_prefixes")
    strip_prefixes = get_setting("strip_prefixes")

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
        return False

    m3u_entries = []

    # Filter out any channels that match any of the exclude regexes
    if exclude_prefixes:
        exclude_prefixes = exclude_prefixes.strip().split(",")
        exclude_prefixes.append("✦●✦●")
    else:
        exclude_prefixes = ["✦●✦●"]

    for channel in live_streams:
        # Ensure category_id is a string and handle potential 'null' values from API
        category_id = str(channel.get("category_id") or "")

        # If the set is not empty, check if this channel's category is in it
        if selected_id_set and category_id not in selected_id_set:
            continue

        # Get the channel name and URL - strip the prefix if needed (do this BEFORE the exclude check!)
        tvg_name = channel.get("name", "")

        if strip_prefixes and " | " in tvg_name:
            tvg_name = tvg_name.split(" | ", 1)[1]

        # Skip channel if it starts with any of the exclude prefixes
        if strip_prefixes and tvg_name.startswith(tuple(exclude_prefixes)):
            continue

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
    return save_new_m3u(m3u_entries)


# saves the given m3u_entries into the file system
def save_new_m3u(m3u_entries):
    m3u_file_path = get_m3u_file_path()

    if m3u_entries is not None:
        log(f"Saving new m3u file: {m3u_file_path}")
        try:
            # Using File() object directly for maximum compatibility
            f = xbmcvfs.File(m3u_file_path, "w")
            f.write("#EXTM3U\n")
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

                f.write(meta)
                f.write(f"{entry.url}\n")
            f.close()

            log(f"M3U file written to {m3u_file_path}")
            stat = xbmcvfs.Stat(m3u_file_path)
            last_modified = stat.st_mtime()
            set_setting(
                "playlist_status",
                f"[{len(m3u_entries)}] channels ({datetime.fromtimestamp(last_modified).strftime('%Y-%m-%d %H:%M:%S')})",
            )
            return True
        except Exception as e:
            log(f"Failed to write M3U file: {str(e)}", xbmc.LOGERROR)
            set_setting("playlist_status", "Failed to write file")
            return False
