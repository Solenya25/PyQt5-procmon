import os
import io
import glob
import logging
import subprocess
import xml.etree.ElementTree as ET
from PIL import Image
from PyQt5.QtGui import QIcon, QPixmap, QImage
from datetime import datetime

def get_uwp_package_info():
    """Get information about installed UWP packages."""
    packages = {}
    try:
        powershell_command = (
            'Get-AppxPackage | Select-Object PackageFamilyName, InstallLocation | '
            'ConvertTo-Csv -NoTypeInformation'
        )
        result = subprocess.run(
            ['powershell', '-Command', powershell_command],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW  # Suppress console window
        )
    
        # Skip header row and process results
        for line in result.stdout.strip().split('\n')[1:]:
            if ',' in line:
                family_name, install_location = line.strip('"').split('","')
                packages[family_name] = install_location.strip('"')  # Strip quotes from install location
        
        logging.debug(f"Found {len(packages)} UWP packages")
    except Exception as e:
        logging.error(f"Error getting UWP packages: {e}")
    return packages

def get_uwp_icon_path(install_location):
    """Extract icon path from UWP app installation directory."""
    try:
        manifest_path = os.path.join(install_location, 'AppxManifest.xml')
        if not os.path.exists(manifest_path):
            logging.debug(f"No manifest found at {manifest_path}")
            return None

        # Parse the manifest XML
        tree = ET.parse(manifest_path)
        root = tree.getroot()
    
        # Define the XML namespaces
        namespaces = {
            'default': 'http://schemas.microsoft.com/appx/manifest/foundation/windows10',
            'uap': 'http://schemas.microsoft.com/appx/manifest/uap/windows10'
        }
    
        # Look for various possible icon paths
        possible_paths = [
            './/uap:VisualElements',
            './/default:VisualElements',
            './/VisualElements'
        ]
    
        for path in possible_paths:
            elements = root.findall(path, namespaces)
            if elements:
                for element in elements:
                    logo_path = None
                    if 'Square44x44Logo' in element.attrib:
                        logo_path = element.attrib['Square44x44Logo']
                    elif 'Logo' in element.attrib:
                        logo_path = element.attrib['Logo']
                    
                    if logo_path:
                        # Handle scale variations
                        base_path = os.path.join(install_location, logo_path)
                        base_dir = os.path.dirname(base_path)
                        base_name = os.path.splitext(os.path.basename(base_path))[0]
                    
                        # Search for any matching icon files
                        possible_files = glob.glob(os.path.join(base_dir, f"{base_name}.*"))
                        if possible_files:
                            # Prefer larger scale versions if available
                            for scale in ['200', '150', '100']:
                                scaled = [f for f in possible_files if f'.scale-{scale}' in f]
                                if scaled:
                                    logging.debug(f"Found scaled icon: {scaled[0]}")
                                    return scaled[0]
                            logging.debug(f"Using first available icon: {possible_files[0]}")
                            return possible_files[0]
        
        logging.debug(f"No suitable icon found in manifest at {manifest_path}")
    except Exception as e:
        logging.error(f"Error extracting UWP icon path: {e}")
    return None

def extract_windowsapps_icon(process):
    """Extract icon for UWP/WindowsApps applications."""
    try:
        exe_path = process.exe()
        process_name = process.name()
    
        # Get UWP package info
        packages = get_uwp_package_info()
    
        # Find the matching package
        install_location = None
        for family_name, pkg_location in packages.items():
            if exe_path.lower().startswith(pkg_location.lower()):
                install_location = pkg_location
                break
            
        if not install_location:
            logging.debug(f"No matching UWP package found for {exe_path}")
            return None
        
        # Get the icon path
        icon_path = get_uwp_icon_path(install_location)
        if not icon_path or not os.path.exists(icon_path):
            logging.debug(f"No valid icon path found for {process_name}")
            return None
        
        # Load and process the icon
        try:
            img = Image.open(icon_path)
            img = img.convert('RGBA')
            img = img.resize((32, 32), Image.Resampling.LANCZOS)
        
            # Convert to QIcon
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            qicon = QIcon(QPixmap.fromImage(QImage.fromData(buffer.getvalue())))
        
            logging.info(f"Successfully loaded UWP icon from {icon_path}")
            return qicon
        except Exception as e:
            logging.error(f"Failed to load icon {icon_path}: {e}")
            return None

    except Exception as e:
        logging.error(f"UWP icon extraction failed for {process_name}: {str(e)}")
        return None