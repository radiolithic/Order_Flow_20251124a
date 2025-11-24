import sys
import os

# Add parent directory to path to import from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from odoosys import url, db, username, password
import argparse
import xmlrpc.client
import pandas as pd
import sqlite3
import ssl
import re
import os
import time

# --- Path Setup ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
SHARED_DATA_DIR = os.path.join(PROJECT_ROOT, 'shared-data')
SQLITE_DIR = os.path.join(SHARED_DATA_DIR, 'sqlite')
DB_PATH = os.path.join(SQLITE_DIR, 'analytics.db')

# Get the output directory from the environment variable set by the runner.
OUTPUT_DIR = os.environ.get('OUTPUT_DIR')
if not OUTPUT_DIR:
    print("Warning: OUTPUT_DIR environment variable not set. Defaulting to 'shared-data/output/default'.")
    OUTPUT_DIR = os.path.join(SHARED_DATA_DIR, 'output', 'default')

# Create directories if they don't exist
os.makedirs(SQLITE_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

def clean_fields(fieldvalue):
    if fieldvalue is False:
        return ''
    if isinstance(fieldvalue, list):
        return fieldvalue[1] if len(fieldvalue) > 1 else str(fieldvalue[0])
    return str(fieldvalue)

def extract_default_code(fieldvalue):
    if isinstance(fieldvalue, list):
        fieldvalue = fieldvalue[1]
    match = re.search(r'\[(.*?)\]', str(fieldvalue))
    if match:
        return match.group(1).strip()
    return ''

def get_plant_prefix(default_code):
    parts = default_code.split('-')
    return '-'.join(parts[:-1])

def get_suffix(default_code):
    parts = default_code.split('-')
    if len(parts) > 1:
        return parts[-1]
    else:
        return ""

def authenticate_with_retry(common, db, username, password, retries=10, delay=6):
    """Attempts to authenticate with Odoo, retrying on connection errors."""
    for i in range(retries):
        try:
            uid = common.authenticate(db, username, password, {})
            print("Successfully authenticated with Odoo.")
            return uid
        except xmlrpc.client.Fault as e:
            if "KeyError: 'res.users'" in e.faultString:
                print(f"Odoo not ready yet (attempt {i+1}/{retries})... Retrying in {delay} seconds.")
                time.sleep(delay)
            else:
                print(f"An unexpected XML-RPC fault occurred: {e}")
                raise
        except Exception as e:
            print(f"A non-XML-RPC error occurred during authentication: {e}")
            # This could be a network error like ConnectionRefusedError
            print(f"Odoo not reachable (attempt {i+1}/{retries})... Retrying in {delay} seconds.")
            time.sleep(delay)

    raise Exception("Could not authenticate with Odoo after several retries.")

parser = argparse.ArgumentParser(description='Get Odoo stock data and generate reports')
parser.add_argument('--report-only', action='store_true', help='Generate reports without updating data')
args = parser.parse_args()

if not args.report_only:
    common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(url), use_datetime=True, context=ssl._create_unverified_context())
    uid = authenticate_with_retry(common, db, username, password)
    models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(url), use_datetime=True, context=ssl._create_unverified_context())

if not args.report_only:
    polling = models.execute_kw(db, uid, password, 'stock.quant', 'search', [[['location_id', 'ilike', 'F%'], ['tracking', '=', 'none'], ['product_categ_id', '=', 'Plant']]])
    stock = models.execute_kw(db, uid, password, 'stock.quant', 'read', [polling], {'fields': ['product_id', 'location_id', 'quantity', 'available_quantity']})
    df_stock = pd.DataFrame(stock)
    product_ids = df_stock['product_id'].copy()
    for column in df_stock.columns:
        if df_stock[column].apply(lambda x: isinstance(x, list)).any():
            df_stock[column] = df_stock[column].apply(clean_fields)
    df_stock['default_code'] = product_ids.apply(extract_default_code)
    df_stock['plant_prefix'] = df_stock['default_code'].apply(get_plant_prefix)
    df_stock['size_suffix'] = df_stock['default_code'].apply(get_suffix)

dbconn = sqlite3.connect(DB_PATH)
cursor = dbconn.cursor()

if not args.report_only:
    print("Fetching plant_sizes from Odoo...")
    try:
        fields_info = models.execute_kw(db, uid, password, 'plant.sizes', 'fields_get', [], {'attributes': ['string', 'type']})
        available_fields = list(fields_info.keys())
        needed_fields = ['name', 'container_capacity']
        plant_sizes_fields = [field for field in needed_fields if field in available_fields]
        plant_sizes_data = models.execute_kw(db, uid, password, 'plant.sizes', 'search_read', [[]], {'fields': plant_sizes_fields})
        df_plant_sizes = pd.DataFrame(plant_sizes_data)
        if 'id' in df_plant_sizes.columns:
            df_plant_sizes = df_plant_sizes.drop(columns=['id'])
        if not df_plant_sizes.empty and all(col in df_plant_sizes.columns for col in ['name', 'container_capacity']):
            df_plant_sizes.to_sql('plant_sizes', con=dbconn, if_exists='replace', index=False)
            print(f"Imported {len(df_plant_sizes)} plant size records from Odoo.")
        else:
            print("Warning: Could not extract required columns from Odoo data. Using existing plant_sizes table if available.")
    except Exception as e:
        print(f"Warning: Could not fetch plant_sizes from Odoo: {e}. Falling back to CSV import...")
        try:
            df_plant_sizes = pd.read_csv('../../shared-data/plant_sizes.csv', encoding='utf-8')
            df_plant_sizes.to_sql('plant_sizes', con=dbconn, if_exists='replace', index=False)
            print(f"Imported {len(df_plant_sizes)} plant size records from CSV.")
        except Exception as csv_e:
            print(f"Warning: Could not import plant_sizes.csv: {csv_e}. Using existing plant_sizes table if available.")
else:
    print("Report-only mode: Using existing plant_sizes table.")

cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='shopifyproducts'")
if cursor.fetchone() is None:
    print("Warning: shopifyproducts table not found. Please run refresh_shopify_data_current.py first. Continuing without Shopify data...")

if not args.report_only:
    if 'df_stock' in locals():
        df_stock.to_sql('odoostock', con=dbconn, if_exists='replace')
        print("Updated Odoo stock data in database")
    else:
        print("Report-only mode: No Odoo data to update")
else:
    print("Report-only mode: Skipping Odoo data update")

cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='shopifyproducts'")
has_shopify_table = cursor.fetchone() is not None
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='odoostock'")
has_odoostock_table = cursor.fetchone() is not None

if args.report_only and not has_odoostock_table:
    print("Error: Cannot run in report-only mode because odoostock table doesn't exist.")
    dbconn.close()
    exit(1)

base_queries = [
    '''DROP TABLE IF EXISTS odoo_stock_by_location''',
    '''CREATE TABLE odoo_stock_by_location AS SELECT A.product_id, A.location_id, SUM(A.quantity) AS ODOO_QTY, SUM(A.available_quantity) AS ODOO_AVAILABLE_QTY, A.default_code, A.plant_prefix, A.size_suffix, B.container_capacity FROM odoostock A LEFT OUTER JOIN plant_sizes B ON A.size_suffix = B.name GROUP BY A.product_id, A.location_id, A.default_code, A.plant_prefix, A.size_suffix, B.container_capacity''',
    '''DROP TABLE IF EXISTS odoo_total_stock''',
    '''CREATE TABLE odoo_total_stock AS SELECT A.product_id, A.default_code, A.plant_prefix, A.size_suffix, SUM(A.quantity) AS ODOO_QTY, SUM(A.available_quantity) AS ODOO_AVAILABLE_QTY, GROUP_CONCAT(A.location_id || ':' || A.quantity, ', ') AS location_breakdown, COUNT(DISTINCT A.location_id) AS location_count, MAX(B.container_capacity) AS container_capacity FROM odoostock A LEFT OUTER JOIN plant_sizes B ON A.size_suffix = B.name GROUP BY A.product_id, A.default_code, A.plant_prefix, A.size_suffix''',
    '''DROP TABLE IF EXISTS loc_count''',
    '''CREATE TABLE loc_count AS SELECT product_id, location_count AS loc_count FROM odoo_total_stock WHERE ODOO_QTY <> 0 ORDER BY loc_count DESC'''
]
shopify_queries = [
    '''DROP TABLE IF EXISTS stock_cross_reference''',
    '''CREATE TABLE stock_cross_reference AS
    WITH combined_shopify AS (
        SELECT sp.sku, MAX(sp.title) AS title, MAX(sp.status) AS status, MAX(COALESCE(si.on_hand, sp.old_inventory_quantity, 0)) AS on_hand, MAX(COALESCE(si.available, sp.inventory_quantity, 0)) AS available, MAX(COALESCE(si.committed, 0)) AS committed, MAX(COALESCE(si.unavailable, 0)) AS unavailable
        FROM shopifyproducts sp LEFT JOIN shopify_inventory si ON sp.sku = si.sku GROUP BY sp.sku
    ),
    potential_size_mismatches AS (
        WITH plant_prefixes AS (SELECT DISTINCT plant_prefix FROM odoostock WHERE plant_prefix != '')
        SELECT DISTINCT o.default_code AS odoo_sku, o.size_suffix AS odoo_size, o.quantity AS odoo_qty, s2.sku AS correct_shopify_sku, s2.option1 AS correct_size, s2.inventory_quantity AS shopify_qty, 'Size mismatch: Odoo has ' || o.size_suffix || ' but Shopify has ' || s2.option1 || ' with matching quantity' AS mismatch_note
        FROM odoostock o JOIN plant_prefixes pp ON o.plant_prefix = pp.plant_prefix LEFT JOIN shopifyproducts s1 ON o.default_code = s1.sku JOIN shopifyproducts s2 ON s2.sku LIKE o.plant_prefix || '-%' AND s2.sku != o.default_code
        WHERE o.quantity > 0 AND (s1.inventory_quantity = 0 OR s1.inventory_quantity IS NULL) AND s2.inventory_quantity > 0 AND ABS(o.quantity - s2.inventory_quantity) <= 5
    )
    SELECT A.product_id, A.location_breakdown, C.loc_count, A.ODOO_QTY AS ODOO_ONHAND_QTY, A.ODOO_AVAILABLE_QTY, CS.on_hand AS SHOPIFY_ONHAND_QTY, CS.available AS SHOPIFY_AVAILABLE_QTY, CS.committed AS SHOPIFY_COMMITTED_QTY, CS.unavailable AS SHOPIFY_UNAVAILABLE_QTY, A.ODOO_QTY - CS.on_hand AS DIFF_ONHAND, A.ODOO_AVAILABLE_QTY - CS.available AS DIFF_AVAILABLE, CS.title AS Title, CS.status AS Status, psm.correct_shopify_sku AS Potential_Correct_SKU, psm.correct_size AS Potential_Correct_Size, psm.mismatch_note AS Size_Mismatch_Note
    FROM odoo_total_stock A LEFT OUTER JOIN combined_shopify CS ON A.default_code = CS.sku LEFT OUTER JOIN loc_count C ON A.product_id = C.product_id LEFT OUTER JOIN potential_size_mismatches psm ON A.default_code = psm.odoo_sku
    WHERE (CS.status = 'active' OR CS.status IS NULL) AND A.ODOO_QTY <> 0
    ORDER BY CASE WHEN psm.mismatch_note IS NOT NULL THEN 0 ELSE 1 END, C.loc_count DESC, CASE WHEN CS.on_hand <> 0 THEN ABS(A.ODOO_QTY-CS.on_hand) ELSE A.ODOO_QTY END DESC, CASE WHEN CS.available <> 0 THEN ABS(A.ODOO_AVAILABLE_QTY-CS.available) ELSE A.ODOO_AVAILABLE_QTY END DESC
    ''',
    '''DROP TABLE IF EXISTS shopify_items_at_zero_stock'''
]

odoo_data_query = base_queries
if has_shopify_table:
    odoo_data_query.extend(shopify_queries)
else:
    print("Skipping Shopify-related queries as shopifyproducts table doesn't exist.")

if not args.report_only:
    print("Updating database tables...")
    for qry in odoo_data_query:
        cursor.execute(qry)

if has_shopify_table:
    try:
        df_stock_cross_reference = pd.read_sql('''SELECT * FROM stock_cross_reference''', con=dbconn)
        standard_filename = os.path.join(OUTPUT_DIR, 'stock_cross_reference.xlsx')
        df_stock_cross_reference.to_excel(standard_filename, index=False)
        print(f"Exported to {standard_filename}")

        print("\nScript finished. Main report generated.")
        print(f"Report saved to: {standard_filename}")

        # Automatically open the Excel file in the user's default application
        try:
            import platform
            if platform.system() == 'Windows':
                os.startfile(standard_filename)
            elif platform.system() == 'Darwin':  # macOS
                import subprocess
                subprocess.run(['open', standard_filename])
            else:  # Linux
                import subprocess
                subprocess.run(['xdg-open', standard_filename])
            print(f"Opening Excel file: {standard_filename}")
        except Exception as open_error:
            print(f"Note: Could not automatically open file (you can open it manually): {open_error}")
    except Exception as e:
        print(f"Warning: Could not export Shopify-related Excel files: {e}")
        import traceback
        traceback.print_exc()
else:
    print("Skipping Shopify-related Excel exports as shopifyproducts table doesn't exist.")

dbconn.commit()
dbconn.close()
