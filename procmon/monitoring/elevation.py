import logging
import win32api
import win32con
import win32security

def is_process_elevated(pid):
    """
    Check if a process with the given PID is running with elevated privileges.
    
    Args:
        pid: Process ID to check
    
    Returns:
        bool: True if the process is elevated, False otherwise
    """
    try:
        # Convert string PID to integer if necessary
        if isinstance(pid, str) and pid.startswith("PID:"):
            pid = int(pid.split(":")[-1].strip())
        elif isinstance(pid, str):
            pid = int(pid)
        
        # Get process handle
        process_handle = win32api.OpenProcess(
            win32con.PROCESS_QUERY_INFORMATION, False, pid
        )
        
        if not process_handle:
            return False
            
        # Get process token
        token_handle = win32security.OpenProcessToken(
            process_handle, win32con.TOKEN_QUERY
        )
        
        # Check for elevation
        elevation = win32security.GetTokenInformation(
            token_handle, win32security.TokenElevation
        )
        
        # Clean up handles
        win32api.CloseHandle(process_handle)
        win32api.CloseHandle(token_handle)
        
        return bool(elevation)
    except Exception as e:
        # Log the error but don't crash
        logging.error(f"Error checking elevation for PID {pid}: {e}")
        return False