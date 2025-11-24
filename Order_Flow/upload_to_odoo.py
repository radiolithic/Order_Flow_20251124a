#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
upload_to_odoo.py - Wrapper script for uploading files to Odoo via API

This script provides functions to upload files to Odoo's report_manager module.
It handles reading the file, encoding it in base64, and calling the appropriate
Odoo API method to create a report file record.

Usage:
    from upload_to_odoo import upload_report
    
    # Generate your report
    report_path = os.path.join(OUTPUT_DIR, 'my_report.xlsx')
    df.to_excel(report_path, index=False)
    
    # Upload the report to Odoo
    upload_report('OrderFlow', report_path)
"""

import os
import sys
import base64
import xmlrpc.client
from datetime import datetime
import sys
import os

# Add parent directory to path to import from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from odoosys import url, db, username, password

# Constants
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

def connect_to_odoo():
    """
    Establishes connection to the Odoo server using XML-RPC.
    
    Returns:
        tuple: (models_proxy, uid) if successful, (None, None) otherwise
    """
    try:
        # Connect to Odoo server
        common_proxy = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        
        # Authenticate and get user ID
        uid = common_proxy.authenticate(db, username, password, {})
        
        if not uid:
            print("Authentication failed. Check credentials.")
            return None, None
        
        # Get models proxy for data operations
        models_proxy = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        
        print(f"Successfully connected to Odoo server at {url}")
        return models_proxy, uid
    
    except Exception as e:
        print(f"Failed to connect to Odoo server: {e}")
        return None, None

def read_file_content(file_path):
    """
    Reads a file and returns its content as bytes.
    
    Args:
        file_path (str): Path to the file to read
        
    Returns:
        bytes: File content as bytes if successful, None otherwise
    """
    try:
        with open(file_path, 'rb') as file:
            content = file.read()
        return content
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return None

def upload_report(package_name, file_path, description=None):
    """
    Uploads a report file to Odoo.
    
    Args:
        package_name (str): Name of the package/module that generated the report
        file_path (str): Path to the file to upload
        description (str, optional): Description of the report
        
    Returns:
        bool: True if successful, False otherwise
    """
    # Connect to Odoo
    models, uid = connect_to_odoo()
    if not models or not uid:
        return False
    
    try:
        # Read file content
        file_content = read_file_content(file_path)
        if not file_content:
            return False
        
        # Get file name
        file_name = os.path.basename(file_path)
        
        # Encode file content in base64
        encoded_content = base64.b64encode(file_content).decode('utf-8')
        
        print(f"Calling 'create_from_analytics' for package '{package_name}', file '{file_name}'...")
        
        # Call Odoo API to create report file - IMPORTANT: Pass the three arguments separately
        result = models.execute_kw(
            db, uid, password,
            'report.file', 'create_from_analytics',
            [package_name, file_name, encoded_content]  # Pass three separate arguments
        )
        
        print(f"Odoo API response: {result}")
        
        if result.get('status') == 'success':
            print(f"Successfully uploaded report {file_name} to Odoo")
            return True
        else:
            print(f"Failed to upload report {file_name} to Odoo: {result.get('message')}")
            return False
    
    except Exception as e:
        print(f"Error uploading report to Odoo: {e}")
        return False

if __name__ == "__main__":
    # This script is intended to be imported, but can be run directly for testing
    if len(sys.argv) < 3:
        print("Usage: python upload_to_odoo.py <package_name> <file_path> [description]")
        sys.exit(1)
    
    package_name = sys.argv[1]
    file_path = sys.argv[2]
    description = sys.argv[3] if len(sys.argv) > 3 else None
    
    success = upload_report(package_name, file_path, description)
    sys.exit(0 if success else 1)