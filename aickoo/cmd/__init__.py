#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@Project:    Aickoo-Assistant
@Author:     艾可科技（昆山）有限责任公司
@Contact:    aickoo@163.com
@CreateTime: 2026-07-07
@Copyright:  Copyright (c) 2026 艾可科技（昆山）有限责任公司
@License:    All Rights Reserved.

Command-line interface for Aickoo-Assistant
"""

import click
import os
import sys
from typing import Optional
from aickoo import logging
from aickoo.internal.config import load_config
from aickoo.internal.db import connect_db
from aickoo.internal.app import App
from aickoo.internal.format import OutputFormat, validate_format


@click.group()
@click.option("--debug", "-d", is_flag=True, help="Enable debug mode")
@click.option("--cwd", "-c", type=click.Path(exists=True), help="Set current working directory")
@click.option("--prompt", "-p", type=str, help="Prompt to run in non-interactive mode")
@click.option("--output-format", "-f", type=str, default="text", 
              help="Output format for non-interactive mode (text, json)")
@click.option("--quiet", "-q", is_flag=True, help="Hide spinner in non-interactive mode")
@click.option("--version", "-v", is_flag=True, help="Show version")
@click.pass_context
def cli(ctx, debug: bool, cwd: Optional[str], prompt: Optional[str], 
        output_format: str, quiet: bool, version: bool):
    """Aickoo-Assistant cli"""
    
    ctx.ensure_object(dict)
    ctx.obj["debug"] = debug
    ctx.obj["cwd"] = cwd
    ctx.obj["prompt"] = prompt
    ctx.obj["output_format"] = output_format
    ctx.obj["quiet"] = quiet
    
    if version:
        from aickoo import __version__
        click.echo(f"Aickoo-Assistant v{__version__}")
        sys.exit(0)
    
    # Validate format option
    if not validate_format(output_format):
        click.echo(f"Invalid format option: {output_format}")
        click.echo("Supported formats: text, json")
        sys.exit(1)
    
    # Change directory if specified
    if cwd:
        try:
            os.chdir(cwd)
        except Exception as e:
            click.echo(f"Failed to change directory: {e}", err=True)
            sys.exit(1)
    
    # Get current working directory
    if not cwd:
        try:
            cwd = os.getcwd()
        except Exception as e:
            click.echo(f"Failed to get current working directory: {e}", err=True)
            sys.exit(1)
    
    ctx.obj["cwd"] = cwd
    
    # Load configuration
    try:
        config = load_config(cwd, debug)
        ctx.obj["config"] = config
    except Exception as e:
        click.echo(f"Failed to load configuration: {e}", err=True)
        sys.exit(1)
    
    # Setup logging
    logging.setup_logging(debug=debug,cwd=cwd)


@cli.command()
@click.pass_context
def run(ctx):
    """Run Aickoo-Assistant in interactive mode"""
    debug = ctx.obj["debug"]
    cwd = ctx.obj["cwd"]
    config = ctx.obj["config"]
    
    try:
        # Connect to database
        conn = connect_db()
        
        # Create application
        app = App(conn, config)
        
        # Run interactive mode
        app.run_interactive()
        
    except Exception as e:
        logging.error(f"Failed to run Aickoo-Assistant: {e}")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.pass_context
def prompt(ctx):
    """Run a single prompt in non-interactive mode"""
    prompt_text = ctx.obj["prompt"]
    output_format = ctx.obj["output_format"]
    quiet = ctx.obj["quiet"]
    config = ctx.obj["config"]
    
    if not prompt_text:
        click.echo("Error: --prompt option is required for non-interactive mode", err=True)
        sys.exit(1)
    
    try:
        # Connect to database
        conn = connect_db()
        
        # Create application
        app = App(conn, config)
        
        # Run non-interactive mode
        result = app.run_non_interactive(prompt_text, output_format, quiet)
        
        # Output result
        if output_format == OutputFormat.JSON:
            import json
            click.echo(json.dumps({"response": result}))
        else:
            click.echo(result)
            
    except Exception as e:
        logging.error(f"Failed to run prompt: {e}")
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def execute():
    """Execute the CLI"""
    cli(obj={})