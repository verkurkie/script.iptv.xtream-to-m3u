import os
import sys
import re
import xbmc
import xbmcgui
import xbmcvfs
import xbmcaddon

from .common import log, get_setting, get_m3u_file_path, check_selected
from .provider_utils import get_iptv_data

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
                log(f"[m3u_utils] m3u file parse AttributeError: {e}", xbmc.LOGERROR)
            except Exception as ex:
                log(f"[m3u_utils] m3u file parse Exception: {ex}", xbmc.LOGERROR)

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


def make_playlist(final_ids=None, silent=True, cron=False):
    user_categories_ids = check_selected(categories=final_ids, cron=cron, silent=silent)
    if not user_categories_ids:
        return False

    if final_ids:
        log(f"[make_playlist] using final_ids: {','.join(map(str, final_ids))}")

    # Create a set from the comma-separated setting string for accurate matching
    selected_id_set = set(id.strip() for id in user_categories_ids.split(",") if id.strip())

    live_categories, live_streams = get_iptv_data(force=cron, cron=cron, silent=True)

    if not live_categories or not live_streams:
        return False

    iptv_host = get_setting("xtream_host")
    iptv_port = get_setting("xtream_port")
    username = get_setting("username")
    password = get_setting("password")
    exclude_prefixes = get_setting("exclude_prefixes")
    strip_prefixes = get_setting("strip_prefixes")

    category_map = {
        str(c.get("category_id")): c.get("category_name") for c in live_categories
    }

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
        tv_archive = channel.get("tv_archive", "")
        tv_archive_duration = channel.get("tv_archive_duration", "")
        group_title = category_map.get(category_id, "Unknown")

        # Build the extras string based on catchup support
        catchup_tags = ""
        # tv_archive is usually an integer 1 or 0, or string "1"/"0"
        if str(tv_archive) == "1":
            catchup_tags += 'catchup="default"'
            if tv_archive_duration:
                catchup_tags += f' catchup-days="{tv_archive_duration}"'

        # Create a new M3uItem object and add it to the list
        m3u_string = (
            f'EXTINF:-1 tvg-id="{epg_channel_id}" '
            f'tvg-name="{tvg_name}" '
            f'tvg-logo="{stream_icon}" '
            f'{catchup_tags} '
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

    log(f"[make_playlist] total M3U entries added: {len(m3u_entries)}")

    # Write the M3U file
    m3u_file_path = get_m3u_file_path()
    write_success = False

    if m3u_entries is not None:
        log(f"[make_playlist] saving new m3u file: {m3u_file_path}")
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
            log(f"[make_playlist] M3U file written to {m3u_file_path}")

            write_success = True

        except Exception as e:
            log(f"[make_playlist] failed to write M3U file: {str(e)}", xbmc.LOGERROR)
            write_success = False

    if not silent:
        xbmcgui.Dialog().ok("Xtream to M3U", "M3U file saved successfully")

    return write_success
