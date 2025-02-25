import os
import io
import logging
import win32gui
import win32api
import win32con
import win32ui
from PIL import Image, ImageDraw
from PyQt5.QtGui import QIcon, QPixmap, QImage, QColor
from datetime import datetime

def create_default_icon(process_name=None):
    """
    Create a default icon for processes with no available icon.
    If process_name is provided, creates a unique color based on the name.
    """
    try:
        # Create a transparent background
        img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # If process name provided, generate a unique color based on the name
        if process_name:
            # Generate a pastel color based on hash of process name
            name_hash = hash(process_name) % 0xFFFFFF
            r = ((name_hash >> 16) & 0xFF) 
            g = ((name_hash >> 8) & 0xFF)
            b = (name_hash & 0xFF)
            
            # Make the color more pastel/soft
            r = (r + 255) // 2
            g = (g + 255) // 2
            b = (b + 255) // 2
            
            # Ensure minimum brightness for visibility
            brightness = (r * 299 + g * 587 + b * 114) / 1000
            if brightness < 128:  # Too dark
                factor = 128 / max(1, brightness)
                r = min(255, int(r * factor))
                g = min(255, int(g * factor))
                b = min(255, int(b * factor))
                
            color = (r, g, b, 255)
        else:
            # Default gray if no process name
            color = (128, 128, 128, 255)
        
        # Draw the background circle
        padding = 2
        draw.ellipse(
            [padding, padding, 32 - padding, 32 - padding], 
            fill=color
        )
        
        # Add a white dot in the center
        center = 16
        dot_size = 3
        draw.ellipse(
            [center - dot_size, center - dot_size, 
             center + dot_size, center + dot_size],
            fill=(255, 255, 255, 255)
        )
        
        # Convert to QIcon
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return QIcon(QPixmap.fromImage(QImage.fromData(buffer.getvalue())))
    except Exception as e:
        logging.error(f"Failed to create default icon: {e}")
        # Fallback to a simple colored QPixmap
        try:
            pixmap = QPixmap(32, 32)
            pixmap.fill(QColor(128, 128, 128))
            return QIcon(pixmap)
        except:
            # Ultimate fallback - empty icon
            return QIcon()

def extract_regular_icon(exe_path, process_name):
    """Extract icon from a regular executable with multiple fallback methods."""
    # Method 1: Use ExtractIconEx - the standard way
    try:
        ico_x = win32api.GetSystemMetrics(win32con.SM_CXICON)
        ico_y = win32api.GetSystemMetrics(win32con.SM_CYICON)

        large, small = win32gui.ExtractIconEx(exe_path, 0)
        if large or small:
            icon_handle = large[0] if large else small[0]
        
            try:
                # Create DC and bitmap
                hdc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
                hdc_mem = hdc.CreateCompatibleDC()
                bmp = win32ui.CreateBitmap()
                bmp.CreateCompatibleBitmap(hdc, ico_x, ico_y)
                hdc_mem.SelectObject(bmp)

                # Draw icon
                hdc_mem.DrawIcon((0, 0), icon_handle)
                bmp_bits = bmp.GetBitmapBits(True)

                # Convert to QIcon
                img = Image.frombuffer('RGBA', (ico_x, ico_y), bmp_bits, 'raw', 'BGRA', 0, 1)
                buffer = io.BytesIO()
                img.save(buffer, format="PNG")
                qicon = QIcon(QPixmap.fromImage(QImage.fromData(buffer.getvalue())))
                
                return qicon

            finally:
                # Cleanup Windows resources
                for resource in [icon_handle] + list(large or []) + list(small or []):
                    if resource and resource != icon_handle:
                        win32gui.DestroyIcon(resource)
                if 'hdc_mem' in locals():
                    hdc_mem.DeleteDC()
                if 'hdc' in locals():
                    hdc.DeleteDC()
                if 'bmp' in locals():
                    win32gui.DeleteObject(bmp.GetHandle())
    except Exception as e:
        logging.debug(f"Primary icon extraction failed for {process_name}: {e}")
        # Continue to fallback methods
    
    # Method 2: Try extracting a different icon index
    try:
        # Try other icon indices (0-5) - many applications have multiple icons
        for idx in range(1, 6):  # Skip 0 as we already tried it
            try:
                large, small = win32gui.ExtractIconEx(exe_path, idx)
                if large or small:
                    icon_handle = large[0] if large else small[0]
                    
                    # Create DC and bitmap
                    hdc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
                    hdc_mem = hdc.CreateCompatibleDC()
                    bmp = win32ui.CreateBitmap()
                    bmp.CreateCompatibleBitmap(hdc, 32, 32)  # Use standard size
                    hdc_mem.SelectObject(bmp)

                    # Draw icon
                    hdc_mem.DrawIcon((0, 0), icon_handle)
                    bmp_bits = bmp.GetBitmapBits(True)

                    # Convert to QIcon
                    img = Image.frombuffer('RGBA', (32, 32), bmp_bits, 'raw', 'BGRA', 0, 1)
                    buffer = io.BytesIO()
                    img.save(buffer, format="PNG")
                    qicon = QIcon(QPixmap.fromImage(QImage.fromData(buffer.getvalue())))
                    
                    # Cleanup
                    for resource in [icon_handle] + list(large or []) + list(small or []):
                        if resource and resource != icon_handle:
                            win32gui.DestroyIcon(resource)
                    hdc_mem.DeleteDC()
                    hdc.DeleteDC()
                    win32gui.DeleteObject(bmp.GetHandle())
                    
                    logging.debug(f"Successfully extracted alternate icon (index {idx}) for {process_name}")
                    return qicon
            except Exception:
                continue  # Try next index
    except Exception as e:
        logging.debug(f"Alternate icon index extraction failed for {process_name}: {e}")
    
    # Method 3: Try to extract from shell32.dll based on extension
    try:
        # Get file extension
        _, ext = os.path.splitext(exe_path.lower())
        
        # Shell32.dll default icon mapping
        ext_icon_map = {
            '.exe': 3,   # Generic application icon
            '.dll': 72,  # DLL icon
            '.txt': 70,  # Text file icon
            '.bat': 73,  # Batch file icon
            '.cmd': 73,  # Command file icon
            '.msi': 74,  # Installer icon
            '.sys': 76,  # System file icon
            '.ini': 69,  # Configuration file icon
            '.log': 70,  # Log file icon
        }
        
        # Default to application icon if extension not mapped
        shell_icon_index = ext_icon_map.get(ext, 3)
        
        shell32_path = os.path.join(os.environ['SystemRoot'], 'System32', 'shell32.dll')
        large, small = win32gui.ExtractIconEx(shell32_path, shell_icon_index, 1, 1)
        
        if large or small:
            icon_handle = large[0] if large else small[0]
            
            # Create DC and bitmap
            hdc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
            hdc_mem = hdc.CreateCompatibleDC()
            bmp = win32ui.CreateBitmap()
            bmp.CreateCompatibleBitmap(hdc, 32, 32)
            hdc_mem.SelectObject(bmp)

            # Draw icon
            hdc_mem.DrawIcon((0, 0), icon_handle)
            bmp_bits = bmp.GetBitmapBits(True)

            # Convert to QIcon
            img = Image.frombuffer('RGBA', (32, 32), bmp_bits, 'raw', 'BGRA', 0, 1)
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            qicon = QIcon(QPixmap.fromImage(QImage.fromData(buffer.getvalue())))
            
            # Cleanup
            for resource in [icon_handle] + list(large or []) + list(small or []):
                if resource and resource != icon_handle:
                    win32gui.DestroyIcon(resource)
            hdc_mem.DeleteDC()
            hdc.DeleteDC()
            win32gui.DeleteObject(bmp.GetHandle())
            
            logging.debug(f"Successfully extracted shell32 icon for {process_name}")
            return qicon
    except Exception as e:
        logging.debug(f"Shell32 icon extraction failed for {process_name}: {e}")
    
     # Method 4: Generate a text-based icon with the first letter
    try:
        # Create a text-based icon with the first letter of the process name
        img = Image.new('RGBA', (32, 32), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Draw a colored circle background
        bgcolor = hash(process_name) % 0xFFFFFF  # Generate a color from the process name hash
        r = (bgcolor >> 16) & 0xFF
        g = (bgcolor >> 8) & 0xFF
        b = bgcolor & 0xFF
        
        # Ensure the color isn't too light
        r = max(30, min(220, r))
        g = max(30, min(220, g))
        b = max(30, min(220, b))
        
        draw.ellipse([2, 2, 30, 30], fill=(r, g, b, 255))
        
        # Add a white circle in the center
        draw.ellipse([13, 13, 19, 19], fill=(255, 255, 255, 255))
        
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        qicon = QIcon(QPixmap.fromImage(QImage.fromData(buffer.getvalue())))
        
        logging.debug(f"Created text-based icon for {process_name}")
        return qicon
    except Exception as e:
        logging.debug(f"Text-based icon creation failed for {process_name}: {e}")
        
    # All methods failed
    return None