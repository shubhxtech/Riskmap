
import sys
import os
from PyQt5.QtWidgets import QApplication
import qtawesome as qta
from PyQt5.QtCore import QSize

def generate_icons():
    app = QApplication(sys.argv)
    
    # Define paths
    base_path = os.path.dirname(os.path.abspath(__file__))
    assets_path = os.path.join(base_path, "assets", "icons")
    
    if not os.path.exists(assets_path):
        os.makedirs(assets_path)
        
    print(f"Generating icons in: {assets_path}")

    # Generate Arrow Down (Normal State - Grey)
    icon_down = qta.icon('fa5s.chevron-down', color='#5f6368')
    pixmap_down = icon_down.pixmap(QSize(16, 16))
    pixmap_down.save(os.path.join(assets_path, "arrow_down.png"))
    print("Generated arrow_down.png")

    # Generate Arrow Up (Open State - Brand Blue)
    icon_up = qta.icon('fa5s.chevron-up', color='#1DA1F2')
    pixmap_up = icon_up.pixmap(QSize(16, 16))
    pixmap_up.save(os.path.join(assets_path, "arrow_up.png"))
    print("Generated arrow_up.png")

if __name__ == "__main__":
    try:
        generate_icons()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
