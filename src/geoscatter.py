import os
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from .AppLogger import Logger
from .config_ import Config
import random
from pathlib import Path

class GeoAnalysis:
    def __init__(self, config: Config, logger: Logger):
        self.logger = logger
        self.config = config
        self.class_colors = {}
        self.output_folder = self.config.get_current_working_folder() / 'Scatter'
        self.region = self.config.get_general_data()['region']
        if not self.output_folder.exists():
            self.output_folder.mkdir()

    def _assign_colors(self, classes):
        BANNED = {"#D3D3D3", "#000000"} #The Background grey and Pure black are banned
        for cls in classes:
            for attempt in range(10_000):
                colour = "#" + "".join(random.choices("0123456789ABCDEF", k=6))
                if colour not in BANNED:
                    self.class_colors[cls] = colour
                    break
            else:
                self.logger.log_status("I was unable to choose te colours for a geoscatter", "WARNING")
            self.class_colors[cls] = colour

    def geoscatter(self, location_file, output_folder: Path|None = None):
        
        location_file = self.config.get_paths_data()["geoscatter_path"]
        self.output_folder = output_folder or self.output_folder
        
        import json
        with open(self.config.get_map_index_path(), 'r') as f:
            coords = json.load(f)
        
        try:
            self.logger.log_status("Geoscatter started.")
            latlong_class : dict[tuple[float, float], str] = {}
            with open(location_file, 'r') as f:
                for line in f:
                    line = line[:-2]
                    parts = line.strip().split(':')
                    if len(parts) == 3:
                        lat, lon, cls = parts
                        latlong_class[(float(lat), float(lon))] = cls

            classes = set(latlong_class.values())
            self._assign_colors(classes)

            fig = plt.figure(figsize=(10, 5))
            ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
            ax.set_extent(coords[self.region], crs=ccrs.PlateCarree())
            ax.coastlines()
            ax.add_feature(cfeature.BORDERS)
            ax.add_feature(cfeature.LAND, facecolor='lightgray')
            ax.add_feature(cfeature.OCEAN, facecolor='lightblue')

            for (lat, lon), cls in latlong_class.items():
                color = self.class_colors.get(cls, 'black')
                ax.plot(lon, lat, marker='o', color=color, markersize=6, transform=ccrs.Geodetic())

            legend_handles = [
                Line2D([0], [0],
                    marker='o',
                    color=self.class_colors[cls],
                    linestyle='None',
                    markersize=6,
                    label=cls)
                for cls in sorted(self.class_colors)
            ]

            ax.legend(handles=legend_handles,
                  title="Classes",
                  loc="lower left",
                  frameon=True,
                  fontsize="small",
                  title_fontsize="medium")

            plt.savefig(os.path.join(self.output_folder, 'geoscatter_plot.png'), bbox_inches='tight')
            plt.close()

            self.logger.log_status(f"Plot saved to {self.output_folder}")
            self.logger.log_status("Geoscatter finished successfully.")

        except Exception as e:
            self.logger.log_status(f"Geoscatter error: {e}")


# class GeoAnalysis:
#     def __init__(self, config: Config, logger: Logger):
#         self.logger = logger
#         self.config = config ### config.get('filename', 'data.txt')????? config.get('output_file', 'geoscatter_plot.png')?????
#         self.input_folder = "" ###
#         self.output_folder = "" ###

#     def geoscatter(self):
#         input_folder, output_folder, logger, config = self.input_folder, self.output_folder, self.logger, self.config
#         try:
#             logger.log_status("Geoscatter started.")

#             # Read the data file
#             input_file = os.path.join(input_folder, config.get('filename', 'data.txt'))
#             logger.log_status(f"Reading data from {input_file}")

#             latitudes = []
#             longitudes = []
#             colors = []

#             with open(input_file, 'r') as f:
#                 for line in f:
#                     parts = line.strip().split(':')
#                     if len(parts) == 3:
#                         lat, lon, color = parts
#                         latitudes.append(float(lat))
#                         longitudes.append(float(lon))
#                         colors.append(color)

#             logger.log_status(f"Read {len(latitudes)} coordinates.")

#             # Create plot
#             fig = plt.figure(figsize=(10, 5))
#             ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
#             ax.set_global()
#             ax.coastlines()
#             ax.add_feature(cfeature.BORDERS)
#             ax.add_feature(cfeature.LAND, facecolor='lightgray')
#             ax.add_feature(cfeature.OCEAN, facecolor='lightblue')

#             for lat, lon, color in zip(latitudes, longitudes, colors):
#                 ax.plot(lon, lat, marker='o', color=color, markersize=6, transform=ccrs.Geodetic())

#             # Save output
#             output_path = os.path.join(output_folder, config.get('output_file', 'geoscatter_plot.png'))
#             plt.savefig(output_path, bbox_inches='tight')
#             plt.close()

#             logger.log_status(f"Plot saved to {output_path}")
#             logger.log_status("Geoscatter finished successfully.")

#         except Exception as e:
#             logger.log_status(f"Geoscatter error: {str(e)}")

#     def show_scatter(self):
#         # Get the latest evaluated geoscatter
#         # A dropdown that allows you to choose from all the geoscatters
#         # A function that goes through the lat:long classifies file and checks if it has been turned into a map or not. 
#         # The file should have two parts: the headers that contain the metadata and the part that contains the data. The metadata should include if the file has been converted to a map or not, what is the nominal name of the file, the path of the file. 
#         pass