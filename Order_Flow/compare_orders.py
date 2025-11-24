# compare_orders.py
import sqlite3
import pandas as pd
import argparse
import sys
from datetime import datetime
import sys
import os

# Add parent directory to path to import from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shopify_export_cred import db_name

# --- Configuration ---
# Get the root directory path and use it for the database file
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FILE = os.path.join(ROOT_DIR, db_name)  # Use full path to database in root directory
SHOPIFY_TABLE = 'shopify_orders'
ODOO_TABLE = 'odoo_orders'
COMPARISON_TABLE = 'order_comparison'

def connect_to_db():
    """
    Connects to the SQLite database.
    Returns a connection object if successful, None otherwise.
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        print(f"Successfully connected to database: {DB_FILE}")
        return conn
    except sqlite3.Error as e:
        print(f"Failed to connect to database: {e}")
        return None

def check_tables_exist(conn):
    """
    Checks if the required tables exist in the database.
    Returns True if both tables exist, False otherwise.
    """
    cursor = conn.cursor()
    
    # Check Shopify orders table
    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{SHOPIFY_TABLE}';")
    shopify_exists = cursor.fetchone() is not None
    
    # Check Odoo orders table
    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{ODOO_TABLE}';")
    odoo_exists = cursor.fetchone() is not None
    
    if not shopify_exists:
        print(f"Table '{SHOPIFY_TABLE}' does not exist. Please run update_shopify_orders.py first.")
    
    if not odoo_exists:
        print(f"Table '{ODOO_TABLE}' does not exist. Please run refresh_odoo_orders.py first.")
    
    return shopify_exists and odoo_exists

def load_shopify_orders(conn):
    """
    Loads Shopify orders from the database.
    Returns a DataFrame of Shopify orders.
    """
    try:
        query = f"""
        SELECT 
            "Name" as shopify_order_number,
            "Lineitem sku" as shopify_sku,
            "Lineitem name" as shopify_product_name,
            "Lineitem quantity" as shopify_quantity,
            "Lineitem price" as shopify_price,
            "Financial Status" as shopify_financial_status,
            "Fulfillment Status" as shopify_fulfillment_status,
            "Created at" as shopify_created_at,
            "Paid at" as shopify_paid_at,
            "Fulfilled at" as shopify_fulfilled_at,
            "Total" as shopify_total
        FROM {SHOPIFY_TABLE}
        """
        
        shopify_df = pd.read_sql_query(query, conn)
        print(f"Loaded {len(shopify_df)} Shopify order lines")
        return shopify_df
    
    except Exception as e:
        print(f"Error loading Shopify orders: {e}")
        return pd.DataFrame()

def load_odoo_orders(conn):
    """
    Loads Odoo orders from the database.
    Returns a DataFrame of Odoo orders.
    """
    try:
        query = f"""
        SELECT 
            "Shopify_Order_Number" as odoo_shopify_order_number,
            "Product_Default_Code" as odoo_sku,
            "Product_Name" as odoo_product_name,
            "Product_Quantity" as odoo_quantity,
            "Product_Unit_Price" as odoo_price,
            "Payment_Status" as odoo_payment_status,
            "Delivery_Status" as odoo_delivery_status,
            "Order_Date" as odoo_order_date,
            "Total_Amount" as odoo_total,
            "Odoo_Name" as odoo_order_name,
            "Odoo_ID" as odoo_order_id
        FROM {ODOO_TABLE}
        """
        
        odoo_df = pd.read_sql_query(query, conn)
        print(f"Loaded {len(odoo_df)} Odoo order lines")
        return odoo_df
    
    except Exception as e:
        print(f"Error loading Odoo orders: {e}")
        return pd.DataFrame()

def compare_orders(shopify_df, odoo_df):
    """
    Compares orders between Shopify and Odoo.
    Returns a DataFrame with the comparison results.
    """
    print("Comparing orders between Shopify and Odoo...")
    
    # Ensure data types are consistent
    shopify_df['shopify_quantity'] = pd.to_numeric(shopify_df['shopify_quantity'], errors='coerce')
    odoo_df['odoo_quantity'] = pd.to_numeric(odoo_df['odoo_quantity'], errors='coerce')
    shopify_df['shopify_price'] = pd.to_numeric(shopify_df['shopify_price'], errors='coerce')
    odoo_df['odoo_price'] = pd.to_numeric(odoo_df['odoo_price'], errors='coerce')
    
    # Prepare for merge
    # Convert column names to lowercase for case-insensitive join
    shopify_df['shopify_order_number_lower'] = shopify_df['shopify_order_number'].str.lower()
    shopify_df['shopify_sku_lower'] = shopify_df['shopify_sku'].str.lower()
    odoo_df['odoo_shopify_order_number_lower'] = odoo_df['odoo_shopify_order_number'].str.lower()
    odoo_df['odoo_sku_lower'] = odoo_df['odoo_sku'].str.lower()
    
    # Merge on order number and SKU
    merged_df = pd.merge(
        shopify_df,
        odoo_df,
        how='outer',
        left_on=['shopify_order_number_lower', 'shopify_sku_lower'],
        right_on=['odoo_shopify_order_number_lower', 'odoo_sku_lower']
    )
    
    # Add comparison columns
    merged_df['in_shopify'] = ~merged_df['shopify_order_number'].isna()
    merged_df['in_odoo'] = ~merged_df['odoo_shopify_order_number'].isna()
    
    # Compare quantities
    merged_df['quantity_match'] = (
        (merged_df['shopify_quantity'] == merged_df['odoo_quantity']) | 
        (merged_df['shopify_quantity'].isna() & merged_df['odoo_quantity'].isna())
    )
    
    # Compare prices (with small tolerance for floating point differences)
    merged_df['price_match'] = (
        (abs(merged_df['shopify_price'] - merged_df['odoo_price']) < 0.01) | 
        (merged_df['shopify_price'].isna() & merged_df['odoo_price'].isna())
    )
    
    # Determine sync status
    def get_sync_status(row):
        if not row['in_shopify']:
            return "Missing in Shopify"
        elif not row['in_odoo']:
            return "Missing in Odoo"
        elif not row['quantity_match']:
            return "Quantity mismatch"
        elif not row['price_match']:
            return "Price mismatch"
        else:
            return "Synced"
    
    merged_df['sync_status'] = merged_df.apply(get_sync_status, axis=1)
    
    # Add timestamp
    merged_df['comparison_date'] = datetime.now().isoformat()
    
    print(f"Comparison complete. Found {len(merged_df)} total order lines.")
    print(f"Synced: {len(merged_df[merged_df['sync_status'] == 'Synced'])}")
    print(f"Missing in Shopify: {len(merged_df[merged_df['sync_status'] == 'Missing in Shopify'])}")
    print(f"Missing in Odoo: {len(merged_df[merged_df['sync_status'] == 'Missing in Odoo'])}")
    print(f"Quantity mismatch: {len(merged_df[merged_df['sync_status'] == 'Quantity mismatch'])}")
    print(f"Price mismatch: {len(merged_df[merged_df['sync_status'] == 'Price mismatch'])}")
    
    return merged_df

def save_comparison_results(conn, comparison_df):
    """
    Saves the comparison results to the database.
    """
    try:
        # Drop temporary columns used for joining
        columns_to_drop = [
            'shopify_order_number_lower', 'shopify_sku_lower',
            'odoo_shopify_order_number_lower', 'odoo_sku_lower'
        ]
        comparison_df = comparison_df.drop(columns=columns_to_drop, errors='ignore')
        
        # Save to database
        comparison_df.to_sql(COMPARISON_TABLE, conn, if_exists='replace', index=False)
        print(f"Comparison results saved to table '{COMPARISON_TABLE}'")
        
        return True
    
    except Exception as e:
        print(f"Error saving comparison results: {e}")
        return False

def export_to_csv(comparison_df, output_file):
    """
    Exports the comparison results to a CSV file.
    """
    try:
        # Drop temporary columns used for joining
        columns_to_drop = [
            'shopify_order_number_lower', 'shopify_sku_lower',
            'odoo_shopify_order_number_lower', 'odoo_sku_lower'
        ]
        comparison_df = comparison_df.drop(columns=columns_to_drop, errors='ignore')
        
        # Export to CSV
        comparison_df.to_csv(output_file, index=False)
        print(f"Comparison results exported to {output_file}")
        
        return True
    
    except Exception as e:
        print(f"Error exporting to CSV: {e}")
        return False

def generate_sync_report(comparison_df):
    """
    Generates a report of orders that need to be synced.
    """
    # Orders missing in Odoo (need to be imported from Shopify to Odoo)
    missing_in_odoo = comparison_df[comparison_df['sync_status'] == 'Missing in Odoo']
    
    # Orders with mismatches (need to be updated in Odoo)
    mismatches = comparison_df[
        (comparison_df['sync_status'] == 'Quantity mismatch') | 
        (comparison_df['sync_status'] == 'Price mismatch')
    ]
    
    print("\n=== SYNC REPORT ===")
    print(f"Total orders to import to Odoo: {len(missing_in_odoo)}")
    print(f"Total orders to update in Odoo: {len(mismatches)}")
    
    if len(missing_in_odoo) > 0:
        print("\nTop 5 orders to import to Odoo:")
        for _, row in missing_in_odoo.head(5).iterrows():
            print(f"  - Order {row['shopify_order_number']}: {row['shopify_product_name']} (SKU: {row['shopify_sku']}, Qty: {row['shopify_quantity']})")
    
    if len(mismatches) > 0:
        print("\nTop 5 orders to update in Odoo:")
        for _, row in mismatches.head(5).iterrows():
            print(f"  - Order {row['shopify_order_number']}: {row['shopify_product_name']} (SKU: {row['shopify_sku']}) - {row['sync_status']}")
            if row['sync_status'] == 'Quantity mismatch':
                print(f"    Shopify Qty: {row['shopify_quantity']}, Odoo Qty: {row['odoo_quantity']}")
            elif row['sync_status'] == 'Price mismatch':
                print(f"    Shopify Price: {row['shopify_price']}, Odoo Price: {row['odoo_price']}")
    
    print("\nRun this script with --export option to generate a CSV file for detailed analysis.")

if __name__ == "__main__":
    # --- Argument Parsing ---
    parser = argparse.ArgumentParser(description='Compare orders between Shopify and Odoo.')
    parser.add_argument('--export', action='store_true',
                        help='Export comparison results to a CSV file')
    parser.add_argument('--output', type=str, default='order_comparison.csv',
                        help='Output CSV file name (default: order_comparison.csv)')
    args = parser.parse_args()
    
    # --- Connect to Database ---
    conn = connect_to_db()
    if not conn:
        sys.exit(1)
    
    # --- Check Tables ---
    if not check_tables_exist(conn):
        conn.close()
        sys.exit(1)
    
    # --- Load Orders ---
    shopify_df = load_shopify_orders(conn)
    odoo_df = load_odoo_orders(conn)
    
    if shopify_df.empty or odoo_df.empty:
        print("Failed to load order data. Aborting.")
        conn.close()
        sys.exit(1)
    
    # --- Compare Orders ---
    comparison_df = compare_orders(shopify_df, odoo_df)
    
    # --- Save Comparison Results ---
    save_comparison_results(conn, comparison_df)
    
    # --- Generate Sync Report ---
    generate_sync_report(comparison_df)
    
    # --- Export to CSV if requested ---
    if args.export:
        export_to_csv(comparison_df, args.output)
    
    # --- Close Connection ---
    conn.close()
    print("Database connection closed.")
    print("Comparison process completed.")