#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
create_excel_report.py - Generate Excel report from order data

This script generates an Excel report from the order data stored in the SQLite database.
It creates intermediate tables for analysis and exports the final report to an Excel file.
The report is then uploaded to Odoo using the upload_to_odoo.py wrapper.
"""

import os
import sqlite3
import pandas as pd
import sys
from datetime import datetime
import sys
import os

# Add parent directory to path to import from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shopify_export_cred import db_name

# --- Path Configuration ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- Configuration ---
# Use parent directory (root) for database location
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
DB_FILE = os.path.join(ROOT_DIR, db_name)
EXCEL_OUTPUT = os.path.join(OUTPUT_DIR, 'order_flow.xlsx')
PACKAGE_NAME = 'OrderFlow'

def connect_to_db():
    """
    Connects to the SQLite database.
    
    Returns:
        Connection object if successful, None otherwise
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        print(f"Connected to database: {DB_FILE}")
        return conn
    except sqlite3.Error as e:
        print(f"Error connecting to database: {e}")
        return None

def execute_sql(conn, sql, description=None):
    """
    Executes a SQL statement.
    
    Args:
        conn: Database connection
        sql: SQL statement to execute
        description: Optional description of the SQL operation
        
    Returns:
        True if successful, False otherwise
    """
    if description:
        print(f"{description}...")
    
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        conn.commit()
        if description:
            print(f"{description} completed successfully.")
        return True
    except sqlite3.Error as e:
        print(f"SQL Error: {e}")
        print(f"Failed SQL: {sql}")
        return False

def create_shopify_orders_basesku(conn):
    """
    Creates the shopify_orders_basesku table.
    
    Args:
        conn: Database connection
        
    Returns:
        True if successful, False otherwise
    """
    # Drop table if it exists
    drop_sql = "DROP TABLE IF EXISTS shopify_orders_basesku"
    if not execute_sql(conn, drop_sql, "Dropping shopify_orders_basesku table if it exists"):
        return False
    
    # Create table
    create_sql = """
    CREATE TABLE shopify_orders_basesku AS 
    SELECT Name,
           A."Lineitem sku" AS SKU,
           Email,
           "Financial Status",
           "Fulfillment Status",
           "Paid at",
           "Lineitem quantity",
           "Lineitem name",
           "Lineitem price",
           "Billing Name",
           Tags,
           month_paid,
           year_paid,
           day_paid,
           plantname
      FROM shopify_orders A
    """
    
    return execute_sql(conn, create_sql, "Creating shopify_orders_basesku table")

def create_excel_report(conn):
    """
    Creates the excel_report table.
    
    Args:
        conn: Database connection
        
    Returns:
        True if successful, False otherwise
    """
    # Drop table if it exists
    drop_sql = "DROP TABLE IF EXISTS excel_report"
    if not execute_sql(conn, drop_sql, "Dropping excel_report table if it exists"):
        return False
    
    # Create table
    create_sql = """
    CREATE TABLE excel_report AS
    SELECT Name,
           A."Billing Name" AS Customer,
           SKU,
           A."Lineitem name" AS Item,
           A."Paid at" AS "Paid Date",
           "Lineitem quantity" AS Qty,
           "Financial Status" AS Payment,
           "Fulfillment Status" AS Shipment,
           B.Delivery_Status,
           Tags
      FROM shopify_orders_basesku A
      LEFT OUTER JOIN odoo_orders B
      ON A.Name = B.Odoo_Name
      AND A.SKU = B.Product_Default_Code
      ORDER BY Name DESC
    """
    
    return execute_sql(conn, create_sql, "Creating excel_report table")

def export_to_excel(conn):
    """
    Exports the excel_report table to an Excel file.
    
    Args:
        conn: Database connection
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Read the excel_report table into a pandas DataFrame
        query = "SELECT * FROM excel_report"
        df = pd.read_sql_query(query, conn)
        
        print(f"Retrieved {len(df)} rows from excel_report table.")
        
        # Export to Excel without any formatting
        df.to_excel(EXCEL_OUTPUT, index=False)

        print(f"Excel report exported to {EXCEL_OUTPUT}")

        # Automatically open the Excel file in the user's default application
        try:
            import platform
            if platform.system() == 'Windows':
                os.startfile(EXCEL_OUTPUT)
            elif platform.system() == 'Darwin':  # macOS
                import subprocess
                subprocess.run(['open', EXCEL_OUTPUT])
            else:  # Linux
                import subprocess
                subprocess.run(['xdg-open', EXCEL_OUTPUT])
            print(f"Opening Excel file: {EXCEL_OUTPUT}")
        except Exception as open_error:
            print(f"Note: Could not automatically open file (you can open it manually): {open_error}")

        return True

    except Exception as e:
        print(f"Error exporting to Excel: {e}")
        return False

# upload_to_odoo function removed - abandoned Odoo addon approach

def main():
    """
    Main function to run the report generation process.
    """
    print("Starting order flow report generation process...")
    
    # Connect to the database
    conn = connect_to_db()
    if not conn:
        print("Failed to connect to the database. Aborting.")
        sys.exit(1)
    
    try:
        # Create shopify_orders_basesku table
        if not create_shopify_orders_basesku(conn):
            print("Failed to create shopify_orders_basesku table. Aborting.")
            sys.exit(1)
        
        # Create excel_report table
        if not create_excel_report(conn):
            print("Failed to create excel_report table. Aborting.")
            sys.exit(1)
        
        # Export to Excel
        if not export_to_excel(conn):
            print("Failed to export to Excel. Aborting.")
            sys.exit(1)
        
        print(f"Order flow report generation completed successfully.")
        print(f"Excel report saved to: {EXCEL_OUTPUT}")
    
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        sys.exit(1)
    
    finally:
        # Close the database connection
        if conn:
            conn.close()
            print("Database connection closed.")

if __name__ == "__main__":
    main()
