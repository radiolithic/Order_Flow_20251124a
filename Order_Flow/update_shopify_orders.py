# update_shopify_orders.py
import requests
import pandas as pd
import sys
import argparse
import sqlite3 # Added for SQLite database interaction
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path to import from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shopify_export_cred import clean_shop_url, access_token, db_name

# --- Configuration ---
SHOP_URL = clean_shop_url
ACCESS_TOKEN = access_token
API_VERSION = '2024-01' # Or your desired API version
ORDER_STATUS = 'any' # Fetch orders of any status initially, filter later
LIMIT = 250 # Max records per API page
# Get the root directory path and use it for the database file
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FILE = os.path.join(ROOT_DIR, db_name) # SQLite database file in root directory
TABLE_NAME = 'shopify_orders' # Table name in the database

# Define expected columns based on the original orders_export_1.csv header
# (Keep this consistent for data structure)
EXPECTED_COLUMNS = [
    'Name', 'Email', 'Financial Status', 'Paid at', 'Fulfillment Status', 'Fulfilled at',
    'Accepts Marketing', 'Currency', 'Subtotal', 'Shipping', 'Taxes', 'Total',
    'Discount Code', 'Discount Amount', 'Shipping Method', 'Created at',
    'Lineitem quantity', 'Lineitem name', 'Lineitem price', 'Lineitem compare at price',
    'Lineitem sku', 'Lineitem requires shipping', 'Lineitem taxable',
    'Lineitem fulfillment status', 'Billing Name', 'Billing Street', 'Billing Address1',
    'Billing Address2', 'Billing Company', 'Billing City', 'Billing Zip',
    'Billing Province', 'Billing Country', 'Billing Phone', 'Shipping Name',
    'Shipping Street', 'Shipping Address1', 'Shipping Address2', 'Shipping Company',
    'Shipping City', 'Shipping Zip', 'Shipping Province', 'Shipping Country',
    'Shipping Phone', 'Notes', 'Note Attributes', 'Cancelled at', 'Payment Method',
    'Payment Reference', 'Refunded Amount', 'Vendor', 'Id', 'Tags', 'Risk Level', 'Shopify_ID',
    'Source', 'Lineitem discount', 'Tax 1 Name', 'Tax 1 Value', 'Tax 2 Name',
    'Tax 2 Value', 'Tax 3 Name', 'Tax 3 Value', 'Tax 4 Name', 'Tax 4 Value',
    'Tax 5 Name', 'Tax 5 Value', 'Phone', 'Receipt Number', 'Duties',
    'Billing Province Name', 'Shipping Province Name', 'Payment ID',
    'Payment Terms Name', 'Next Payment Due At', 'Payment References',
    'Lineitem Number', # Added for sequential line item numbering
    'day_paid',    # Day number from 'Paid at' field
    'month_paid',  # Month number from 'Paid at' field
    'year_paid',   # Year number from 'Paid at' field
    'plantname'    # Plant name extracted from 'Lineitem name'
]


# --- Helper Functions ---

def fetch_shopify_orders(created_at_min=None):
    """
    Fetches orders from Shopify.
    If created_at_min is provided, fetches orders created after that timestamp.
    Otherwise, fetches all orders.
    """
    orders = []
    page_count = 1
    base_url = f"https://{SHOP_URL}/admin/api/{API_VERSION}"
    headers = {
        'X-Shopify-Access-Token': ACCESS_TOKEN,
        'Content-Type': 'application/json'
    }

    params = {
        'limit': LIMIT,
        'status': ORDER_STATUS,
        'order': 'created_at asc' # Fetch oldest first within the criteria
    }

    if created_at_min:
        params['created_at_min'] = created_at_min
        print(f"Fetching orders created after {created_at_min}...")
    else:
        print("Fetching all orders...")

    # Initial URL construction
    url_params = "&".join([f"{k}={v}" for k, v in params.items()])
    url = f"{base_url}/orders.json?{url_params}"

    while url:
        print(f"Fetching page {page_count}...")
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)

            data = response.json()
            current_page_orders = data.get('orders', [])
            if not current_page_orders:
                print("No orders found on this page.")
                break

            orders.extend(current_page_orders)
            print(f"Retrieved {len(current_page_orders)} orders from page {page_count}")

            # Check for next page link in headers
            link_header = response.headers.get('Link', '')
            next_link = None
            if link_header:
                links = link_header.split(',')
                for link in links:
                    if 'rel="next"' in link:
                        next_link = link.split(';')[0].strip('<> ')
                        break
            url = next_link
            page_count += 1

        except requests.exceptions.RequestException as e:
            print(f"API request failed: {e}")
            if response is not None:
                print(f"Response status: {response.status_code}")
                print(f"Response text: {response.text}")
            return None # Indicate failure
        except Exception as e:
            print(f"An unexpected error occurred during API fetch: {e}")
            return None # Indicate failure

    print(f"\nTotal orders retrieved (before filtering): {len(orders)}")
    return orders

def flatten_order_data(orders, column_list):
    """Flattens Shopify order data based on the provided column list,
    including a sequential line item number."""
    flattened_data = []
    print("Formatting fetched orders...")
    for order in orders:
        # Basic order details (handle missing keys gracefully)
        base_details = {
            'Name': order.get('name'),
            'Email': order.get('email'),
            'Financial Status': order.get('financial_status'),
            'Paid at': order.get('processed_at'), # Often used for 'Paid at'
            'Fulfillment Status': order.get('fulfillment_status') if order.get('fulfillment_status') else 'unfulfilled',
            'Fulfilled at': order.get('fulfillments', [{}])[0].get('created_at') if order.get('fulfillments') else None, # Takes first fulfillment
            'Accepts Marketing': 'yes' if order.get('buyer_accepts_marketing') else 'no',
            'Currency': order.get('currency'),
            'Subtotal': order.get('subtotal_price'),
            'Shipping': order.get('total_shipping_price_set', {}).get('shop_money', {}).get('amount'),
            'Taxes': order.get('total_tax'),
            'Total': order.get('total_price'),
            'Discount Code': ', '.join([d.get('code', '') for d in order.get('discount_codes', [])]) if order.get('discount_codes') else '',
            'Discount Amount': order.get('total_discounts'),
            'Shipping Method': (order.get('shipping_lines', [{}]) or [{}])[0].get('title') if order.get('shipping_lines') else None,
            'Created at': order.get('created_at'),
            'Billing Name': f"{(order.get('billing_address') or {}).get('first_name', '')} {(order.get('billing_address') or {}).get('last_name', '')}".strip(),
            'Billing Street': (order.get('billing_address') or {}).get('address1'),
            'Billing Address1': (order.get('billing_address') or {}).get('address1'),
            'Billing Address2': (order.get('billing_address') or {}).get('address2'),
            'Billing Company': (order.get('billing_address') or {}).get('company'),
            'Billing City': (order.get('billing_address') or {}).get('city'),
            'Billing Zip': (order.get('billing_address') or {}).get('zip'),
            'Billing Province': (order.get('billing_address') or {}).get('province_code'),
            'Billing Country': (order.get('billing_address') or {}).get('country_code'),
            'Billing Phone': (order.get('billing_address') or {}).get('phone'),
            'Shipping Name': f"{(order.get('shipping_address') or {}).get('first_name', '')} {(order.get('shipping_address') or {}).get('last_name', '')}".strip(),
            'Shipping Street': (order.get('shipping_address') or {}).get('address1'),
            'Shipping Address1': (order.get('shipping_address') or {}).get('address1'),
            'Shipping Address2': (order.get('shipping_address') or {}).get('address2'),
            'Shipping Company': (order.get('shipping_address') or {}).get('company'),
            'Shipping City': (order.get('shipping_address') or {}).get('city'),
            'Shipping Zip': (order.get('shipping_address') or {}).get('zip'),
            'Shipping Province': (order.get('shipping_address') or {}).get('province_code'),
            'Shipping Country': (order.get('shipping_address') or {}).get('country_code'),
            'Shipping Phone': (order.get('shipping_address') or {}).get('phone'),
            'Notes': order.get('note'),
            'Note Attributes': str(order.get('note_attributes', [])), # Convert list to string
            'Cancelled at': order.get('cancelled_at'),
            'Payment Method': (order.get('payment_gateway_names') or ['Unknown'])[0], # Takes first gateway safely
            'Payment Reference': order.get('checkout_token') or order.get('cart_token'), # Best guess for reference
            'Refunded Amount': sum(r.get('amount', 0.0) for t in order.get('refunds', []) for r in t.get('transactions', []) if t.get('kind') == 'refund'),
            'Shopify_ID': order.get('id'),
            'Tags': order.get('tags'),
            'risk_level': order.get('order_risk', {}).get('level', 'Unknown') if order.get('order_risk') else 'Unknown',
            'Source': order.get('source_name', 'web'),
            # Removed duplicate Shopify_ID entries
            'Phone': order.get('phone', ''),  # Customer phone
            'Receipt Number': None,  # Often not directly available in API order object like this
            'Duties': order.get('total_duties'),
            # Handle potential missing address components with null checks
            'Billing Province Name': order.get('billing_address', {}).get('province', 'Unknown') if order.get('billing_address') else 'Unknown',
            'Shipping Province Name': order.get('shipping_address', {}).get('province', 'Unknown') if order.get('shipping_address') else 'Unknown',
            'Payment ID': order.get('checkout_id'), # Or other relevant ID
            'Payment Terms Name': order.get('payment_terms', {}).get('payment_terms_name') if order.get('payment_terms') else None,
            'Next Payment Due At': order.get('payment_terms', {}).get('next_payment_due_at') if order.get('payment_terms') else None,
            'Payment References': None # May need specific transaction details
        }

        # Line item details (create one row per line item)
        line_items = order.get('line_items', [])
        if not line_items: # Create at least one row even if no line items
            row_data = {col: base_details.get(col) for col in column_list}
            row_data['Lineitem Number'] = 1 # Assign 1 if no line items (shouldn't happen for real orders)
            flattened_data.append(row_data)
        else:
            for i, item in enumerate(line_items):
                line_details = {
                    'Lineitem quantity': item.get('quantity'),
                    'Lineitem name': item.get('name'),
                    'Lineitem price': item.get('price'),
                    'Lineitem compare at price': item.get('variant', {}).get('compare_at_price') if item.get('variant') else None,
                    'Lineitem sku': item.get('sku'),
                    'Lineitem requires shipping': item.get('requires_shipping'),
                    'Lineitem taxable': item.get('taxable'),
                    'Lineitem fulfillment status': item.get('fulfillment_status'),
                    'Vendor': item.get('vendor'),
                    'Lineitem discount': sum(float(d.get('amount', 0.0)) for d in item.get('discount_allocations', [])) if item.get('discount_allocations') else 0.0,
                    'Tax 1 Name': item.get('tax_lines', [{}])[0].get('title') if item.get('tax_lines') else None,
                    'Tax 1 Value': item.get('tax_lines', [{}])[0].get('price') if item.get('tax_lines') else None,
                    'Tax 2 Name': item.get('tax_lines', [{}])[1].get('title') if len(item.get('tax_lines', [])) > 1 else None,
                    'Tax 2 Value': item.get('tax_lines', [{}])[1].get('price') if len(item.get('tax_lines', [])) > 1 else None,
                    # Add Tax 3, 4, 5 similarly if needed
                    'Lineitem Number': i + 1, # Assign sequential number
                    # Extract plantname by splitting at the last hyphen and taking the first part
                    'plantname': (item.get('name') or '').split(' - ')[0].strip() if ' - ' in (item.get('name') or '') else (item.get('name') or '')
                }
                # Combine base order details with line item details
                row_data = {**base_details, **line_details}
                # Ensure all columns from the defined list are present
                full_row = {col: row_data.get(col) for col in column_list}
                flattened_data.append(full_row)

    print(f"Formatted {len(flattened_data)} rows from fetched orders.")
    return flattened_data

def get_max_created_at_from_db(db_file, table_name):
    """
    Connects to the SQLite database and retrieves the 'Created at' timestamp
    of the order with the maximum *numerical* 'Name' (e.g., #XXXX) from the specified table.
    Returns None if the table is empty, does not exist, or no valid 'Name' found.
    """
    conn = None
    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        # Check if table exists
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}';")
        if cursor.fetchone():
            # Select 'Created at' and the numerical part of 'Name', order by numerical part descending
            # and limit to 1 to get the highest numerical order name's 'Created at'
            cursor.execute(f"""
                SELECT "Created at", CAST(SUBSTR(Name, 2) AS INTEGER) AS OrderNum
                FROM {table_name}
                WHERE Name LIKE '#%'
                ORDER BY OrderNum DESC
                LIMIT 1;
            """)
            result = cursor.fetchone()

            if result:
                created_at_str = result[0]
                max_name_number = result[1]
                print(f"Highest order name number in database: #{max_name_number}, corresponding 'Created at': {created_at_str}")
                return created_at_str
            else:
                print(f"No valid order 'Name' (e.g., #1234) found in table '{table_name}'. Starting from the beginning.")
                return None
        else:
            print(f"Table '{table_name}' does not exist. Starting from the beginning.")
            return None
    except sqlite3.Error as e:
        print(f"Database error when fetching max 'Created at' by name: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while fetching max 'Created at' by name: {e}")
        return None
    finally:
        if conn:
            conn.close()


# --- Main Execution ---

if __name__ == "__main__":
    # --- Argument Parsing ---
    parser = argparse.ArgumentParser(description='Fetch Shopify orders, filter them, and store in SQLite.')
    parser.add_argument('--days', type=int, default=90,
                        help='Number of days of orders to fetch (default: 90)')
    parser.add_argument('--all', action='store_true',
                        help='Fetch all orders, overriding --days')
    args = parser.parse_args()

    # Determine the start date for fetching orders
    if args.all:
        created_at_min_to_fetch = None
        print("Fetching ALL orders (--all flag used)")
    else:
        start_date = datetime.now() - timedelta(days=args.days)
        created_at_min_to_fetch = start_date.strftime('%Y-%m-%dT%H:%M:%S%z')
        print(f"Fetching orders from the past {args.days} days (since {created_at_min_to_fetch})")


    # --- Fetch Orders ---
    print("Fetching orders from Shopify...")
    fetched_orders_raw = fetch_shopify_orders(created_at_min=created_at_min_to_fetch)

    if fetched_orders_raw is None:
        print("Failed to fetch orders from Shopify. Aborting.")
        sys.exit(1)

    if not fetched_orders_raw:
        print("No new orders found.")
        sys.exit(0)

    # --- Flatten Data ---
    print("Flattening fetched order data...")
    flattened_orders = flatten_order_data(fetched_orders_raw, EXPECTED_COLUMNS)

    if not flattened_orders:
        print("Failed to format fetched orders. Aborting.")
        sys.exit(1)

    # --- Create DataFrame ---
    orders_df = pd.DataFrame(flattened_orders)
    # Ensure columns are in the correct predefined order
    orders_df = orders_df[EXPECTED_COLUMNS]
    
    # Add month and year columns from 'Paid at'
    try:
        # Handle date parsing and formatting with null safety
        try:
            # Convert to datetime with UTC timezone awareness
            orders_df['Paid at'] = pd.to_datetime(
                orders_df['Paid at'],
                errors='coerce',
                utc=True
            ).apply(
                lambda x: x.strftime('%Y-%m-%dT%H:%M:%S%z') if pd.notnull(x) else None
            )
            
            # Extract temporal components with fallbacks
            paid_dates = pd.to_datetime(orders_df['Paid at'], errors='coerce', utc=True)
            orders_df['day_paid'] = paid_dates.dt.day.fillna(0).astype(int).astype(str).str.zfill(2)
            orders_df['month_paid'] = paid_dates.dt.month.fillna(0).astype(int).astype(str).str.zfill(2)
            orders_df['year_paid'] = paid_dates.dt.year.fillna(0).astype(int).astype(str)
            
        except Exception as e:
            print(f"Error processing dates: {e}")
            # Set default values if date processing fails
            orders_df['day_paid'] = '00'
            orders_df['month_paid'] = '00'
            orders_df['year_paid'] = '0000'
        
        print("Successfully added month_paid and year_paid columns.")
    except Exception as e:
        print(f"Warning: Error extracting month/year from 'Paid at': {e}")
        # Initialize empty columns if extraction fails
        orders_df['day_paid'] = None
        orders_df['month_paid'] = None
        orders_df['year_paid'] = None
    
    print(f"Created DataFrame with {len(orders_df)} total rows.")

    # --- Filter Data ---
    print("Filtering orders for 'Financial Status' = 'paid' (including all fulfillment statuses)...")
    filtered_df = orders_df[
        (orders_df['Financial Status'] == 'paid')
        # No longer filtering by fulfillment status
    ].copy() # Use .copy() to avoid SettingWithCopyWarning
    print(f"Filtered down to {len(filtered_df)} rows.")

    # Assign filtered_df to new_orders_df for database operations
    new_orders_df = filtered_df

    if filtered_df.empty:
        print("No orders matched the filter criteria (paid and fulfilled). Nothing to load into the database.")
        sys.exit(0)

    # --- Load to SQLite ---
    print(f"Connecting to database: {DB_FILE}")
    conn = None # Initialize conn to None
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
            "Shopify_ID" TEXT,
            "Name" TEXT,
            "Email" TEXT,
            "Created at" TEXT,
            "Paid at" TEXT,
            "Financial Status" TEXT,
            "Fulfillment Status" TEXT"""
            
        # Add all other expected columns
        for column in EXPECTED_COLUMNS:
            # Skip columns already added and avoid duplicate "Id"/"id" column
            if column.lower() != "id" and column not in ["Shopify_ID", "Name", "Email", "Created at", "Paid at", "Financial Status", "Fulfillment Status"]:
                create_table_sql += f',\n"{column}" TEXT'
        
        create_table_sql += "\n)"
        cursor.execute(create_table_sql)
        conn.commit()
        print(f"Table {TABLE_NAME} created successfully.")
        
        # Create temp table with identical schema for bulk insert
        temp_table = f"temp_{TABLE_NAME}"
        new_orders_df.to_sql(temp_table, conn, if_exists='replace', index=False)
        
        # Insert all records from temp table to main table
        print(f"Inserting {len(new_orders_df)} records into {TABLE_NAME}...")
        cols = ', '.join(f'"{col}"' for col in new_orders_df.columns)
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
            print("Database connection closed.")

    print(f"Order loading process finished. Table has been completely replaced with orders from the past {args.days} days.")