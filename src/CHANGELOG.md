Ver 2.1 (UI Modernization)
------ Completed changes -----
. Implemented a global Dark Theme (dark grey background, blue accents, light text) via `styles.py`.
. Updated application font to "Segoe UI" for a modern look.
. Modernized `OverlaySidebar` with better styling, distinct background, and a "Tools" header.
. Added a "Close" button to the sidebar for better accessibility.
. Fixed `QEasingCurve` import error preventing animations.
. Refined layouts in `ApiWindow`, `BuildingDetectionWindow`, and `CropStreetWindow` with proper margins and spacing.
. Updated color schemes for UI elements (e.g., city dropdown) to ensure visibility in dark mode.

Ver 0.1
------ Completed changes -----

. Added secrets.env creation form popup to ApiWindow.py
. Updated default config in config_.py
. Added multiple locations support to the Map presented by google Maps API in ApiWindow.py
. Added updater script and Icon to desktop. Will run updates on github code and models.zip if run.
. Turned on showing cmd line processing for all processes that occur via command line
. Created documentation and documentaion page for the app (developer-guide/modules/ApiWindow.md && index.md && developer-guide/contributing.md)
. Added a Pixel Map to the CropWindow UI that shows the to be edited image and allows the user to modify the height of the image that is removed
. Remove uninstaller when uninstalling
. Add progress bars to the installation and uninstallation process 

------ Ever running changes ------

. [Update the documentation as changes are made]

------ Slotted Changes ------


Line 31 of Duplicates_Better.py -> os.environ['TF_KERAS_CACHE_DIR'] = resolve_path('..\models') ## Shift this hardcoded dependency to config file
. Complete the documentation page


