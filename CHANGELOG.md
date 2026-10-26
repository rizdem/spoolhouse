# Changelog

Versions follow [semantic versioning](https://semver.org): **major** for big or breaking
changes, **minor** for new features, **patch** for bug fixes.

## 2.0.2 - 2026-10-26

### Changed
- The menu bar shows Spoolhouse's own icon (a line version of One Strand that follows a light or dark menu bar) in
  place of the printer symbol.

## 2.0.1 - 2026-10-26

### Added
- Spoolhouse has its own app icon: one strand of filament that winds into a spool and draws the house.

## 2.0.0 - 2026-10-26

### Changed
- **CFS Tag Writer is now Spoolhouse** ([spoolhouse.app](https://spoolhouse.app)): filament inventory for
  Creality CFS. The app, window, menu bar, notifications, exports and backups use the new name, and the
  download is `Spoolhouse-<version>-apple-silicon.zip`.
- Data now lives in `~/Library/Application Support/Spoolhouse/`. On first launch your data is copied over from
  the CFS Tag Writer folder, which is left as it was (with a note saying where everything went), so nothing
  is lost. Logs are in `~/Library/Logs/Spoolhouse.log`.
- If "Open at login" was on, it's switched over to Spoolhouse automatically.
- macOS treats Spoolhouse as a new app, so it asks once more for permission to send notifications.
- Backups made by CFS Tag Writer can still be restored.

## 1.11.2 - 2026-10-26

### Fixed
- A slot's spool could be changed by accident (a stray key press on its dropdown), after which auto-linking
  left the wrong spool linked and charged it. Changing a slot away from the spool its tag identifies now asks
  first, and a slot linked against its tag shows a warning with "Switch back to the tagged spool".
- Will it fit? for a running print uses the printer's own routing of the print's filaments to CFS slots, so it
  always shows the spool actually feeding. For other files, a spool of the exact same Creality material is
  matched whatever colour the slicer used.
- Live tracking wrote a new usage entry at every check during a print. It now keeps one running entry per
  print, slot and spool, and existing entries are merged (totals unchanged).

## 1.11.1 - 2026-10-26

### Changed
- The interface now lives in its own files (`web/index.html`, `web/style.css` and `web/js/*.js`, one per
  area) instead of inside `cfs_gui.py`, which is now just the local server. No visible change.
- Automated tests (`tests/`, 53 so far) cover tag encoding, stock and charging maths, refunds, costs, backups,
  print-file and CFS parsing, fit checks, auto-linking, alerts and the local server. They run on every push
  with GitHub Actions.

### Fixed
- Settings in the browser version (cfs_gui.py) didn't load the notification and backup sections.

## 1.11.0 - 2026-10-26

### Added
- CFS slots link to your spools automatically. The printer reports the tag each spool in the CFS was loaded
  with (via Klipper's CFS data), so the app links the slot to the spool with the same serial, material and
  colour, and re-links when you swap spools. The slot says "Matched by its tag".
  - A loaded spool that isn't in your inventory shows "Not in your inventory (tag #…): scan it in", and links
    itself once you've scanned it.
  - If several spools share a tag (factory tags can repeat serials), it asks you to pick instead of guessing.
  - Unlinking a slot by hand, or linking it to a different spool, is respected for that spool.

## 1.10.2 - 2026-10-26

### Added
- Will it fit? checks your inventory too. A colour that isn't loaded shows whether you have it in stock and
  whether that's enough ("In stock: Green Creality CR-PETG · 493 g · enough", "not enough", or "Not in your
  inventory"). A loaded spool that's short shows whether another spool is in stock to swap in. The summary
  line takes this into account (e.g. "One colour isn't loaded yet, but you have enough in stock: load it
  before printing").

## 1.10.1 - 2026-10-26

### Fixed
- Will it fit?: picking a file while a print is running did nothing. The card now shows the running print's
  check and, underneath, the file you picked as "Next print", checked against what will be left once the
  current print finishes. Both refresh as the spools are used.

## 1.10.0 - 2026-10-26

### Added
- Shopping list (Inventory → Shopping list): every filament running low or used up in the last 60 days, with
  the last price you paid, where from and when; set quantities, add other filaments, hide ones you don't need
  (they come back if they run low again), see an estimated total, then copy the list or email it.
- Undo deletes: deleting spools (one or many) shows an Undo button, and deleted spools go to "Recently deleted"
  for 30 days, where you can restore them or delete them for good. Scanning the tag of a deleted spool offers
  to restore it. Print history keeps its colours and costs either way.

### Changed
- Deleting no longer asks "are you sure?" first, since it can be undone.

## 1.9.0 - 2026-10-26

### Added
- Will it fit? The app reads how much of each colour a print needs from its G-code (Creality Print / OrcaSlicer
  write this at the end of the file) and matches each colour to the CFS slot feeding it (Creality material ID,
  then type, then nearest colour).
  - While printing, the printer page shows each colour still needed against what its spool has left, and
    warns if one will run short.
  - Before printing, pick any file on the printer to check your loaded spools have enough.
- Charging a past print pre-fills the split from its print file, so multi-colour prints divide themselves.
- Humidity alert: the CFS heading turns amber ("too damp") and the printer card shows 💧 when a unit goes
  above your limit (Settings, default 50%).
- Mac notifications for: print finished or stopped (with filament used and cost), filament may run out, running
  low, prints to charge, CFS too damp, and the NFC reader being unplugged or plugged back in. Each can be
  switched off in Settings, which also has a test button. Clicking a notification opens the app.

## 1.8.1 - 2026-10-26

### Added
- "Buy me a beer" button in the sidebar, linking to the project's support page.

## 1.8.0 - 2026-10-26

### Added
- Menu bar mode: closing the window keeps the app running from a printer icon in the menu bar, so printer
  usage is still tracked. The menu shows each printer's status (e.g. "Printing · 12.3 m used · 221 g left"),
  low stock and usage waiting to be charged, and the icon shows metres used while printing. ⌘Q or Quit
  really quits. Can be turned off in Settings.
- Open at login: starts quietly in the menu bar when you log in.
- Cost per print in the print log, from the spools' prices, plus a this-month total of grams and cost for each
  printer. Correcting a spool's price updates its prints; deleting a spool keeps their cost.
- Settings page with backups:
  - Automatic backups to any folder (a NAS share mounted in Finder, an external drive or a cloud folder),
    daily or weekly, keeping the newest 7/14/30/90. If the folder isn't available the problem is shown and
    it's tried again every 10 minutes.
  - Save a backup to a file, and restore from one (a copy of your current data is saved first).
  - Export spools and print usage to CSV for Excel or Numbers.

## 1.7.3 - 2026-10-26

### Changed
- On a printer's page, Recent usage and Print log are collapsible sections, closed by default (the app
  remembers which you open). Closed, they still show a summary: the number of usage entries and the last
  one, and the number of prints with how many need attention.

## 1.7.2 - 2026-10-26

### Changed
- Create is responsive. With room (the default window and up), the choices (filament, colour, weight) sit
  on the left and a summary panel stays in view on the right: a larger spool preview, Printer, Tags per
  spool, Write tags and the status. Narrow windows keep a single column. Colour swatches reflow (12, 8 or
  6 per row) to fit their column.

## 1.7.1 - 2026-10-26

### Fixed
- The reader status in the sidebar now follows the NFC reader being unplugged and plugged back in
  (checked every 2.5 s while the app is visible) instead of only at start-up.

### Changed
- Reader status shows a coloured dot: green "Reader connected" with its name, red "No reader", or amber
  "Reader not responding" if macOS's card service stalls. A short notice pops up when it connects or disconnects.

## 1.7.0 - 2026-10-26

### Added
- Inventory totals: "Filament used" (what's gone from every spool, finished ones included) and "Cost used"
  (each spool's price times the share used). Like the other totals they follow your search and filters.
- Each total has a short breakdown underneath, e.g. "32% of 3.00 kg bought" or "69% of spend".

### Changed
- Sidebar order is Inventory, Printers, Create, and the app opens on Inventory by default.
- Totals are laid out as two rows of three (left on top, used underneath), or one row on wide windows.
  Amounts under 1 kg show in grams.

## 1.6.1 - 2026-10-26

### Changed
- Create: Printer and Tags per spool are always visible in their own card (no more "Advanced" fold-out),
  with clearer option names and a short explanation under each.
- Those two use the same style of picker as Filament type, without the search box (arrow keys, Enter
  and Esc still work).

## 1.6.0 - 2026-10-26

### Added
- Searchable filament picker on Create and in the spool form: type to filter (e.g. "hyper", "petg cf"),
  with matches highlighted, arrow keys to move, Enter to pick and Esc to close.

### Changed
- Creality filaments are listed before Generic ones, A-Z within each group.
- Create starts on Hyper PLA when there's no previous choice (it still remembers your last one).

## 1.5.0 - 2026-10-25

### Changed
- Every spool is added by scanning its tag (or straight after writing its tags on Create), so stock and
  usage stay accurate. The app also refuses to save a new spool without a tag.

### Removed
- "How many spools", "Add stock", the "+ Add" buttons in By filament, "+ Add spools of this" and
  "+ Add more like this".

### Added
- Spools added before this (without a tag) show "Scan tag to link" in their form. Scanning links the
  tag and updates the type and colour from it. A tag that already belongs to another spool is refused.

## 1.4.1 - 2026-10-25

### Fixed
- Charging a print no longer leaves a sliver as "0 g unassigned". The charge dialog now works out grams
  from the print's actual length and the chosen spool's material, extra rows pre-fill whatever is still
  unallocated, and a split within 3% of the whole print is saved as exactly 100%.
- Spool amounts are tracked to 0.1 g: charges and refunds deduct exact amounts instead of rounding to
  whole grams. Small amounts show a decimal (e.g. 0.4 g).
- Leftover slivers from charges made in 1.4.0 are folded into the spools those prints were charged to.

## 1.4.0 - 2026-10-25

### Added
- Charge any past print to the right spools: a dialog showing the print's details and total, where you
  pick the spool (or several for a multi-colour print, in grams from your slicer). It suggests the likely
  spool and shows how much is still unallocated.
- Edit any print's charges, including automatically tracked ones. Spools charged before get their grams
  back first, so corrections never double-count.
- Skip prints your spool amounts already include (with undo).
- Print log: a "Needs attention" filter with a count, highlighted rows, and "Load older prints" to go back
  through the printer's whole history.
- Usage records keep a snapshot of the filament's colour, material and brand, so history stays right when
  spools are edited or deleted, and unlinked-slot usage shows what was loaded. Existing records are filled
  in from their spools.

## 1.3.1 - 2026-10-25

### Fixed
- Form controls look consistent everywhere: dropdowns, text, number and date fields, colour pickers
  and buttons share one height, border and corner style (with a compact size in slot cards and tables).
- Dropdowns use a matching custom arrow instead of the native macOS style; number fields drop the
  up/down arrows; one focus ring for every field; date pickers and checkboxes follow light/dark mode.

## 1.3.0 - 2026-10-25

### Added
- Multiple printers. The Printers page lists every printer with its status (online, offline, printing),
  the colours loaded and how many slots still need linking. Click one to see its slots, usage and print log.
- Add printer form: name, model (K2, K2 Pro, K2 Plus, Hi, K1, K1C, K1 Max, K1 SE, Other) and IP address,
  with a Test connection button. Printers can be edited or removed later.
- Printers without a CFS get a single spool holder you can link a spool to.
- Inventory's printer badge includes the printer's name.

### Changed
- An existing single-printer setup is moved over automatically as "My printer", keeping its links and usage.

## 1.2.0 - 2026-10-25

### Added
- Inventory shows which spools are in the printer: a printer badge with the slot ("In printer · CFS 1 · Slot 2"),
  which turns solid with "Printing" while that slot is feeding. The By filament view counts them too.
- Location filter (In printer / On shelf).
- The spool form says which slot a spool is in.
- Past prints marked "Not tracked" can be charged to a spool from the print log, using the total the printer
  recorded for that job. Each print can only be charged once, and you're asked to confirm first.

## 1.1.1 - 2026-10-25

### Fixed
- Printer usage tracking now actually deducts filament. The CFS doesn't count a slot's remaining
  length down while printing, so 1.1.0 never charged anything. Usage now comes from Moonraker's
  running total for the job, charged to whichever slot is feeding (checked every 15 s while printing),
  with a final top-up when the print ends.
- Prints that ran while the app was closed, or from an unlinked slot, are logged as unassigned;
  assign them to a spool from the print log or the Recent usage list.
- CFS slot cards: consistent layout, equal heights, dropdowns aligned.

### Changed
- Printer page is responsive: slots go 4 across (2 x 2 when narrow), and the external holder
  shares the row on wide windows. Inventory also uses more width on big screens.
- "Use printer's estimate" when linking is now off by default (the CFS figure is only a snapshot
  from when the spool was loaded).

## 1.1.0 - 2026-10-25

### Added
- Printer page: connect to a Creality K-series printer on your network (read-only; tested on K2 Pro).
- Live CFS view: what's in each slot, grams and metres left, which slot is printing, CFS temperature and humidity.
- Link each CFS slot to a spool; filament the printer uses is deducted from that spool automatically
  (every 60 s while the app is open, catching up on prints that ran while it was closed).
- Spool swap detection: if a slot's remaining length jumps up, the link is dropped and you're asked which spool it is.
- Recent usage list and a print log (from Moonraker): each job's time, filament used in metres and grams,
  and which spools it came from.

### Changed
- Brighter green/red status colours in dark mode.

## 1.0.0 - 2026-10-25

First release.

### Added
- Write, read and wipe Creality CFS RFID tags with a USB NFC reader (ACR122U).
- Unique spool serials, checked against every serial the app has issued.
- Inventory: scan spools in, weigh-it remaining calculator, spool-equivalent totals,
  value left and total spent, running-low alerts.
- Search and filters (type, brand, colour family, shop); the totals follow the filters.
- By filament view, quick top-ups for untagged stock, multi-select delete.
- Native Apple Silicon app with a Support button.

### Fixed
- The reader can no longer freeze the app: reader calls time out, connections are
  released after every operation, and errors are logged.
