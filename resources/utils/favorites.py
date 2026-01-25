import xbmc
import xbmcgui
import json

from .common import log, db_exec
from .pvr_utils import reset_pvr

GROUP_ADDED = False
FAVS_ADDED = 0

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


def get_matching_channels(fav_titles=None):
    if fav_titles is None:
        fav_titles = []

    # Efficiency Step: Get ALL channels from the DB once
    placeholders = ",".join("?" for _ in fav_titles)
    query = f"SELECT * FROM channels WHERE sChannelName IN ({placeholders})"
    db_channels_raw = db_exec("TV", query, tuple(fav_titles))
    if not db_channels_raw:
        log("[favorites] No channels found in TV database.", xbmc.LOGWARNING)
        return

    # Create a lookup dictionary: { "Channel Name": ID }
    db_channels = {row["sChannelName"]: row for row in db_channels_raw}

    # Find the channels and add them
    log(f"Checking [{len(fav_titles)}] favorites...")
    matching_channels = []
    for channel_title in fav_titles:
        channel = db_channels.get(channel_title)

        if channel:
            matching_channels.append(channel)

    return matching_channels


def get_new_channels(matching_channels=[]):
    if len(matching_channels) == 0:
        return

    # At this point, we have favorites and we can get (or create) the [Favs] group
    # Get the Favs channelgroup ID
    fav_group_id = db_get_channelgroup_id()
    if not fav_group_id:
        return

    new_channels = []

    for matching_channel in matching_channels:
        # Check if the channel is already in the Favs group
        channel_id = matching_channel.get("idChannel")
        exists = db_exec("TV", "SELECT * FROM map_channelgroups_channels WHERE idGroup = ? AND idChannel = ?", (fav_group_id, channel_id))

        if len(exists) == 0:
            new_channels.append(matching_channel)
    
    return new_channels


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
    num_new = 0
    if len(favorites) > 0:
        fav_titles = [f.get("title", "Unknown") for f in favorites]
        matching_channels = get_matching_channels(fav_titles)
        if len(matching_channels) > 0:
            num_matching = len(matching_channels)
            new_channels = get_new_channels(matching_channels)

            if len(new_channels) > 0:
                num_new = len(new_channels)
                db_add_channels_to_group(new_channels)
            else:
                log("No new channels to be added to the Favs group")
        else:
            log("No matching favorites found")

    if GROUP_ADDED or FAVS_ADDED:
        # Trigger reload of PVR
        xbmcgui.Dialog().ok("Favorites", f"Found [{num_matching}] matching favorites - added [{num_new}]")
        reset_pvr()
    else:
        xbmcgui.Dialog().ok("Favorites", f"Found [{num_matching}] matching favorites - already in the Favs group" if num_matching > 0 else "Found no matching favorites")

    log(f"All done - favs group added: {GROUP_ADDED} - favs added: {FAVS_ADDED}")
