# Roadmap

Planned improvements for Spoolhouse, roughly in priority order. Shipped items move to
[CHANGELOG.md](CHANGELOG.md). Ideas and pull requests are welcome.

Status: ✅ done · 🚧 in progress · 📋 planned

## Keeping inventory live

| | Feature | What it does |
|---|---|---|
| ✅ | **Menu bar mode** | Closing the window keeps the app running quietly in the menu bar, so printer usage is still tracked. The menu shows what's printing and grams left. |
| ✅ | **Open at login** | Starts in the menu bar when you log in, so tracking never stops. |
| ✅ | **Will it fit?** | Before a print, compare its filament estimate with what's left on the loaded spool and warn if it will run out (depends on the printer exposing the estimate). |
| ✅ | **Mac notifications** | Low stock, print finished, unassigned usage to charge, reader unplugged. |
| ✅ | **Humidity alert** | Warn when a CFS unit's humidity goes above a threshold (e.g. 50%), as a reminder to dry or reseal. |

## Costs and stock

| | Feature | What it does |
|---|---|---|
| ✅ | **Cost per print** | Each print in the log shows what its filament cost (from the spools' prices), with a monthly total. |
| ✅ | **Shopping list** | Turn "Running low" into a reorder list with last price and shop; copy or share it. |
| ✅ | **Undo deletes** | Deleted spools go to "Recently deleted" for 30 days instead of disappearing. |

## Your data

| | Feature | What it does |
|---|---|---|
| ✅ | **Backup and restore** | One-click backup of everything to a file, and restore from one (with a safety copy first). |
| ✅ | **CSV export** | Inventory and print history as spreadsheets. |
| ✅ | **Automatic backups to a NAS or any folder** | Scheduled backups (daily or weekly) to a folder you choose, such as a NAS share mounted in Finder, an external drive or a cloud-synced folder. Old backups are pruned automatically, and failures (e.g. the NAS isn't connected) are shown and retried. |

## Release and project

| | Feature | What it does |
|---|---|---|
| ✅ | **App name** | **Spoolhouse** ([spoolhouse.app](https://spoolhouse.app)), "Filament inventory for Creality CFS". Creality and CFS stay out of the name itself (they're Creality's trademarks). |
| ✅ | **App icon** | "One Strand": a single line of filament that winds into a spool and draws the house (`branding/Spoolhouse.svg`). |
| ✅ | **Update available notice** | Checks GitHub releases once a day; notification, a card with Download / Later / Skip this version, and Settings → Updates. |
| 📋 | **In-app updates** | Download and install a new version from inside the app (Settings → Updates), keeping your data, instead of replacing the app by hand. |
| 📋 | **Developer ID signing and notarization** | Opens without the "unidentified developer" warning (needs an Apple Developer membership). |
| ✅ | **Split the interface into files** | Move the page out of `cfs_gui.py` into separate HTML, CSS and JS files, so it's easier to contribute to. |
| ✅ | **Automated tests** | Tests for stock, charging and refund maths, run on every change (GitHub Actions). |

## Other platforms

| | Feature | What it does |
|---|---|---|
| 📋 | **Windows app** | Same app on Windows: system tray icon instead of the menu bar, start with Windows, data in `%APPDATA%`. Tag writing, inventory and printer tracking are shared code. Built and tested on a Windows PC with an ACR122U (may need ACS's driver). |
| 📋 | **Automatic builds (GitHub Actions)** | Build the Mac and Windows downloads automatically for each GitHub release. |
| 📋 | **Android companion app** | Use the phone's NFC to scan spools at the shelf or printer and send them over Wi-Fi to the Mac/Windows app, so there's one inventory. Needs a phone with an NXP NFC chip: many phones, including many Samsung models, can't read MIFARE Classic tags. |
| 📋 | **Standalone Android app** | A full app with its own inventory. Larger job. |

## More printers and filament

| | Feature | What it does |
|---|---|---|
| 📋 | **Bambu Lab spools (read-only)** | Scan Bambu spools into inventory. Writing isn't possible: Bambu tags are signed. |
| 📋 | **Anycubic ACE Pro** | Research reading/writing its NTAG tags. |
| 📋 | **Other systems** | Qidi, Snapmaker, Elegoo and Prusa OpenPrintTag, as their formats become known. |
