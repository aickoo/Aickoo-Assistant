#!/usr/bin/env python3
"""
Generate a shell command to download a file from a URL.
Usage: python generate_download_command.py <URL>
"""

import sys
import os
import platform
import subprocess

def get_download_command(url: str) -> str:
    """
    Return a shell command to download the given URL.
    Prefers wget if available, otherwise uses curl.
    """
    # Check if wget is available
    try:
        if platform.system() == "Windows":
            # On Windows, check if wget is in PATH
            result = subprocess.run(["where", "wget"], capture_output=True, text=True)
        else:
            result = subprocess.run(["which", "wget"], capture_output=True, text=True)
        if result.returncode == 0:
            # wget available
            return f'wget "{url}"'
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    
    # Fallback to curl (assumed to be available on most systems)
    # Use -L to follow redirects, -O to save with remote filename
    return f'curl -L -O "{url}"'

def main():
    if len(sys.argv) != 2:
        print("Usage: python generate_download_command.py <URL>")
        sys.exit(1)
    
    url = sys.argv[1]
    command = get_download_command(url)
    print(command)

if __name__ == "__main__":
    main()