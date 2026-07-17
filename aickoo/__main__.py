#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Project:    Aickoo-Assistant
@Author:     艾可科技（昆山）有限责任公司
@Contact:    aickoo@163.com
@CreateTime: 2026-07-07
@Copyright:  Copyright (c) 2026 艾可科技（昆山）有限责任公司
@License:    All Rights Reserved.
"""

import sys
import traceback
from aickoo import logging
from aickoo.cmd import execute


def main():
    """Main entry point for Aickoo-Assistant"""
    try:
        execute()
    except Exception as e:
        logging.error(f"Application terminated due to unhandled error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()