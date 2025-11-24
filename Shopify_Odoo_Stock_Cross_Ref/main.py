#!/usr/bin/env python3
"""
Helper script to synchronize inventory data between Odoo and Shopify.

This script can:
1. Update Shopify data by running refresh_shopify_data_current.py
2. Update Odoo data by running get_odoo_stock_current.py
3. Generate the stock cross-reference report with size mismatch detection

Usage:
  python sync_inventory.py --all         # Run both Shopify and Odoo updates
  python sync_inventory.py --shopify     # Update only Shopify data
  python sync_inventory.py --odoo        # Update only Odoo data (includes report generation)
  python sync_inventory.py --report      # Generate report only (no data updates)

Notes:
  - The --odoo option automatically generates reports after updating the data
  - The --report option uses the --report-only flag with get_odoo_stock_current.py
    to generate reports without updating any data
  - The --all option runs both updates but doesn't run a separate report generation
    since the Odoo update already includes report generation
"""

import argparse
import subprocess
import sys
import os
import datetime
import logging

# Get the absolute path of the directory containing this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Import systemname from odoosys
sys.path.append(os.path.dirname(SCRIPT_DIR))
try:
    from odoosys import systemname
except ImportError:
    systemname = "ORGANIZATION"  # Fallback if odoosys.py doesn't exist yet

# Define the output directory - using a subdirectory of the current workspace
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Create a shared-data directory in the current workspace if it doesn't exist
SHARED_DATA_DIR = os.path.join(SCRIPT_DIR, 'shared-data')
os.makedirs(SHARED_DATA_DIR, exist_ok=True)

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def run_command(command, description):
    """Run a command and handle errors."""
    logger.info(f"{'=' * 80}")
    logger.info(f"Running: {description}")
    logger.info(f"{'=' * 80}")
    
    # Set environment variables for the subprocess
    env = os.environ.copy()
    env['OUTPUT_DIR'] = OUTPUT_DIR
    
    try:
        result = subprocess.run(command, shell=True, check=True, text=True, capture_output=True, env=env)
        if result.stdout:
            for line in result.stdout.splitlines():
                logger.info(line)
        if result.stderr:
            logger.warning(f"Warnings:")
            for line in result.stderr.splitlines():
                logger.warning(line)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running {description}:")
        logger.error(f"Exit code: {e.returncode}")
        if e.stdout:
            for line in e.stdout.splitlines():
                logger.info(line)
        if e.stderr:
            for line in e.stderr.splitlines():
                logger.error(line)
        return False

def update_shopify_data():
    """Update Shopify data by running import_shopify_inventory.py to import inventory data from CSV exports.

    This method has been updated to only use the CSV export method, which provides access to all four
    inventory values (Unavailable, Committed, Available, On hand) and is more reliable than the API method.
    """
    command = f'python "{os.path.join(SCRIPT_DIR, "get_shopify_data_current.py")}"'
    api_success = run_command(command, "Shopify inventory data import (API method)")
    return api_success

def update_odoo_data():
    """Update Odoo data by running get_odoo_stock_current.py."""
    command = f'python "{os.path.join(SCRIPT_DIR, "get_odoo_stock_current.py")}"'
    return run_command(command, "Odoo data update")

def main():
    """
    Runs the full inventory synchronization process.
    1. Imports Shopify data from CSV.
    2. Fetches Odoo stock data.
    3. Generates cross-reference reports.
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info("=" * 80)
    logger.info(f"  {systemname.upper()} INVENTORY SYNC AND REPORTING SYSTEM")
    logger.info(f"  Started at: {timestamp}")
    logger.info("=" * 80)
    
    # --- Step 1: Update Shopify Data ---
    shopify_success = update_shopify_data()
    
    # --- Step 2: Update Odoo Data & Generate Reports ---
    # The Odoo script handles its own reporting.
    odoo_success = update_odoo_data()
    
    # --- Summary ---
    success = shopify_success and odoo_success
    
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info("=" * 80)
    logger.info("  INVENTORY SYNC AND REPORTING COMPLETED")
    logger.info(f"  Finished at: {timestamp}")
    logger.info(f"  Overall status: {'Success' if success else 'Failed'}")
    logger.info("=" * 80)
    
    # Return appropriate exit code
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())