---
name: download-command
description: Analyze a file URL and generate appropriate shell command for downloading (using curl or wget). Input: file URL. Output: shell command string.
license: MIT
---

# Download Command Skill

This skill analyzes a file URL and generates a shell command to download it using either curl or wget.

## Usage

When the user provides a file URL, this skill will generate a shell command that can be executed to download the file.

The command will prefer `wget` if available, otherwise fallback to `curl`. The generated command includes appropriate flags for handling redirects and saving with the original filename.

## Implementation

A Python script is provided that implements the logic. The script can be used directly or integrated into other tools.

### Script: `scripts/generate_download_command.py`

```python
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
```

### Example

Input: `https://example.com/file.zip`

Output (if wget is available): `wget "https://example.com/file.zip"`

Output (otherwise): `curl -L -O "https://example.com/file.zip"`

## Notes

- The command uses `-L` flag for curl to follow redirects.
- The command uses `-O` flag for curl to save with the remote filename.
- For wget, no additional flags are needed as it follows redirects by default and saves with the original filename.
- On Windows, the `where` command is used to check for wget availability.
- On Unix-like systems, the `which` command is used.