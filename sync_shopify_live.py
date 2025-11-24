#!/usr/bin/env python3
"""
Shopify Live Import & Sync Status

This script fetches orders directly from Shopify API (last 30 days), compares with Odoo,
displays sync status in terminal, and generates import CSV files for unmatched orders.

Eliminates the need for manual orders_export.csv while providing sync visibility.
"""

import requests
import pandas as pd
import xmlrpc.client
import ssl
import sys
import os
import csv
from datetime import datetime, timedelta

# Import credentials
try:
    from shopify_export_cred import clean_shop_url, access_token
except ImportError:
    print("ERROR: shopify_export_cred.py not found")
    sys.exit(1)

try:
    from odoosys import url, db, username, password
except ImportError:
    print("ERROR: odoosys.py not found")
    sys.exit(1)

# Configuration
SHOPIFY_URL = clean_shop_url
ACCESS_TOKEN = access_token
API_VERSION = '2024-01'
DAYS_TO_FETCH = 30

# Odoo connection
common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(url), use_datetime=True, context=ssl._create_unverified_context())
uid = common.authenticate(db, username, password, {})
models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(url), use_datetime=True, context=ssl._create_unverified_context())

# SKU correction tracking
sku_corrections = []
sku_cache = {}

class UserAbortException(Exception):
    """Raised when user aborts the script"""
    pass

# ============================================================================
# SHOPIFY API FUNCTIONS
# ============================================================================

def fetch_shopify_orders_last_n_days(days=30):
    """
    Fetches orders from Shopify created in the last N days.
    Returns list of order dictionaries.
    """
    orders = []
    page_count = 1
    base_url = f"https://{SHOPIFY_URL}/admin/api/{API_VERSION}"
    headers = {
        'X-Shopify-Access-Token': ACCESS_TOKEN,
        'Content-Type': 'application/json'
    }

    # Calculate date range
    created_at_min = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%S%z')

    params = {
        'limit': 250,
        'status': 'any',
        'created_at_min': created_at_min,
        'order': 'created_at desc'
    }

    url_params = "&".join([f"{k}={v}" for k, v in params.items()])
    url = f"{base_url}/orders.json?{url_params}"

    print(f"\nFetching Shopify orders from last {days} days...")

    while url:
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()

            data = response.json()
            current_page_orders = data.get('orders', [])

            if not current_page_orders:
                break

            orders.extend(current_page_orders)
            print(f"  Page {page_count}: {len(current_page_orders)} orders")

            # Check for next page
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
            return None

    print(f"Total orders fetched: {len(orders)}")
    return orders

def flatten_shopify_order(order):
    """
    Flattens a Shopify order into rows (one per line item) matching orders_export.csv format.
    """
    rows = []

    # Extract order-level data
    order_data = {
        'Name': order.get('name'),
        'Email': order.get('email'),
        'Financial Status': order.get('financial_status'),
        'Paid at': order.get('processed_at'),
        'Fulfillment Status': order.get('fulfillment_status') or 'unfulfilled',
        'Fulfilled at': order.get('fulfillments', [{}])[0].get('created_at') if order.get('fulfillments') else '',
        'Billing Name': f"{(order.get('billing_address') or {}).get('first_name', '')} {(order.get('billing_address') or {}).get('last_name', '')}".strip(),
        'Billing Street': (order.get('billing_address') or {}).get('address1', ''),
        'Billing City': (order.get('billing_address') or {}).get('city', ''),
        'Billing Zip': (order.get('billing_address') or {}).get('zip', ''),
        'Billing Province': (order.get('billing_address') or {}).get('province_code', ''),
        'Billing Country': (order.get('billing_address') or {}).get('country_code', ''),
        'Billing Phone': (order.get('billing_address') or {}).get('phone', ''),
        'Refunded Amount': sum(float(t.get('amount', 0.0)) for r in order.get('refunds', []) for t in r.get('transactions', [])),
    }

    # Extract line items
    line_items = order.get('line_items', [])
    for item in line_items:
        row = order_data.copy()
        row.update({
            'Lineitem quantity': item.get('quantity'),
            'Lineitem name': item.get('name'),
            'Lineitem price': item.get('price'),
            'Lineitem sku': item.get('sku', ''),
        })
        rows.append(row)

    return rows

# ============================================================================
# ODOO FUNCTIONS
# ============================================================================

def get_simple_location(location):
    """Strip the stock root prefix from location name"""
    if location.startswith("F/Stock/"):
        return location[8:]
    else:
        return location

def search_odoo_products(search_term):
    """Search for products in Odoo by name - only products that can be sold"""
    try:
        products = models.execute_kw(db, uid, password, 'product.template', 'search_read',
            [[['name', 'ilike', search_term], ['sale_ok', '=', True]]],
            {'fields': ['name', 'default_code'], 'limit': 50})

        products_with_stock = []
        for p in products:
            if not p.get('default_code'):
                continue

            # Get product.product variant IDs
            product_ids = models.execute_kw(db, uid, password, 'product.product', 'search',
                [[['product_tmpl_id', '=', p['id']], ['default_code', '=', p['default_code']]]])

            if not product_ids:
                p['stock_info'] = []
                products_with_stock.append(p)
                continue

            # Query stock.quant
            quants = models.execute_kw(db, uid, password, 'stock.quant', 'search_read',
                [[['product_id', 'in', product_ids],
                  ['quantity', '>', 0],
                  ['location_id.usage', '=', 'internal']]],
                {'fields': ['location_id', 'quantity'], 'limit': 5})

            stock_info = []
            for q in quants:
                loc_full = q['location_id'][1] if q['location_id'] else 'Unknown'
                loc_short = get_simple_location(loc_full)
                qty = int(q['quantity'])
                stock_info.append({'qty': qty, 'loc': loc_short})

            p['stock_info'] = stock_info
            products_with_stock.append(p)

        return products_with_stock
    except Exception as e:
        print(f"Error searching Odoo: {e}")
        return []

def interactive_sku_lookup(lineitem_name, order_name, current_sku='', page_size=10):
    """Interactive SKU lookup - prompt user to find correct SKU in Odoo"""
    print(f"\n{'='*80}")
    print(f"SKU Issue Found")
    print(f"{'='*80}")
    print(f"Order: {order_name}")
    print(f"Product: {lineitem_name}")
    if current_sku:
        print(f"Current SKU: {current_sku} (not found in Odoo)")
    else:
        print(f"Current SKU: (missing)")
    print()

    while True:
        search = input("Search term ('skip' to skip, 'qqq' to exit script): ").strip()

        if search.lower() == 'skip':
            sku_cache[lineitem_name] = None
            return None

        if search.lower() == 'qqq':
            raise UserAbortException("User aborted during SKU search")

        if not search:
            print("Please enter a search term")
            continue

        results = search_odoo_products(search)

        if not results:
            print(f"No products found matching '{search}'. Try again.")
            continue

        # Paginate results
        total_results = len(results)
        current_page = 0

        while True:
            page_start = current_page * page_size
            page_end = min((current_page + 1) * page_size, total_results)

            print(f"\nFound {total_results} matching product(s):")
            for i in range(page_start, page_end):
                display_num = i + 1
                prod = results[i]

                stock_info = prod.get('stock_info', [])
                if stock_info:
                    first_stock = stock_info[0]
                    qty = first_stock['qty']
                    loc = first_stock['loc']
                    qty_str = f"{qty:3d}" if qty < 1000 else str(qty)
                    print(f"{display_num}: {qty_str}, {loc}, [{prod['default_code']}] {prod['name']}")

                    for additional in stock_info[1:3]:
                        qty = additional['qty']
                        loc = additional['loc']
                        qty_str = f"{qty:3d}" if qty < 1000 else str(qty)
                        print(f"    {qty_str}, {loc}")
                else:
                    print(f"{display_num}:   0, -, [{prod['default_code']}] {prod['name']}")

            print()
            if total_results > page_size:
                total_pages = (total_results + page_size - 1) // page_size
                print(f"Page {current_page + 1}/{total_pages} ({page_start + 1}-{page_end} of {total_results})")

            prompt = "'F'wd, 'B'ck, 'R'etry search, 'S'kip, # to select, or 'qqq': "
            choice = input(prompt).strip().lower()

            if choice == 'qqq':
                raise UserAbortException("User aborted during product selection")
            elif choice == 's':
                sku_cache[lineitem_name] = None
                return None
            elif choice == 'r':
                break
            elif choice == 'f':
                if page_end < total_results:
                    current_page += 1
                else:
                    print("Already on the last page.")
            elif choice == 'b':
                if current_page > 0:
                    current_page -= 1
                else:
                    print("Already on the first page.")
            elif choice.isdigit():
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < total_results:
                        selected_sku = results[idx]['default_code']
                        print(f"✓ Selected: {selected_sku}")

                        sku_cache[lineitem_name] = selected_sku

                        sku_corrections.append({
                            'Order': order_name,
                            'Product Name': lineitem_name,
                            'Shopify SKU': current_sku if current_sku else '(missing)',
                            'Corrected to Odoo SKU': selected_sku,
                            'Action': 'Update SKU in Shopify'
                        })

                        return selected_sku
                    else:
                        print("Invalid selection number")
                except ValueError:
                    print("Invalid input")
            else:
                print("Invalid input. Please enter a valid option.")

def load_odoo_data():
    """Load contacts, orders, and SKUs from Odoo"""
    print("\nLoading Odoo data...")

    # Load contacts
    try:
        polling = models.execute_kw(db, uid, password, 'res.partner', 'search', [[['type', '=', 'contact']]])
        if len(polling) > 0:
            contacts = models.execute_kw(db, uid, password, 'res.partner', 'read', [polling], {'fields': ['name', 'city', 'street']})
            df_contacts = pd.DataFrame(contacts)
        else:
            df_contacts = pd.DataFrame()
    except Exception as e:
        print(f"Error querying contacts: {e}")
        df_contacts = pd.DataFrame()

    # Load orders
    try:
        polling = models.execute_kw(db, uid, password, 'sale.order', 'search', [[]])
        if len(polling) > 0:
            orders = models.execute_kw(db, uid, password, 'sale.order', 'read', [polling], {'fields': ['name', 'partner_id', 'state', 'date_order']})
            df_orders = pd.DataFrame(orders)
        else:
            df_orders = pd.DataFrame()
    except Exception as e:
        print(f"Error querying sale orders: {e}")
        df_orders = pd.DataFrame()

    # Load product SKUs
    try:
        all_products = models.execute_kw(db, uid, password, 'product.template', 'search_read',
            [[]], {'fields': ['default_code'], 'limit': 10000})
        odoo_skus = set([p.get('default_code') for p in all_products if p.get('default_code')])
    except Exception as e:
        print(f"Error querying products: {e}")
        odoo_skus = set()

    print(f"  Loaded {len(df_contacts)} contacts, {len(df_orders)} orders, {len(odoo_skus)} SKUs")

    return df_contacts, df_orders, odoo_skus

# ============================================================================
# DISPLAY FUNCTIONS
# ============================================================================

def truncate(text, width):
    """Truncate text to width, adding ... if needed"""
    text = str(text) if text else ''
    if len(text) <= width:
        return text
    return text[:width-3] + '...'

def display_sync_status(df, df_orders):
    """
    Display sync status in terminal (80-char width).
    Columns: Order# | Qty | Item | Sync | S-Ful | O-Ful
    """
    print("\n" + "="*80)
    print("SHOPIFY TO ODOO SYNC STATUS (Last 30 Days)".center(80))
    print("="*80)

    # Header
    print(f"{'Order':<8} {'Qty':>3} {'Item':<35} {'Sync':^6} {'S-Ful':^6} {'O-Ful':^6}")
    print("-"*80)

    # Group by order
    current_order = None
    for _, row in df.iterrows():
        order_num = row['Name']
        qty = int(row['Lineitem quantity']) if pd.notna(row['Lineitem quantity']) else 0
        item_name = truncate(row['Lineitem name'], 35)

        # Check if in Odoo
        in_odoo = order_num in df_orders['name'].values if not df_orders.empty and 'name' in df_orders.columns else False
        sync_status = '[O]' if in_odoo else '[N]'

        # Fulfillment status
        s_ful = row.get('Fulfillment Status', '')
        s_ful_short = 'fulfil' if s_ful == 'fulfilled' else 'unfil' if s_ful == 'unfulfilled' else truncate(s_ful, 6)

        o_ful = '-' if not in_odoo else 'done'  # Simplified - would need to query actual status

        # Print row
        if order_num != current_order:
            # New order - show order number
            print(f"{order_num:<8} {qty:3d} {item_name:<35} {sync_status:^6} {s_ful_short:^6} {o_ful:^6}")
            current_order = order_num
        else:
            # Continuation of same order - blank order column
            print(f"{'':<8} {qty:3d} {item_name:<35} {sync_status:^6} {s_ful_short:^6} {o_ful:^6}")

    print("="*80)
    print(f"Legend: [N]=Not in Odoo  [O]=In Odoo  S-Ful=Shopify  O-Ful=Odoo")
    print("="*80)

# ============================================================================
# MAIN WORKFLOW
# ============================================================================

def main():
    """Main execution flow"""
    try:
        # Step 1: Fetch from Shopify
        shopify_orders = fetch_shopify_orders_last_n_days(DAYS_TO_FETCH)
        if shopify_orders is None:
            print("Failed to fetch orders from Shopify. Aborting.")
            sys.exit(1)

        if not shopify_orders:
            print("No orders found in the last 30 days.")
            sys.exit(0)

        # Step 2: Flatten orders to line items
        print("\nProcessing Shopify orders...")
        all_rows = []
        for order in shopify_orders:
            rows = flatten_shopify_order(order)
            all_rows.extend(rows)

        df_shopify = pd.DataFrame(all_rows)

        # Step 3: Apply filters (same as orders_export.csv)
        print("Applying filters...")
        initial_count = len(df_shopify['Name'].unique()) if len(df_shopify) > 0 else 0

        # Filter: paid, not refunded, not fulfilled
        df_filtered = df_shopify[
            (df_shopify['Financial Status'] == 'paid') &
            (df_shopify['Refunded Amount'] == 0) &
            (df_shopify['Fulfilled at'] == '')
        ].copy()

        filtered_count = len(df_filtered['Name'].unique()) if len(df_filtered) > 0 else 0
        print(f"  {initial_count} total orders -> {filtered_count} after filters (paid, not refunded, not fulfilled)")

        if df_filtered.empty:
            print("\nNo orders match the criteria. Nothing to import.")
            sys.exit(0)

        # Step 4: Load Odoo data
        df_contacts, df_orders, odoo_skus = load_odoo_data()

        # Step 5: Display sync status
        display_sync_status(df_filtered, df_orders)

        # Step 6: Check for orders already in Odoo
        already_imported = set()
        if not df_orders.empty and 'name' in df_orders.columns:
            unique_order_names = df_filtered['Name'].unique()
            for order_name in unique_order_names:
                if order_name in df_orders['name'].values:
                    already_imported.add(order_name)

        if already_imported:
            df_filtered = df_filtered[~df_filtered['Name'].isin(already_imported)]
            print(f"\n✓ Skipped {len(already_imported)} order(s) already in Odoo:")
            for order_name in sorted(already_imported):
                print(f"  - {order_name}")
            print()

        if df_filtered.empty:
            print("\nAll orders are already imported to Odoo. Nothing new to process.")
            sys.exit(0)

        # Step 7: Interactive SKU validation for unmatched orders
        print(f"\nValidating SKUs for {len(df_filtered)} line items...")

        for idx, row in df_filtered.iterrows():
            sku = row['Lineitem sku']
            lineitem_name = row['Lineitem name']
            order_name = row['Name']

            if not lineitem_name:
                continue

            if not sku or sku not in odoo_skus:
                # Check cache first
                if lineitem_name in sku_cache:
                    corrected_sku = sku_cache[lineitem_name]
                    if corrected_sku:
                        print(f"✓ Auto-applying cached correction: {lineitem_name[:50]}... -> {corrected_sku}")
                        df_filtered.at[idx, 'Lineitem sku'] = corrected_sku
                        sku_corrections.append({
                            'Order': order_name,
                            'Product Name': lineitem_name,
                            'Shopify SKU': sku if sku else '(missing)',
                            'Corrected to Odoo SKU': corrected_sku,
                            'Action': 'Update SKU in Shopify'
                        })
                    else:
                        df_filtered.at[idx, 'Lineitem sku'] = '__SKIP__'
                else:
                    # Not in cache - prompt user
                    corrected_sku = interactive_sku_lookup(lineitem_name, order_name, sku)
                    if corrected_sku:
                        df_filtered.at[idx, 'Lineitem sku'] = corrected_sku
                    else:
                        sku_corrections.append({
                            'Order': order_name,
                            'Product Name': lineitem_name,
                            'Shopify SKU': sku if sku else '(missing)',
                            'Corrected to Odoo SKU': '(skipped)',
                            'Action': 'SKIPPED - Order line will not be imported'
                        })
                        df_filtered.at[idx, 'Lineitem sku'] = '__SKIP__'

        # Step 8: Handle skipped orders
        skipped_rows = df_filtered[df_filtered['Lineitem sku'] == '__SKIP__']
        skipped_order_names = []

        if len(skipped_rows) > 0:
            skipped_order_names = skipped_rows['Name'].unique()
            print(f"\n{'='*80}")
            print(f"UNRESOLVED: {len(skipped_order_names)} order(s) with SKU issues")
            print(f"{'='*80}")
            print(f"Orders: {', '.join(skipped_order_names)}")
            print("\nThese orders will be excluded from import.")

            # Remove skipped orders
            df_filtered = df_filtered[~df_filtered['Name'].isin(skipped_order_names)]

        # Remove any remaining __SKIP__ markers
        df_filtered = df_filtered[df_filtered['Lineitem sku'] != '__SKIP__']

        if df_filtered.empty:
            print("\nNo orders remain after SKU validation. Nothing to import.")
            sys.exit(0)

        # Step 9: Generate CSV files for Odoo import
        print(f"\n{'='*80}")
        print("GENERATING ODOO IMPORT FILES")
        print(f"{'='*80}")

        # Create orders CSV
        df_orders_final = pd.DataFrame({
            'Order Reference': df_filtered['Name'],
            'Customer': df_filtered['Billing Name'],
            'Invoice Address': 'Shopify',
            'Delivery Address': df_filtered['Billing Name'],
            'Order Date': df_filtered['Paid at'],
            'OrderLines/Quantity': df_filtered['Lineitem quantity'],
            'OrderLines/Price_unit': df_filtered['Lineitem price'],
            'Order Lines/Product': df_filtered['Lineitem sku']
        })

        # For multi-line orders, clear header info for subsequent lines
        df_orders_final['is_first_line'] = ~df_orders_final.duplicated(subset=['Order Reference'], keep='first')
        df_orders_final.loc[~df_orders_final['is_first_line'], ['Order Reference', 'Customer', 'Invoice Address', 'Delivery Address', 'Order Date']] = ''
        df_orders_final = df_orders_final.drop('is_first_line', axis=1)

        # Clean up date format
        df_orders_final['Order Date'] = df_orders_final['Order Date'].str.replace(r' -0500', r'')
        df_orders_final['Order Date'] = df_orders_final['Order Date'].str.replace(r' -0400', r'')

        df_orders_final.to_csv('02_orders_upload.csv', index=False, header=True)
        print(f"✓ Created 02_orders_upload.csv ({len(df_orders_final)} line items)")

        # Create contacts CSV
        keep_col = ['Email', 'Billing Name', 'Billing Street', 'Billing City', 'Billing Zip', 'Billing Province', 'Billing Country', 'Billing Phone']
        df_contacts_work = df_filtered[keep_col].copy()
        df_contacts_work = df_contacts_work.fillna('')
        df_contacts_work = df_contacts_work[df_contacts_work['Billing Name'] != ""]

        dict_rename = {
            'Billing Name': 'Name',
            'Billing Street': 'Street',
            'Billing City': 'City',
            'Billing Zip': 'Zip',
            'Billing Province': 'State',
            'Billing Country': 'Country',
            'Billing Phone': 'Phone'
        }
        df_contacts_work.rename(columns=dict_rename, inplace=True)
        df_contacts_work = df_contacts_work.drop_duplicates(subset=['Name'], keep='first')

        df_contacts_work['Is a company'] = '0'
        df_contacts_work['Address type'] = 'Contact'

        # Check for duplicates against existing contacts
        if not df_contacts.empty and 'name' in df_contacts.columns:
            df_contacts_work['Exist'] = df_contacts_work['Name'].isin(df_contacts['name']).astype(int)
            df_contacts_work = df_contacts_work[df_contacts_work['Exist'] != 1]
            del df_contacts_work['Exist']

        df_contacts_work.to_csv('01_contacts_upload.csv', index=False, header=True)

        final_contact_count = len(df_contacts_work)
        if final_contact_count == 0:
            print(f"✓ Created 01_contacts_upload.csv (empty - all contacts already exist)")
        else:
            print(f"✓ Created 01_contacts_upload.csv ({final_contact_count} contacts)")

        # Export SKU corrections if any
        if sku_corrections:
            corrections_file = 'sku_corrections.csv'
            with open(corrections_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['Order', 'Product Name', 'Shopify SKU', 'Corrected to Odoo SKU', 'Action'])
                writer.writeheader()
                writer.writerows(sku_corrections)
            print(f"\n✓ Created {corrections_file} ({len(sku_corrections)} corrections)")

        # Final summary
        processed_order_count = len(df_filtered['Name'].unique())
        print("\n" + "="*80)
        print("IMPORT FILES READY")
        print("="*80)
        print(f"\nOrders to import: {processed_order_count}")
        if len(already_imported) > 0:
            print(f"Already in Odoo:  {len(already_imported)} (skipped)")
        if len(skipped_order_names) > 0:
            print(f"Orders skipped:   {len(skipped_order_names)} (unresolved SKU issues)")

        print("\nUpload to Odoo:")
        if final_contact_count > 0:
            print("  1. Import 01_contacts_upload.csv → Contacts")
            print("  2. Import 02_orders_upload.csv → Sales/Quotations")
        else:
            print("  1. Skip 01_contacts_upload.csv (no new contacts)")
            print("  2. Import 02_orders_upload.csv → Sales/Quotations")
        print("="*80)

    except UserAbortException:
        print("\n" + "="*80)
        print("SCRIPT ABORTED BY USER")
        print("="*80)
        print("\nNo files were created. Orders were not processed.")
        sys.exit(1)
    except Exception as e:
        print(f"\n{'='*80}")
        print(f"ERROR: {e}")
        print(f"{'='*80}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
