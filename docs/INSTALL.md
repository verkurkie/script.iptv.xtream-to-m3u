# Installation and Configuration <!-- omit in toc -->

This document helps you install and configure the addon.

## Table of contents <!-- omit in toc -->

- [Installation](#installation)
- [Configuration](#configuration)
  - [First time setup](#first-time-setup)
  - [General](#general)
      - [General -\> PVR Instance](#general---pvr-instance)
      - [General -\> Select Categories](#general---select-categories)
  - [Filters](#filters)
  - [Actions](#actions)
- [Test it](#test-it)

## Installation

To install the add-on, follow these steps:

1. Download the latest ZIP file from the [releases page](https://github.com/verkurkie/script.iptv.xtream-to-m2u/releases)

![install](./assets/github_releases.png)

2. Install the addon in Kodi via the addon manager (using the "Install from zip file" option)

   - In Kodi, go to Add-ons -> Install from zip file
   - Select the downloaded ZIP file

   ❗ If you see a message about installing from unknown source, enable it in Kodi settings before installing!

![install](./assets/kodi_install_zip.png)


## Configuration

To configure the add-on anytime after the first setup, follow these steps:

- In Kodi, go to Add-ons -> My add-ons -> Program add-ons -> click on "Xtream to M3U"
- Make sure the add-on is enabled!
- Click on "Configure"

![configure](./assets/kodi_addon_main.png)

### First time setup

When you run the add-on for the first time, or if critical settings are missing, you will be asked to provide them.

![configure](./assets/kodi_addon_first_time.png)

The process will ask for the following details:

- Xtream info:
  - Host
  - Port
  - Username
  - Password
- PVR instance:
  - Select an existing PVR instance in the IPTV Simple Client add-on
- IPTV categories:
  - Select at least one category to include in the generated playlist

![configure](./assets/kodi_addon_first_time_host.png)

### General

- ❗ **Important: You have to select a PVR instance and enter & save your Xtream IPTV credentials on the first run!**
  - Without this, the addon will not function.

![configure](./assets/kodi_config_general.png)

##### General -> PVR Instance

During first-time setup, the add-on asks you to select an existing IPTV Simple Client instance. You can later change it from this setting.

- ℹ️ If IPTV Simple Client is not installed, the addon will ask you to install it.

![configure](./assets/kodi_config_pvr_instance.png)

##### General -> Select Categories

During first-time setup, categories are fetched after selecting a PVR instance. You can select multiple TV channel categories.

- ℹ️ After setup, use this action to change the selected categories.

- ℹ️ When you select "OK" to save your selection, the add-on will convert your selection to an M3U playlist file and configure it in the IPTV Simple Client instance you selected.

- 💡 **Tip**: You can "jump" through the list of categories by simultaneously pressing `SHIFT` and any letter -> it will jump to the first category that starts with that letter.

![configure](./assets/kodi_config_select_categories.png)

### Filters

Filters can be used to further fine-tune your playlist. Your have the following options:

- **Exclude channels starting with**
  - example: if you don't want channels that start with `"HBO"` or `"ESPN"`, enter `"HBO,ESPN"` here
- **Strip country prefixes from channel names**
  - when this option is selected, the add-on will remove country prefixes (like `"US | "` -> `"UK | "`) from channel names

![configure](./assets/kodi_config_filters.png)

### Actions

The "Actions" tab is where you can find the add-on status and perform actions that normally require a restart of Kodi. The following actions are available:

- **Check Addon Status**
  - this will check the addon display the status
- **Check IPTV Simple Client**
  - this will check if IPTV Simple Client is installed and enabled and display the status
- **Rebuild M3U playlist and sync PVR**
  - this will rebuild your M3U playlist, (re-)configure your IPTV Simple Client instance and reload the PVR instance
- **Make playlist (no sync)**
  - this will only rebuild your M3U playlist (so you can inspect it)

![configure](./assets/kodi_config_actions.png)

![configure](./assets/kodi_config_actions_status.png)

## Test it

Once you have gone through configuring the add-on, make sure you always click on OK!
Then, head over to the "TV" section of Kodi and check if your groups/channels are there.

🎉 Happy Kodi-ing!
