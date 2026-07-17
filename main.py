#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Project:    Aickoo-Assistant
@Author:     艾可科技（昆山）有限责任公司
@Contact:    aickoo@163.com
@CreateTime: 2026-07-07
@Copyright:  Copyright (c) 2026 艾可科技（昆山）有限责任公司
@License:    All Rights Reserved.

Aickoo Assistant - A powerful terminal-based AI assistant for developers
Python rewrite of the original Go project
"""

import os
import sys
import traceback
from pathlib import Path

root_path = Path(__file__).resolve().parent
if str(root_path) not in sys.path:
    sys.path.insert(0, str(root_path))

from aickoo import logging
from aickoo.cmd import execute
from aickoo.internal.splash_screen import show_splash

def main():
    """Main entry point for Aickoo AI"""

    splash = None
    try:
        splash = show_splash()
        execute()
    except Exception as e:
        logging.error(f"Application terminated due to unhandled error: {e}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        if splash:
            splash.hide()
            logging.info("Splash screen hidden")
        os._exit(0)


if __name__ == "__main__":
    main()