#!/usr/bin/env python3
"""
Create materials.db for the Materials Management System

This script creates a new materials.db file in the root directory, copied from
either the Order_Flow database (order_sync.db) or the Shopify_Odoo_Stock_Cross_Ref
database (woodlanders.db) depending on which one exists.

If neither database exists, it creates an empty SQLite database.

This script also ensures the legacy_lookup table is created in the database,
populated from the legacy_lookup.xlsx file in the Order_Flow directory.
"""

import os
import sqlite3
import shutil
import sys
import pandas as pd

def ensure_legacy_lookup_table(db_path, excel_path):
    """Ensure the legacy_lookup table exists in the database from the Excel file.
    
    This function checks if the table exists and creates it if it doesn't,
    regardless of whether the database was just created or already existed.
    """
    if not os.path.exists(excel_path):
        print(f"Warning: legacy_lookup.xlsx not found at {excel_path}")
        return False
    
    try:
        # Read the Excel file
        print(f"Reading legacy_lookup data from {excel_path}")
        df = pd.read_excel(excel_path)
        
        # Connect to the database
        conn = sqlite3.connect(db_path)
        
        # Check if the table already exists
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='legacy_lookup'")
        if cursor.fetchone():
            print("legacy_lookup table already exists, skipping creation")
            conn.close()
            return True
        
        # Create the table and populate it with the data from the Excel file
        print("Creating legacy_lookup table in the database")
        df.to_sql('legacy_lookup', conn, if_exists='replace', index=False)
        conn.commit()
        conn.close()
        print("Successfully created legacy_lookup table")
        return True
    except Exception as e:
        print(f"Error creating legacy_lookup table: {e}")
        return False

def main():
    """Create the materials.db file in the root directory if it doesn't exist
    and ensure the legacy_lookup table is present."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    order_flow_db = os.path.join(script_dir, 'Order_Flow', 'order_sync.db')
    stock_xref_db = os.path.join(script_dir, 'Shopify_Odoo_Stock_Cross_Ref', 'woodlanders.db')
    materials_db = os.path.join(script_dir, 'materials.db')
    legacy_lookup_excel = os.path.join(script_dir, 'Order_Flow', 'legacy_lookup.xlsx')
    
    # If materials.db already exists, just check for the legacy_lookup table
    if os.path.exists(materials_db):
        print(f"materials.db already exists at {materials_db}")
        ensure_legacy_lookup_table(materials_db, legacy_lookup_excel)
        return
    
    # Try to copy from Order_Flow database first
    if os.path.exists(order_flow_db):
        print(f"Copying database from {order_flow_db} to {materials_db}")
        shutil.copy2(order_flow_db, materials_db)
        print("Successfully created materials.db from Order_Flow database")
        
        # Ensure legacy_lookup table exists
        ensure_legacy_lookup_table(materials_db, legacy_lookup_excel)
        return
    
    # If that fails, try to copy from Shopify_Odoo_Stock_Cross_Ref database
    if os.path.exists(stock_xref_db):
        print(f"Copying database from {stock_xref_db} to {materials_db}")
        shutil.copy2(stock_xref_db, materials_db)
        print("Successfully created materials.db from Shopify_Odoo_Stock_Cross_Ref database")
        
        # Ensure legacy_lookup table exists
        ensure_legacy_lookup_table(materials_db, legacy_lookup_excel)
        return
    
    # If neither database exists, create an empty SQLite database
    print(f"Creating new empty database at {materials_db}")
    conn = sqlite3.connect(materials_db)
    conn.close()
    print("Successfully created empty materials.db")
    
    # Ensure legacy_lookup table exists
    ensure_legacy_lookup_table(materials_db, legacy_lookup_excel)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error creating materials.db: {e}")
        sys.exit(1)