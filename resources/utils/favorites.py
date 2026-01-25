import xbmc
import xbmcgui
import json

from .common import log, db_exec
from .pvr_utils import reset_pvr

GROUP_ADDED = False
FAVS_ADDED = 0
FAVS_REMOVED = 0

"""
TV Database schema:
- channelgroups
  - idGroup
  - isGroupType - 2 is for custom added groups
  - sName
  - iClientId - set to -1 for custom groups
- channels
  - idChannel - unique table ID
  - sChannelName
  - idEpg
- map_channelgroups_channels
  - idChannel
    -> channels.idChannel
  - idGroup
    -> channelgroups.idGroup
  - iChannelNumber
    -> channels.idEpg
  - iClientChannelNumber
    -> channels.idEpg
"""

def db_get_channelgroup_id():
    global GROUP_ADDED
    # Gets the "Favs" group ID from the TV database
    result = db_exec("TV", "SELECT idGroup FROM channelgroups WHERE sName = ?", "Favs")
    if result and len(result):
        fav_group_id = result[0].get("idGroup")
        log(f"[favorites] Found [Favs] group with id {fav_group_id}")
        return fav_group_id  # Return the ID from the first row found
    else:
        # The Favs group was not found - add it!
        log("[favorites] Group [Favs] not found in database. Creating it...")
        
        # Get the next available ID
        max_id_res = db_exec("TV", "SELECT MAX(idGroup) as max_id FROM channelgroups")
        next_group_id = (max_id_res[0].get("max_id") or 0) + 1
        
        # Insert the new group
        db_exec("TV", 
            "INSERT INTO channelgroups VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", 
            (next_group_id, 0, 2, "Favs", 0, 0, 0, 0, -1, 0, '', 0)
        )
        
        log(f"[favorites] Successfully created [Favs] group with id {next_group_id}")
        GROUP_ADDED = True
        return next_group_id


def get_favorites_db_data(fav_titles=None):
    if not fav_titles:
        return [], []

    fav_group_id = db_get_channelgroup_id()
    if not fav_group_id:
        return [], []

    # Efficiency Step: Get matching channels and their group status in ONE query
    placeholders = ",".join("?" for _ in fav_titles)
    query = f"""
        SELECT c.*, m.idGroup as groupLink
        FROM channels c
        LEFT JOIN map_channelgroups_channels m ON c.idChannel = m.idChannel AND m.idGroup = ?
        WHERE c.sChannelName IN ({placeholders})
    """
    
    params = [fav_group_id] + fav_titles
    db_rows = db_exec("TV", query, tuple(params))
    
    if not db_rows:
        log("[favorites] No matching channels found in TV database.")
        return [], []

    matching_channels = []
    new_channels = []

    for row in db_rows:
        matching_channels.append(row)
        # If groupLink is None, it means the LEFT JOIN found no entry in the group map
        if row.get("groupLink") is None:
            new_channels.append(row)

    return matching_channels, new_channels


def db_add_channels_to_group(new_channels=[]):
    global FAVS_ADDED
    if len(new_channels) == 0:
        return

    # Get the Favs channelgroup ID
    fav_group_id = db_get_channelgroup_id()
    if not fav_group_id:
        return

    # Build a single batch INSERT query
    placeholders = ",".join(["(?, ?, ?, ?, ?, ?, ?)" for _ in new_channels])
    query = f"INSERT INTO map_channelgroups_channels VALUES {placeholders}"
    
    # Flatten all channel parameters into one tuple
    params = []
    for chan in new_channels:
        channel_id = chan.get("idChannel")
        channel_num = chan.get("idEpg")
        params.extend([channel_id, fav_group_id, channel_num, 0, 0, channel_num, 0])
        
    db_exec("TV", query, tuple(params))
    FAVS_ADDED = len(new_channels)
    log(f"[favorites] Batch inserted {len(new_channels)} channels into group {fav_group_id}")


def db_cleanup_orphans(fav_titles=None):
    global FAVS_REMOVED
    if fav_titles is None:
        fav_titles = []

    fav_group_id = db_get_channelgroup_id()
    if not fav_group_id:
        return

    # Get all channels currently in the Favs group
    query = """
        SELECT m.idChannel, c.sChannelName 
        FROM map_channelgroups_channels m
        JOIN channels c ON m.idChannel = c.idChannel
        WHERE m.idGroup = ?
    """
    current_favs = db_exec("TV", query, (fav_group_id,))
    
    if not current_favs:
        return

    # Find channels in DB that are NOT in the Kodi favorites list
    orphans = [row["idChannel"] for row in current_favs if row["sChannelName"] not in fav_titles]

    if orphans:
        placeholders = ",".join("?" for _ in orphans)
        delete_query = f"DELETE FROM map_channelgroups_channels WHERE idGroup = ? AND idChannel IN ({placeholders})"
        db_exec("TV", delete_query, tuple([fav_group_id] + orphans))
        FAVS_REMOVED = len(orphans)
        log(f"[favorites] Cleaned up {len(orphans)} orphaned channels from Favs group")


def sync_favorites():
    # Get favorites
    rpc_query = {
        "jsonrpc": "2.0",
        "method": "Favourites.GetFavourites",
        "params": {
            "type": "media",
        },
        "id": 1,
    }

    response = xbmc.executeJSONRPC(json.dumps(rpc_query))
    result = json.loads(response)
    favorites = []

    if result:
        favorites = result.get("result", {}).get("favourites", None)
    else:
        xbmcgui.Dialog().ok("Favorites", "No favorites to process")
        return

    num_matching = 0
    if len(favorites) > 0:
        fav_titles = [f.get("title", "Unknown") for f in favorites]
        log(f"Checking [{len(fav_titles)}] favorites against TV database...")
        
        # 1. Add new favorites
        matching_channels, new_channels = get_favorites_db_data(fav_titles)
        
        if matching_channels:
            num_matching = len(matching_channels)
            if new_channels:
                db_add_channels_to_group(new_channels)
            else:
                log("No new channels to be added to the Favs group")
        
        # 2. Cleanup old favorites (reverse check)
        db_cleanup_orphans(fav_titles)

    if GROUP_ADDED or FAVS_ADDED or FAVS_REMOVED:
        # Trigger reload of PVR
        msg = f"Found [{num_matching}] matching favorites.\nAdded: {FAVS_ADDED} | Removed: {FAVS_REMOVED}"
        xbmcgui.Dialog().ok("Favorites Sync", msg)
        reset_pvr()
    else:
        xbmcgui.Dialog().ok("Favorites Sync", "Everything is already in sync!")

    log(f"All done - group added: {GROUP_ADDED} - added: {FAVS_ADDED} - removed: {FAVS_REMOVED}")
