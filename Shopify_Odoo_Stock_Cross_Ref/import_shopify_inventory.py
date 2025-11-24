import pandas as pd
import sqlite3
import datetime
import os

# --- Path Setup ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
SHARED_DATA_DIR = os.path.join(PROJECT_ROOT, 'shared-data')
SQLITE_DIR = os.path.join(SHARED_DATA_DIR, 'sqlite')
INPUT_DIR = os.path.join(SHARED_DATA_DIR, 'input')
DB_PATH = os.path.join(SQLITE_DIR, 'analytics.db')

# Get the output directory from the environment variable set by the runner.
OUTPUT_DIR = os.environ.get('OUTPUT_DIR')
if not OUTPUT_DIR:
    print("Warning: OUTPUT_DIR environment variable not set. Defaulting to 'shared-data/output/default'.")
    OUTPUT_DIR = os.path.join(SHARED_DATA_DIR, 'output', 'default')

# Create directories if they don't exist
os.makedirs(SQLITE_DIR, exist_ok=True)
os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

def import_shopify_inventory(csv_file):
    """
    Import Shopify inventory data from CSV file into SQLite database.
    Filter out entries where inventory values are "not stocked".
    """
    print(f"Importing Shopify inventory data from {csv_file}...")
    
    # Read the CSV file
    df = pd.read_csv(csv_file, encoding='utf-8')
    print(f"Read {len(df)} rows from CSV file")
    
    # Filter out "not stocked" entries
    stocked_df = df[~(df['Available'].astype(str) == 'not stocked')]
    print(f"Filtered to {len(stocked_df)} rows with stocked items")
    
    # Group by SKU and aggregate inventory values
    # For each SKU, we'll sum the inventory values across all locations
    inventory_by_sku = stocked_df.groupby('SKU').agg({
        'Incoming': lambda x: sum(pd.to_numeric(x, errors='coerce').fillna(0)),
        'Unavailable': lambda x: sum(pd.to_numeric(x, errors='coerce').fillna(0)),
        'Committed': lambda x: sum(pd.to_numeric(x, errors='coerce').fillna(0)),
        'Available': lambda x: sum(pd.to_numeric(x, errors='coerce').fillna(0)),
        'On hand': lambda x: sum(pd.to_numeric(x, errors='coerce').fillna(0)),
        'Title': 'first',  # Keep the first title
        'Handle': 'first',  # Keep the first handle
        'Option1 Value': 'first'  # Keep the first option value (will be renamed to option_value)
    }).reset_index()
    
    print(f"Aggregated to {len(inventory_by_sku)} unique SKUs")
    
    # Connect to the database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create shopify_inventory table if it doesn't exist
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS shopify_inventory (
        sku TEXT PRIMARY KEY,
        title TEXT,
        handle TEXT,
        option_value TEXT,
        incoming REAL,
        unavailable REAL,
        committed REAL,
        available REAL,
        on_hand REAL,
        import_date TEXT
    )
    """)
    
    # Add import date
    inventory_by_sku['import_date'] = datetime.datetime.now().isoformat()
    
    # Rename Option1 Value to option_value to match the table schema
    inventory_by_sku = inventory_by_sku.rename(columns={'Option1 Value': 'option_value'})
    
    # Rename On hand to on_hand to match the table schema
    inventory_by_sku = inventory_by_sku.rename(columns={'On hand': 'on_hand'})
    
    # Insert or replace data in the table
    inventory_by_sku.to_sql('shopify_inventory', conn, if_exists='replace', index=False)
    
    # Print column names for debugging
    cursor.execute("PRAGMA table_info(shopify_inventory)")
    columns = cursor.fetchall()
    print(f"Columns in shopify_inventory table: {[c[1] for c in columns]}")
    
    print(f"Imported {len(inventory_by_sku)} SKUs into shopify_inventory table")
    
    # Check if odoostock table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='odoostock'")
    odoostock_exists = cursor.fetchone() is not None
    
    if not odoostock_exists:
        print("Warning: odoostock table not found. Run get_odoo_stock_current.py first.")
        print("Skipping stock cross-reference creation.")
        return None
    
    # Create a new stock cross-reference view that includes all inventory values
    cursor.execute("DROP VIEW IF EXISTS stock_cross_reference_extended")
    
    cursor.execute("""
    CREATE VIEW stock_cross_reference_extended AS
    SELECT
        o.product_id,
        o.location_id,
        o.default_code AS odoo_sku,
        o.quantity AS odoo_quantity,
        si.sku AS shopify_sku,
        si.title AS shopify_title,
        si.option_value AS shopify_option,
        si.on_hand AS shopify_on_hand,
        si.available AS shopify_available,
        si.committed AS shopify_committed,
        si.unavailable AS shopify_unavailable,
        si.incoming AS shopify_incoming,
        CASE
            WHEN si.on_hand IS NOT NULL THEN o.quantity - si.on_hand
            ELSE o.quantity
        END AS quantity_diff
    FROM 
        odoostock o
    LEFT JOIN 
        shopify_inventory si ON o.default_code = si.sku
    WHERE 
        o.quantity > 0 OR si.on_hand > 0
    ORDER BY 
        CASE 
            WHEN si.on_hand IS NOT NULL THEN ABS(o.quantity - si.on_hand) 
            ELSE o.quantity 
        END DESC
    """)
    
    # Export the view to Excel if it was created
    if odoostock_exists:
        excel_file = os.path.join(OUTPUT_DIR, 'stock_cross_reference_extended.xlsx')
        
        try:
            df_cross_ref = pd.read_sql("SELECT * FROM stock_cross_reference_extended", conn)
            
            # Check if file exists and is not open
            if os.path.exists(excel_file):
                try:
                    # Try to open and close the file to check if it's accessible
                    with open(excel_file, 'a', encoding='utf-8'):
                        pass
                    # If we get here, file is accessible, so we can overwrite it
                    df_cross_ref.to_excel(excel_file, index=False)
                    print(f"Exported {len(df_cross_ref)} rows to {excel_file}")
                except (IOError, PermissionError):
                    print(f"Warning: Could not update {excel_file} - file may be open in another program")
                    excel_file = None
            else:
                # File doesn't exist, so we can create it
                df_cross_ref.to_excel(excel_file, index=False)
                print(f"Exported {len(df_cross_ref)} rows to {excel_file}")
        except Exception as e:
            print(f"Error creating stock cross-reference report: {e}")
            excel_file = None
    else:
        excel_file = None
    
    # Create a mismatch report for items with significant differences
    if odoostock_exists:
        try:
            cursor.execute("""
            SELECT * FROM stock_cross_reference_extended
            WHERE shopify_sku IS NOT NULL
              AND odoo_quantity > 0
              AND shopify_on_hand != odoo_quantity
              AND ABS(shopify_on_hand - odoo_quantity) > 5
            ORDER BY ABS(shopify_on_hand - odoo_quantity) DESC
            """)
            
            mismatches = cursor.fetchall()
            if mismatches:
                print(f"\nFound {len(mismatches)} significant inventory mismatches:")
                for i, mismatch in enumerate(mismatches[:5]):
                    print(f"{i+1}. {mismatch[2]} (Odoo: {mismatch[3]}, Shopify: {mismatch[11]})")
        except Exception as e:
            print(f"Error creating mismatch report: {e}")
    
    # Look for SKU prefix mismatches (same product, different size)
    if odoostock_exists:
        try:
            cursor.execute("""
    SELECT 
        o1.default_code AS odoo_sku1,
        o1.quantity AS odoo_qty1,
        o1.size_suffix AS odoo_size1,
        o2.default_code AS odoo_sku2,
        o2.quantity AS odoo_qty2,
        o2.size_suffix AS odoo_size2,
        si1.sku AS shopify_sku1,
        si1.on_hand AS shopify_qty1,
        si1.option_value AS shopify_size1,
        si2.sku AS shopify_sku2,
        si2.on_hand AS shopify_qty2,
        si2.option_value AS shopify_size2,
        si1.title
    FROM 
        odoostock o1
    JOIN 
        odoostock o2 ON o1.plant_prefix = o2.plant_prefix AND o1.size_suffix != o2.size_suffix
    JOIN 
        shopify_inventory si1 ON o1.default_code = si1.sku
    JOIN 
        shopify_inventory si2 ON o2.default_code = si2.sku
    WHERE 
        o1.quantity > 0 AND o2.quantity = 0
        AND si1.on_hand = 0 AND si2.on_hand > 0
    """)
    
            sku_mismatches = cursor.fetchall()
            if sku_mismatches:
                mismatch_df = pd.DataFrame(sku_mismatches, columns=[
                    'odoo_sku1', 'odoo_qty1', 'odoo_size1',
                    'odoo_sku2', 'odoo_qty2', 'odoo_size2',
                    'shopify_sku1', 'shopify_qty1', 'shopify_size1',
                    'shopify_sku2', 'shopify_qty2', 'shopify_size2',
                    'title'
                ])
                
                mismatch_file = os.path.join(OUTPUT_DIR, 'sku_mismatches.xlsx')
                
                # Check if file exists and is not open
                if os.path.exists(mismatch_file):
                    try:
                        # Try to open and close the file to check if it's accessible
                        with open(mismatch_file, 'a', encoding='utf-8'):
                            pass
                        # If we get here, file is accessible, so we can overwrite it
                        mismatch_df.to_excel(mismatch_file, index=False)
                    except (IOError, PermissionError):
                        print(f"Warning: Could not update {mismatch_file} - file may be open in another program")
                else:
                    # File doesn't exist, so we can create it
                    mismatch_df.to_excel(mismatch_file, index=False)
                
                print(f"\nFound {len(sku_mismatches)} potential SKU mismatches (exported to {mismatch_file}):")
                for i, mismatch in enumerate(sku_mismatches[:5]):
                    print(f"{i+1}. {mismatch[12]}")
                    print(f"   Odoo shows inventory for {mismatch[0]} ({mismatch[1]} units) but Shopify shows 0")
                    print(f"   Shopify shows inventory for {mismatch[9]} ({mismatch[10]} units) but Odoo shows 0")
        except Exception as e:
            print(f"Error looking for SKU mismatches: {e}")
    
    conn.close()
    return excel_file

def main():
    """Main function to find the latest Shopify export and import it."""
    """Main function to find the latest Shopify export and import it."""
    # Find the most recent inventory export file in the input directory
    try:
        inventory_files = [f for f in os.listdir(INPUT_DIR) if f.startswith('inventory_export') and f.endswith('.csv')]
    except FileNotFoundError:
        inventory_files = []

    if not inventory_files:
        print("Warning: No inventory export files found in the input directory (e.g., 'inventory_export_*.csv').")
        print("Please place Shopify export files in 'shared-data/input/'.")
        print("Skipping Shopify data import.")
        return

    # Sort by modification time (newest first)
    inventory_files.sort(key=lambda f: os.path.getmtime(os.path.join(INPUT_DIR, f)), reverse=True)
    latest_file_name = inventory_files[0]
    latest_file_path = os.path.join(INPUT_DIR, latest_file_name)
    
    print(f"Using most recent inventory file: {latest_file_path}")
    excel_file = import_shopify_inventory(latest_file_path)
    
    print(f"\nInventory import complete. Stock cross-reference report saved to {excel_file}")

if __name__ == "__main__":
    main()