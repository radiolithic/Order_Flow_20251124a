import pandas as pd
import xmlrpc.client
import re
import ssl
import sqlite3
import os

def Clean_fields(fieldvalue):
    # Handle different data types
    if fieldvalue is None:
        return ""
    
    # Convert to string first
    fieldvalue = str(fieldvalue)
    
    # Handle Odoo's [ID, "Name"] format - extract the name part
    if fieldvalue.startswith('[') and ',' in fieldvalue:
        try:
            # Split on comma and take the second part, then clean it
            parts = fieldvalue.split(',', 1)
            if len(parts) > 1:
                name_part = parts[1].strip()
                # Remove quotes and closing bracket
                name_part = name_part.strip('\'"')
                name_part = name_part.rstrip(']')
                name_part = name_part.strip('\'"')
                return name_part
        except:
            pass
    
    # Handle simple [ID] format  
    if fieldvalue.startswith('[') and fieldvalue.endswith(']') and ',' not in fieldvalue:
        return fieldvalue.strip('[]')
    
    return fieldvalue

# Import credentials
try:
    from odoosys import url, db, username, password
except ImportError:
    print("ERROR: odoosys.py not found!")
    print("Please create odoosys.py with your Odoo credentials:")
    print("  url = 'https://your-instance.odoo.com'")
    print("  db = 'your_database_name'")
    print("  username = 'your_username'")
    print("  password = 'your_password'")
    exit(1)

common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(url), use_datetime=True,context=ssl._create_unverified_context())
uid = common.authenticate(db, username, password, {})
models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(url), use_datetime=True,context=ssl._create_unverified_context())

print("Fetching stock levels from Odoo (Plants only)...")
# Search for stock where location starts with F% AND product category is 'Plant'
polling = models.execute_kw(db, uid, password, 'stock.quant', 'search', [
    [
        ['location_id', 'like', 'F%'],
        ['product_categ_id', '=', 'Plant']
    ]
])
stock=models.execute_kw(db, uid, password, 'stock.quant', 'read', [polling], {'fields': ['product_id', 'location_id', 'quantity']})
df_stock = pd.DataFrame(stock)

# Debug: Check data types before cleaning
print("Raw data sample:")
print(df_stock.head())
print("Data types:", df_stock.dtypes)

# Clean the fields
df_stock['product_id'] = df_stock['product_id'].apply(Clean_fields)
df_stock['location_id'] = df_stock['location_id'].apply(Clean_fields)

# Debug: Check data after cleaning
print("Cleaned data sample:")
print(df_stock.head())
print("Data types after cleaning:", df_stock.dtypes)

# Ensure all columns are proper types for SQLite
df_stock['product_id'] = df_stock['product_id'].astype(str)
df_stock['location_id'] = df_stock['location_id'].astype(str)
df_stock['quantity'] = pd.to_numeric(df_stock['quantity'], errors='coerce').fillna(0)

df_stock.to_csv('stock_levels.csv', index = False, header = True)
print(f"Retrieved {len(df_stock)} stock records")

# Create SQLite database (use persistent file for debugging)
db_file = 'pullsheet_debug.db'  # Use persistent file instead of :memory: for debugging
dbconn = sqlite3.connect(db_file)
cursor = dbconn.cursor()
print(f"Using persistent database: {db_file}")

# Load stock levels into SQLite
df_stock.to_sql('stock_levels', con=dbconn, if_exists='replace')
print("Stock levels loaded into SQLite")

# Read and process the transfer file (Excel or CSV)
print("Looking for transfer file...")

# Check for Excel file first, then CSV
if os.path.exists('Transfer (stock.picking).xlsx'):
    file_path = 'Transfer (stock.picking).xlsx'
    file_type = 'Excel'
elif os.path.exists('Transfer (stock.picking).csv'):
    file_path = 'Transfer (stock.picking).csv'
    file_type = 'CSV'
else:
    print("ERROR: Transfer file not found!")
    print("Looking for: 'Transfer (stock.picking).xlsx' or 'Transfer (stock.picking).csv'")
    exit(1)

print(f"Reading {file_path} ({file_type})...")
try:
    if file_type == 'Excel':
        pull01 = pd.read_excel(file_path)
    else:
        pull01 = pd.read_csv(file_path)

    print(f"Read {len(pull01)} rows from {file_type} file")
    print("Original columns:", pull01.columns.tolist())
    
    # Column mapping for both Odoo v15/v16 and v17
    # v17 changes:
    #   - "Stock Moves/Quantity" → "Stock Moves/Move Line/Quantity"
    #   - "Stock Moves/Product/Quantity On Hand" → "Stock Moves/Product On Hand Quantity"
    dict_rename = {
        'Stock Moves': 'Order',
        'Stock Moves/Product': 'Item',
        'Stock Moves/Move Line/From': 'Location',
        # Try v17 column name first, fallback to older versions
        'Stock Moves/Move Line/Quantity': 'Quantity',  # v17
        'Stock Moves/Quantity': 'Quantity',  # v15/v16 (fallback)
        # Try v17 column name first, fallback to older versions
        'Stock Moves/Product On Hand Quantity': 'OnHand',  # v17
        'Stock Moves/Product/Quantity On Hand': 'OnHand'  # v15/v16 (fallback)
    }
    
    # Check which columns actually exist before renaming
    print("Checking column mapping:")
    for old_name, new_name in dict_rename.items():
        if old_name in pull01.columns:
            print(f"  ✓ Found '{old_name}' -> will rename to '{new_name}'")
        else:
            print(f"  ✗ Missing '{old_name}' - available columns: {pull01.columns.tolist()}")
    
    pull01.rename(columns=dict_rename, inplace=True)
    print("Renamed columns:", pull01.columns.tolist())
    
    # Verify we have the required columns
    required_cols = ['Order', 'Item', 'Location', 'Quantity', 'OnHand']
    missing_cols = [col for col in required_cols if col not in pull01.columns]
    if missing_cols:
        print(f"ERROR: Missing required columns after rename: {missing_cols}")
        print("Available columns:", pull01.columns.tolist())
        exit(1)
    
    # Load into SQLite
    pull01.to_sql('stock_picking', con=dbconn, if_exists='replace')
    print("Stock picking data loaded into SQLite")
    
    # Debug: Show what we loaded and check for order truncation
    print("Sample data loaded into SQLite:")
    sample_query = cursor.execute("SELECT * FROM stock_picking LIMIT 3")
    for row in sample_query:
        print(row)
    
    # Debug: Check what Order values we actually have
    print("\nUnique Order values in the data:")
    order_query = cursor.execute("SELECT DISTINCT \"Order\" FROM stock_picking")
    for row in order_query:
        print(f"  Order: '{row[0]}'")
    
    # Test the order extraction logic
    print("\nTesting order extraction:")
    test_query = cursor.execute("""
        SELECT "Order" as original_order,
               CASE 
                   WHEN "Order" LIKE '%/%' THEN SUBSTR("Order", 1, INSTR("Order", '/') - 1)
                   ELSE "Order"
               END AS extracted_order
        FROM stock_picking LIMIT 5
    """)
    for row in test_query:
        print(f"  Original: '{row[0]}' -> Extracted: '{row[1]}'")
    print()
    
except FileNotFoundError:
    print(f"ERROR: '{file_path}' file not found!")
    exit(1)
except Exception as e:
    print(f"ERROR reading {file_type} file: {e}")
    exit(1)

# SQL queries (fixed to extract just the order number from the full string)
qrys=[
    '''CREATE TABLE pullsheet AS SELECT
           CASE
               WHEN "Order" LIKE '%/%' THEN SUBSTR("Order", 1, INSTR("Order", '/') - 1)
               ELSE "Order"
           END AS ORD,
           Item,
           Location,
           Quantity AS QTY,
           OnHand
      FROM stock_picking
      WHERE Quantity > 0
      ORDER BY Location, Item, ORD;
    ''',
    '''CREATE TABLE order_items AS SELECT DISTINCT "index",
           CASE 
               WHEN "Order" LIKE '%/%' THEN SUBSTR("Order", 1, INSTR("Order", '/') - 1)
               ELSE "Order"
           END AS ORD,
           Item
    FROM stock_picking
    WHERE Quantity > 0;
    ''',
    '''CREATE TABLE skus_per_order AS SELECT ORD,
           COUNT(*) AS SKUS
      FROM order_items
      GROUP BY ORD;
    ''',
    '''CREATE TABLE plants_per_order AS SELECT 
           CASE 
               WHEN "Order" LIKE '%/%' THEN SUBSTR("Order", 1, INSTR("Order", '/') - 1)
               ELSE "Order"
           END AS ORD,
        SUM(Quantity) as PLANTS
    FROM stock_picking
    WHERE Quantity > 0
    GROUP BY ORD;
    ''',
    '''CREATE TABLE skus_plants_by_order AS SELECT skus_per_order.ORD,
           SKUS,
           PLANTS
      FROM skus_per_order
      JOIN plants_per_order
      ON skus_per_order.ORD = plants_per_order.ORD
      GROUP BY skus_per_order.ORD
      ORDER BY skus_per_order.ORD;
    ''',
    '''CREATE TABLE alt_stock AS SELECT DISTINCT product_id,
           location_id,
           stock_levels.quantity
      FROM stock_levels
      JOIN stock_picking
      WHERE stock_levels.product_id = stock_picking.Item
      AND stock_levels.location_id <> stock_picking.Location
      ORDER BY product_id, location_id;
    '''
]

print("Executing SQL queries...")

# First, drop any existing tables to ensure we get fresh data
drop_tables = [
    'DROP TABLE IF EXISTS pullsheet',
    'DROP TABLE IF EXISTS order_items', 
    'DROP TABLE IF EXISTS skus_per_order',
    'DROP TABLE IF EXISTS plants_per_order',
    'DROP TABLE IF EXISTS skus_plants_by_order',
    'DROP TABLE IF EXISTS alt_stock'
]

print("Dropping existing tables...")
for drop_sql in drop_tables:
    cursor.execute(drop_sql)

for i, qry in enumerate(qrys):
    try:
        cursor.execute(qry)
        print(f"Query {i+1} executed successfully")
    except Exception as e:
        print(f"Error in query {i+1}: {e}")
        print(f"Query was: {qry}")
        # Continue with other queries

# Extract results
print("Extracting results...")
try:
    # Debug: Let's see what the SQL actually created
    debug_query = cursor.execute("SELECT ORD, Item, Location FROM pullsheet LIMIT 5")
    print("Sample from pullsheet table:")
    for row in debug_query:
        print(f"  ORD: '{row[0]}', Item: '{row[1]}', Location: '{row[2]}'")
    
    df_pullsheet = pd.read_sql_query("SELECT * FROM pullsheet", dbconn)
    print(f"Pullsheet has {len(df_pullsheet)} rows")
except Exception as e:
    print(f"Error reading pullsheet: {e}")
    df_pullsheet = pd.DataFrame()

try:
    df_items = pd.read_sql_query("SELECT * FROM skus_plants_by_order", dbconn)
    print(f"Order targets has {len(df_items)} rows")
except Exception as e:
    print(f"Error reading order targets: {e}")
    df_items = pd.DataFrame()

try:
    df_alt_stock = pd.read_sql_query("SELECT * FROM alt_stock", dbconn)
    print(f"Alt inventory has {len(df_alt_stock)} rows")
except Exception as e:
    print(f"Error reading alt stock: {e}")
    df_alt_stock = pd.DataFrame()

# Clean up the data (fix regex patterns but preserve full order numbers)
if not df_pullsheet.empty:
    # Clean up Item names - remove Odoo format brackets
    df_pullsheet['Item'] = df_pullsheet['Item'].astype(str).str.replace(r'\[.*?\]', r'', regex=True).str.strip()
    
    # Clean up Location - remove F/Stock/ prefix but keep the location code
    df_pullsheet['Location'] = df_pullsheet['Location'].astype(str).str.replace(r'F/Stock/', r'', regex=True)
    
    # DON'T truncate ORD - keep full order numbers
    # The original script had: df_pullsheet['ORD'] = df_pullsheet['ORD'].str.replace(r'\/', r'', regex=True)
    # But this might be truncating. Let's preserve the full ORD values.
    
    print("Sample of cleaned data:")
    print(df_pullsheet.head())

# Export results
print("Exporting results...")
if not df_pullsheet.empty:
    df_pullsheet.to_excel('03_pullsheet.xlsx', index=False, header=True)
    print("Created 03_pullsheet.xlsx")

if not df_items.empty:
    df_items.to_excel('04_order_targets.xlsx', index=False, header=True)
    print("Created 04_order_targets.xlsx")

if not df_alt_stock.empty:
    df_alt_stock.to_excel('05_alt_inventory.xlsx', index=False, header=True)
    print("Created 05_alt_inventory.xlsx")

# Clean up
cursor.close()
dbconn.close()
print("Processing complete!")