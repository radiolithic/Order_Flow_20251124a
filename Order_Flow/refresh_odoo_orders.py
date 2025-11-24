# refresh_odoo_orders.py
print("Starting refresh_odoo_orders.py...")
import xmlrpc.client
import pandas as pd
import sys
import sqlite3
from datetime import datetime, timedelta
import sys
import os
import ssl

# Add parent directory to path to import from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from odoosys import url, db, username, password
from shopify_export_cred import db_name

# --- Configuration ---
ODOO_URL = url
ODOO_DB = db
ODOO_USERNAME = username
ODOO_PASSWORD = password
# Get the root directory path and use it for the database file
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FILE = os.path.join(ROOT_DIR, db_name)  # Use full path to database in root directory
TABLE_NAME = 'odoo_orders'

# Define expected columns for the odoo_orders table
EXPECTED_COLUMNS = [
    'Odoo_ID',                  # Odoo's internal sale order ID
    'Odoo_Name',                # Odoo's sale order name (e.g., SO0001)
    'Shopify_Order_Number',     # Reference to Shopify order number
    'Customer_Name',            # Customer's name
    'Customer_Email',           # Customer's email
    'Order_Date',               # Date when the order was created
    'Order_Status',             # Status of the order in Odoo
    'Payment_Status',           # Payment status
    'Delivery_Status',          # Delivery/shipping status
    'Currency',                 # Currency code
    'Subtotal',                 # Order subtotal
    'Tax_Amount',               # Total tax amount
    'Shipping_Amount',          # Shipping cost
    'Discount_Amount',          # Discount amount
    'Total_Amount',             # Total order amount
    'Line_Number',              # Line item sequence number
    'Product_ID',               # Odoo product ID
    'Product_Default_Code',     # Internal reference (SKU) - key for matching with Shopify
    'Product_Name',             # Product name
    'Product_Description',      # Product description
    'Product_Quantity',         # Quantity ordered
    'Product_UOM',              # Unit of measure
    'Product_Unit_Price',       # Unit price
    'Product_Subtotal',         # Line item subtotal
    'Product_Tax',              # Line item tax
    'Product_Total',            # Line item total
    'Shipping_Name',            # Shipping contact name
    'Shipping_Street',          # Shipping street address
    'Shipping_Street2',         # Shipping street address line 2
    'Shipping_City',            # Shipping city
    'Shipping_State',           # Shipping state/province
    'Shipping_Zip',             # Shipping postal code
    'Shipping_Country',         # Shipping country
    'Shipping_Phone',           # Shipping phone number
    'Billing_Name',             # Billing contact name
    'Billing_Street',           # Billing street address
    'Billing_Street2',          # Billing street address line 2
    'Billing_City',             # Billing city
    'Billing_State',            # Billing state/province
    'Billing_Zip',              # Billing postal code
    'Billing_Country',          # Billing country
    'Billing_Phone',            # Billing phone number
    'Notes',                    # Order notes
    'Created_At',               # Record creation timestamp
    'Updated_At',               # Record update timestamp
    'day_ordered',              # Day number from Order_Date
    'month_ordered',            # Month number from Order_Date
    'year_ordered',             # Year number from Order_Date
]

# --- Helper Functions ---

def connect_to_odoo():
    """
    Establishes connection to the Odoo server using XML-RPC.
    Returns a tuple of (common_proxy, models_proxy, uid) if successful, None otherwise.
    """
    try:
        # Connect to Odoo server with SSL context
        common_proxy = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/common', context=ssl._create_unverified_context())
        
        # Authenticate and get user ID
        uid = common_proxy.authenticate(ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD, {})
        
        if not uid:
            print("Authentication failed. Check credentials.")
            return None
        
        # Get models proxy for data operations
        models_proxy = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/object', context=ssl._create_unverified_context())
        
        print(f"Successfully connected to Odoo server at {ODOO_URL}")
        return (common_proxy, models_proxy, uid)
    
    except Exception as e:
        print(f"Failed to connect to Odoo server: {e}")
        return None

def fetch_odoo_orders(models_proxy, uid):
    """
    Fetches all sales orders from Odoo.
    
    Args:
        models_proxy: XML-RPC proxy for Odoo models
        uid: User ID from authentication
        
    Returns:
        List of sale order dictionaries if successful, None otherwise
    """
    try:
        # Build domain filter to fetch all orders
        domain = []
        print("Fetching all orders from Odoo...")
        
        # Search for sale order IDs
        order_ids = models_proxy.execute_kw(
            ODOO_DB, uid, ODOO_PASSWORD,
            'sale.order', 'search',
            [domain],
            {'order': 'date_order asc'}
        )
        
        if not order_ids:
            print("No orders found matching the criteria.")
            return []
        
        print(f"Found {len(order_ids)} orders. Fetching details...")
        
        # Define fields to fetch
        fields = [
            'id', 'name', 'partner_id', 'date_order', 'state', 'client_order_ref',
            'amount_untaxed', 'amount_tax', 'amount_total', 'currency_id',
            'order_line', 'note', 'invoice_status', 'delivery_status',
            'partner_invoice_id', 'partner_shipping_id', 'origin'
        ]
        
        # Fetch order details
        orders = models_proxy.execute_kw(
            ODOO_DB, uid, ODOO_PASSWORD,
            'sale.order', 'read',
            [order_ids, fields]
        )
        
        print(f"Retrieved {len(orders)} orders from Odoo")
        
        # Fetch order line details for all orders
        all_order_line_ids = []
        for order in orders:
            all_order_line_ids.extend(order['order_line'])
        
        order_line_fields = [
            'id', 'order_id', 'product_id', 'name', 'product_uom_qty',
            'product_uom', 'price_unit', 'price_subtotal', 'price_tax',
            'price_total', 'sequence'
        ]
        
        order_lines = models_proxy.execute_kw(
            ODOO_DB, uid, ODOO_PASSWORD,
            'sale.order.line', 'read',
            [all_order_line_ids, order_line_fields]
        )
        
        # Create a dictionary to map order_id to its order lines
        order_lines_by_order = {}
        for line in order_lines:
            order_id = line['order_id'][0]  # Odoo returns a tuple (id, name)
            if order_id not in order_lines_by_order:
                order_lines_by_order[order_id] = []
            order_lines_by_order[order_id].append(line)
        
        # Add order lines to each order
        for order in orders:
            order['detailed_order_lines'] = order_lines_by_order.get(order['id'], [])

        # Batch fetch all product details at once
        print("Fetching product details...")
        all_product_ids = list(set([
            line['product_id'][0]
            for line in order_lines
            if line['product_id']
        ]))

        if all_product_ids:
            print(f"Fetching details for {len(all_product_ids)} unique products...")
            product_details = models_proxy.execute_kw(
                ODOO_DB, uid, ODOO_PASSWORD,
                'product.product', 'read',
                [all_product_ids, ['id', 'name', 'default_code', 'description_sale']]
            )

            # Create a dictionary to map product_id to product details
            products_by_id = {product['id']: product for product in product_details}
            print(f"Cached {len(products_by_id)} product records")

            # Add product details to each order line
            for order in orders:
                for line in order['detailed_order_lines']:
                    if line['product_id']:
                        product_id = line['product_id'][0]
                        line['product_details'] = products_by_id.get(product_id, {})

        # Fetch partner (customer) details
        partner_ids = list(set([order['partner_id'][0] for order in orders if order['partner_id']]))
        invoice_partner_ids = list(set([order['partner_invoice_id'][0] for order in orders if order['partner_invoice_id']]))
        shipping_partner_ids = list(set([order['partner_shipping_id'][0] for order in orders if order['partner_shipping_id']]))
        
        all_partner_ids = list(set(partner_ids + invoice_partner_ids + shipping_partner_ids))
        
        partner_fields = [
            'id', 'name', 'email', 'phone', 'street', 'street2',
            'city', 'state_id', 'zip', 'country_id'
        ]
        
        partners = models_proxy.execute_kw(
            ODOO_DB, uid, ODOO_PASSWORD,
            'res.partner', 'read',
            [all_partner_ids, partner_fields]
        )
        
        # Create a dictionary to map partner_id to partner details
        partners_by_id = {partner['id']: partner for partner in partners}
        
        # Add partner details to each order
        for order in orders:
            if order['partner_id']:
                order['partner_details'] = partners_by_id.get(order['partner_id'][0], {})
            if order['partner_invoice_id']:
                order['invoice_partner_details'] = partners_by_id.get(order['partner_invoice_id'][0], {})
            if order['partner_shipping_id']:
                order['shipping_partner_details'] = partners_by_id.get(order['partner_shipping_id'][0], {})
        
        return orders
    
    except Exception as e:
        print(f"Error fetching orders from Odoo: {e}")
        return None

def flatten_order_data(orders, column_list, models_proxy, uid):
    """
    Flattens Odoo order data based on the provided column list,
    including a sequential line item number.
    
    Args:
        orders: List of Odoo sale order dictionaries
        column_list: List of column names for the output
        models_proxy: XML-RPC proxy for Odoo models
        uid: User ID from authentication
        
    Returns:
        List of flattened order dictionaries
    """
    flattened_data = []
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Formatting {len(orders)} fetched orders...")

    # Fetch all states and countries once to avoid repeated API calls
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetching state and country data for caching...")
    try:
        all_states = models_proxy.execute_kw(
            ODOO_DB, uid, ODOO_PASSWORD,
            'res.country.state', 'search_read',
            [[]],
            {'fields': ['id', 'name']}
        )
        state_cache = {state['id']: state['name'] for state in all_states}
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Cached {len(state_cache)} states")
    except Exception as e:
        print(f"Warning: Could not fetch states: {e}")
        state_cache = {}

    try:
        all_countries = models_proxy.execute_kw(
            ODOO_DB, uid, ODOO_PASSWORD,
            'res.country', 'search_read',
            [[]],
            {'fields': ['id', 'name']}
        )
        country_cache = {country['id']: country['name'] for country in all_countries}
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Cached {len(country_cache)} countries")
    except Exception as e:
        print(f"Warning: Could not fetch countries: {e}")
        country_cache = {}

    for order_index, order in enumerate(orders):
        if order_index % 50 == 0:  # Progress indicator every 50 orders
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Processing order {order_index + 1}/{len(orders)}...")
        # Get state/country names from cache
        def get_state_name(state_id):
            if not state_id:
                return None
            return state_cache.get(state_id[0])

        def get_country_name(country_id):
            if not country_id:
                return None
            return country_cache.get(country_id[0])
        
        # Extract Shopify order number from client_order_ref if available
        # Extract Shopify order number from client_order_ref if available
        shopify_order_number = None
        if order.get('client_order_ref'):
            # Assuming client_order_ref contains the Shopify order number
            # This might need adjustment based on how Shopify orders are referenced in Odoo
            shopify_order_number = order['client_order_ref']
        
        # Basic order details
        base_details = {
            'Odoo_ID': order.get('id'),
            'Odoo_Name': order.get('name'),
            'Shopify_Order_Number': shopify_order_number,
            'Customer_Name': order.get('partner_details', {}).get('name'),
            'Customer_Email': order.get('partner_details', {}).get('email'),
            'Order_Date': order.get('date_order'),
            'Order_Status': order.get('state'),
            'Payment_Status': order.get('invoice_status'),
            'Delivery_Status': order.get('delivery_status'),
            'Currency': order.get('currency_id', [None, None])[1],
            'Subtotal': order.get('amount_untaxed'),
            'Tax_Amount': order.get('amount_tax'),
            'Total_Amount': order.get('amount_total'),
            'Notes': order.get('note'),
            'Created_At': datetime.now().isoformat(),
            'Updated_At': datetime.now().isoformat(),
        }
        
        # Add shipping details
        shipping_partner = order.get('shipping_partner_details', {})
        base_details.update({
            'Shipping_Name': shipping_partner.get('name'),
            'Shipping_Street': shipping_partner.get('street'),
            'Shipping_Street2': shipping_partner.get('street2'),
            'Shipping_City': shipping_partner.get('city'),
            'Shipping_State': get_state_name(shipping_partner.get('state_id')),
            'Shipping_Zip': shipping_partner.get('zip'),
            'Shipping_Country': get_country_name(shipping_partner.get('country_id')),
            'Shipping_Phone': shipping_partner.get('phone'),
        })
        
        # Add billing details
        billing_partner = order.get('invoice_partner_details', {})
        base_details.update({
            'Billing_Name': billing_partner.get('name'),
            'Billing_Street': billing_partner.get('street'),
            'Billing_Street2': billing_partner.get('street2'),
            'Billing_City': billing_partner.get('city'),
            'Billing_State': get_state_name(billing_partner.get('state_id')),
            'Billing_Zip': billing_partner.get('zip'),
            'Billing_Country': get_country_name(billing_partner.get('country_id')),
            'Billing_Phone': billing_partner.get('phone'),
        })
        
        # Extract day, month and year from Order_Date
        try:
            order_date = datetime.strptime(order.get('date_order', '').split(' ')[0], '%Y-%m-%d')
            base_details['day_ordered'] = str(order_date.day).zfill(2)
            base_details['month_ordered'] = str(order_date.month).zfill(2)
            base_details['year_ordered'] = str(order_date.year)
        except:
            base_details['day_ordered'] = '00'
            base_details['month_ordered'] = '00'
            base_details['year_ordered'] = '0000'
        
        # Line item details (create one row per line item)
        order_lines = order.get('detailed_order_lines', [])
        if not order_lines:
            # Create at least one row even if no line items
            row_data = {col: base_details.get(col) for col in column_list}
            row_data['Line_Number'] = 1
            flattened_data.append(row_data)
        else:
            for i, line in enumerate(order_lines):
                product_details = line.get('product_details', {})
                
                line_details = {
                    'Line_Number': i + 1,
                    'Product_ID': line.get('product_id', [None, None])[0],
                    'Product_Default_Code': product_details.get('default_code'),
                    'Product_Name': product_details.get('name'),
                    'Product_Description': product_details.get('description_sale'),
                    'Product_Quantity': line.get('product_uom_qty'),
                    'Product_UOM': line.get('product_uom', [None, None])[1],
                    'Product_Unit_Price': line.get('price_unit'),
                    'Product_Subtotal': line.get('price_subtotal'),
                    'Product_Tax': line.get('price_tax'),
                    'Product_Total': line.get('price_total'),
                }
                
                # Combine base order details with line item details
                row_data = {**base_details, **line_details}
                
                # Ensure all columns from the defined list are present
                full_row = {col: row_data.get(col) for col in column_list}
                flattened_data.append(full_row)
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Formatted {len(flattened_data)} rows from fetched orders.")
    return flattened_data

# --- Main Execution ---

if __name__ == "__main__":
    # --- Connect to Odoo ---
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Connecting to Odoo server...")
    odoo_connection = connect_to_odoo()
    
    if not odoo_connection:
        print("Failed to connect to Odoo server. Aborting.")
        sys.exit(1)
    
    common_proxy, models_proxy, uid = odoo_connection
    
    # --- Fetch Orders ---
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetching orders from Odoo...")
    fetched_orders = fetch_odoo_orders(models_proxy, uid)
    
    if fetched_orders is None:
        print("Failed to fetch orders from Odoo. Aborting.")
        sys.exit(1)
    
    if not fetched_orders:
        print("No new orders found.")
        sys.exit(0)
    
    # --- Flatten Data ---
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Flattening fetched order data...")
    flattened_orders = flatten_order_data(fetched_orders, EXPECTED_COLUMNS, models_proxy, uid)
    
    if not flattened_orders:
        print("Failed to format fetched orders. Aborting.")
        sys.exit(1)
    
    # --- Create DataFrame ---
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Creating DataFrame...")
    orders_df = pd.DataFrame(flattened_orders)
    # Ensure columns are in the correct predefined order
    orders_df = orders_df[EXPECTED_COLUMNS]
    
    print(f"Created DataFrame with {len(orders_df)} total rows.")
    
    # --- Load to SQLite ---
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Connecting to database: {DB_FILE}")
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{TABLE_NAME}';")
        table_exists = cursor.fetchone() is not None
        
        if table_exists:
            # Drop the existing table to replace it completely
            print(f"Dropping existing table {TABLE_NAME} to replace it with new data...")
            cursor.execute(f"DROP TABLE IF EXISTS {TABLE_NAME}")
            conn.commit()
            print(f"Table {TABLE_NAME} dropped successfully.")
        
        # Create table with all expected columns
        print(f"Creating table {TABLE_NAME} with all expected columns...")
        create_table_sql = f"""CREATE TABLE {TABLE_NAME} (
            "id" INTEGER PRIMARY KEY AUTOINCREMENT,
            "Odoo_ID" INTEGER,
            "Odoo_Name" TEXT,
            "Shopify_Order_Number" TEXT"""
            
        # Add all other expected columns
        for column in EXPECTED_COLUMNS:
            # Skip columns already added
            if column not in ["Odoo_ID", "Odoo_Name", "Shopify_Order_Number"]:
                create_table_sql += f',\n"{column}" TEXT'
        
        create_table_sql += "\n)"
        cursor.execute(create_table_sql)
        conn.commit()
        print(f"Table {TABLE_NAME} created successfully.")
        
        # Create temp table with identical schema for bulk insert
        temp_table = f"temp_{TABLE_NAME}"
        orders_df.to_sql(temp_table, conn, if_exists='replace', index=False)
        
        # Insert all records from temp table to main table
        print(f"Inserting {len(orders_df)} records into {TABLE_NAME}...")
        cols = ', '.join(f'"{col}"' for col in orders_df.columns)
        cursor.execute(f"""
            INSERT INTO {TABLE_NAME} ({cols})
            SELECT {cols} FROM {temp_table}
        """)
        conn.commit()
        
        # Cleanup and report
        cursor.execute(f"DROP TABLE IF EXISTS {temp_table}")
        inserted = cursor.rowcount
        print(f"Inserted {inserted} new records")
        print(f"Successfully wrote data to table '{TABLE_NAME}' in {DB_FILE}.")
    
    except sqlite3.Error as e:
        print(f"SQLite error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"An error occurred during database operation: {e}")
        sys.exit(1)
    finally:
        if conn:
            conn.close()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Database connection closed.")
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Order loading process finished. Table has been completely replaced with orders from Odoo.")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Script ending...")