import os
import logging
from PIL import Image, ImageDraw

def create_system_icon():
    """Create the system tray icon if it doesn't already exist."""
    resources_path = os.path.join(os.getcwd(), "resources")
    os.makedirs(resources_path, exist_ok=True)  # Ensure the resources folder exists

    icon_path = os.path.join(resources_path, "system.ico")
    if not os.path.exists(icon_path):
        img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([4, 4, 28, 28], fill="blue")
        img.save(icon_path, format="ICO")

def create_resource_files():
    """Ensure the required resource files and folders are created in the resources folder."""
    resources_path = os.path.join(os.getcwd(), "resources")
    os.makedirs(resources_path, exist_ok=True)  # Ensure the resources folder exists

    # Create block_list.txt if it doesn't exist
    block_list_path = os.path.join(resources_path, "block_list.txt")
    if not os.path.exists(block_list_path):
        with open(block_list_path, "w") as f:
            f.write(
                "# Add/remove entries automatically by right-clicking notifications\n"
                "# Add full path to block specific processes\n"
                "# Example: C:\\Program Files\\MyApp\\MyApp.exe\n"
                "# Add folder path to block all processes in a directory\n"
                "# Example: C:\\Program Files\\\n"
                "# Add process name for blanket blocking\n"
                "# Example: MyApp.exe\n"
                "# --------------------------------------------------------------------\n"
            )

    # Create allow_list.txt if it doesn't exist
    allow_list_path = os.path.join(resources_path, "allow_list.txt")
    if not os.path.exists(allow_list_path):
        with open(allow_list_path, "w") as f:
            f.write(
                "# Add entries to allow specific processes (overrides block list)\n"
                "# Add full path to allow specific processes\n"
                "# Example: C:\\Program Files\\MyApp\\MyApp.exe\n"
                "# Add folder path to allow all processes in a directory\n"
                "# Example: C:\\Program Files\\\n"
                "# Add process name for blanket allowing\n"
                "# Example: MyApp.exe\n"
                "# --------------------------------------------------------------------\n"
            )

    # Create custom_icons.txt if it doesn't exist
    custom_icons_path = os.path.join(resources_path, "custom_icons.txt")
    if not os.path.exists(custom_icons_path):
        with open(custom_icons_path, "w") as f:
            f.write(
                '# Format: "Path", "Icon name"\n'
                '# Format: "Process name", "Icon name"\n'
                '# Example: "C:\\Program Files\\MyApp\\example.exe", "example_icon"\n'
                '# Example: "example.exe", "example_icon"\n'
                '# --------------------------------------------------------------------\n'
            )

    # Create custom_icons folder if it doesn't exist
    custom_icons_folder = os.path.join(resources_path, "custom_icons")
    os.makedirs(custom_icons_folder, exist_ok=True)