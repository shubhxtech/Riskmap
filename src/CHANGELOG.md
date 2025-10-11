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

. Aesthetic changes to the entire App
