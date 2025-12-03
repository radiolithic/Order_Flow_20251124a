"""
Shopify to Odoo v17 Order Import Script

This script transforms Shopify order exports into two CSV files for Odoo v17 import:
1. 01_contacts_upload.csv - Customer contact information
2. 02_orders_upload.csv - Sales orders with line items

ODOO v17 REQUIREMENTS:
- Customer Addresses feature must be enabled in Odoo (Accounting → Settings → Customer Addresses)
- Uses three separate partner relationships:
  * Customer: The end customer (actual purchaser)
  * Invoice Address: The billing party (marketplace, e.g., "Shopify")
  * Delivery Address: The shipping destination (end customer)

IMPORTANT: For marketplace orders, the "Shopify" contact must exist in Odoo before importing orders.
"""

import pandas as pd
import xmlrpc.client
import ssl
from datetime import datetime, timezone
import openpyxl
import os
import sys
import csv

class UserAbortException(Exception):
    """Raised when user aborts the script"""
    pass

try:
    from odoosys import url, db, username, password
except ImportError:
    print("ERROR: odoosys.py not found!")
    print("Please create odoosys.py with your Odoo credentials:")
    print("  url = 'https://your-instance.odoo.com'")
    print("  db = 'your_database_name'")
    print("  username = 'your_username'")
    print("  password = 'your_password'")
    sys.exit(1)

common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(url), use_datetime=True,context=ssl._create_unverified_context())
uid = common.authenticate(db, username, password, {})
models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(url), use_datetime=True,context=ssl._create_unverified_context())

# SKU correction tracking
sku_corrections = []
sku_cache = {}  # Cache corrections by product name

def get_simple_location(location):
    """Strip the stock root prefix from location name"""
    if location.startswith("F/Stock/"):
        return location[8:]
    else:
        return location

def search_odoo_products(search_term):
    """Search for products in Odoo by name - only products that can be sold"""
    try:
        # Search for product templates
        products = models.execute_kw(db, uid, password, 'product.template', 'search_read',
            [[['name', 'ilike', search_term], ['sale_ok', '=', True]]],
            {'fields': ['name', 'default_code'], 'limit': 50})

        products_with_stock = []
        for p in products:
            if not p.get('default_code'):
                continue

            # Get product.product variant IDs for this template
            product_ids = models.execute_kw(db, uid, password, 'product.product', 'search',
                [[['product_tmpl_id', '=', p['id']], ['default_code', '=', p['default_code']]]])

            if not product_ids:
                # No variants found, add without stock info
                p['stock_info'] = []
                products_with_stock.append(p)
                continue

            # Query stock.quant for this product
            quants = models.execute_kw(db, uid, password, 'stock.quant', 'search_read',
                [[['product_id', 'in', product_ids],
                  ['quantity', '>', 0],
                  ['location_id.usage', '=', 'internal']]],
                {'fields': ['location_id', 'quantity'], 'limit': 5})

            # Format stock info
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
    # Check if auto-skip mode is enabled
    auto_skip = os.environ.get('SHOPIFY_IMPORT_AUTO_SKIP', '0') == '1'

    if auto_skip:
        # Auto-skip mode: skip this item without prompting
        print(f"⊘ Auto-skipping: {lineitem_name}")
        sku_cache[lineitem_name] = None
        return None

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
            # Cache the skip decision
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

        # Paginate results if there are many
        total_results = len(results)
        current_page = 0

        while True:  # Inner pagination loop
            page_start = current_page * page_size
            page_end = min((current_page + 1) * page_size, total_results)

            print(f"\nFound {total_results} matching product(s):")
            for i in range(page_start, page_end):
                display_num = i + 1
                prod = results[i]

                # Format like: 1:   2, H4C, [SKU] Product Name
                stock_info = prod.get('stock_info', [])
                if stock_info:
                    # Show first location with stock
                    first_stock = stock_info[0]
                    qty = first_stock['qty']
                    loc = first_stock['loc']
                    # Format quantity with right alignment (3 chars)
                    qty_str = f"{qty:3d}" if qty < 1000 else str(qty)
                    print(f"{display_num}: {qty_str}, {loc}, [{prod['default_code']}] {prod['name']}")

                    # Show additional locations if any
                    for additional in stock_info[1:3]:  # Show up to 2 more locations
                        qty = additional['qty']
                        loc = additional['loc']
                        qty_str = f"{qty:3d}" if qty < 1000 else str(qty)
                        print(f"    {qty_str}, {loc}")
                else:
                    # No stock - just show product info
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
                # Cache the skip decision
                sku_cache[lineitem_name] = None
                return None
            elif choice == 'r':
                break  # Break inner loop to retry search
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

                        # Cache this correction for future use
                        sku_cache[lineitem_name] = selected_sku

                        # Record the correction
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

# Load Odoo contacts
print("Loading Odoo data...")
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

# Load Odoo orders
try:
    polling = models.execute_kw(db, uid, password, 'sale.order', 'search', [[]])
    if len(polling) > 0:
        orders = models.execute_kw(db, uid, password, 'sale.order', 'read', [polling], {'fields': ['name', 'partner_id', 'state','date_order']})
        df_orders = pd.DataFrame(orders)
    else:
        df_orders = pd.DataFrame()
except Exception as e:
    print(f"Error querying sale orders: {e}")
    df_orders = pd.DataFrame()

# Load all Odoo product SKUs for validation
print("Loading Odoo products...")
try:
    all_products = models.execute_kw(db, uid, password, 'product.template', 'search_read',
        [[]], {'fields': ['default_code'], 'limit': 10000})
    odoo_skus = set([p.get('default_code') for p in all_products if p.get('default_code')])
except Exception as e:
    print(f"Error querying products: {e}")
    odoo_skus = set()

# Read orders_export.csv
csv_file = "orders_export.csv"
print(f"Reading {csv_file}...")

if not os.path.exists(csv_file):
    print(f"ERROR: {csv_file} not found")
    sys.exit(1)

try:
    df_in = pd.read_csv(csv_file, sep=",")
except PermissionError:
    print(f"ERROR: {csv_file} is open in another program. Please close it and try again.")
    sys.exit(1)
except Exception as e:
    print(f"Error reading {csv_file}: {e}")
    sys.exit(1)

# Wrap the main processing in a try block to catch user abort
try:
    #
    # CREATE Orders import candidate
    #
    print("\nProcessing orders...")

    # Filter out orders that should not be imported
    print("Filtering orders...")
    initial_row_count = len(df_in)

    # Get unique order names before filtering
    all_order_names_before = df_in['Name'].fillna('').replace('', pd.NA).dropna().unique()
    total_orders_before = len(all_order_names_before)

    # Filter criteria - exclude orders that are:
    # 1. Refunded (Refunded Amount > 0)
    # 2. Not paid (Financial Status != 'paid')
    # 3. Already fulfilled (Fulfilled at has a date - nothing left to fulfill in Odoo)

    excluded_orders = set()
    excluded_reasons = {}

    for order_name in all_order_names_before:
        order_rows = df_in[df_in['Name'] == order_name]
        if len(order_rows) == 0:
            continue

        first_row = order_rows.iloc[0]

        # Check refunded
        refunded_amount = first_row.get('Refunded Amount', 0)
        try:
            if pd.notna(refunded_amount) and refunded_amount != '' and float(refunded_amount) > 0:
                excluded_orders.add(order_name)
                excluded_reasons[order_name] = f"Refunded (${refunded_amount})"
                continue
        except (ValueError, TypeError):
            pass  # If conversion fails, treat as not refunded

        # Check financial status
        financial_status = first_row.get('Financial Status', '')
        if financial_status.lower() != 'paid':
            excluded_orders.add(order_name)
            excluded_reasons[order_name] = f"Not paid (status: {financial_status})"
            continue

        # Check fulfillment - exclude if already fulfilled
        fulfilled_at = first_row.get('Fulfilled at', '')
        if pd.notna(fulfilled_at) and fulfilled_at != '':
            excluded_orders.add(order_name)
            excluded_reasons[order_name] = "Already fulfilled"
            continue

    # Filter out excluded orders
    if excluded_orders:
        df_in = df_in[~df_in['Name'].isin(excluded_orders)]
        print(f"✓ Excluded {len(excluded_orders)} order(s):")
        for order_name in sorted(excluded_orders):
            print(f"  - {order_name}: {excluded_reasons[order_name]}")
        print()

    # Check for orders already imported to Odoo - do this BEFORE SKU validation
    already_imported = set()
    if not df_orders.empty and 'name' in df_orders.columns:
        unique_order_names = df_in['Name'].fillna('').replace('', pd.NA).dropna().unique()
        for order_name in unique_order_names:
            if order_name in df_orders['name'].values:
                already_imported.add(order_name)

        if already_imported:
            df_in = df_in[~df_in['Name'].isin(already_imported)]
            print(f"✓ Skipped {len(already_imported)} order(s) already in Odoo:")
            for order_name in sorted(already_imported):
                print(f"  - {order_name}")
            print()

    # Create and refine orders dataframe
    keep_col = ['Name','Billing Name','Paid at','Lineitem quantity','Lineitem price','Lineitem sku','Lineitem name']
    df = pd.DataFrame(df_in, columns=keep_col)

    df = df.fillna('')

    # Forward-fill order header info
    df['Name'] = df['Name'].replace('', pd.NA).ffill().fillna('')
    df['Billing Name'] = df['Billing Name'].replace('', pd.NA).ffill().fillna('')
    df['Paid at'] = df['Paid at'].replace('', pd.NA).ffill().fillna('')

    # Interactive SKU resolution for missing or invalid SKUs
    for idx, row in df.iterrows():
        sku = row['Lineitem sku']
        lineitem_name = row['Lineitem name']
        order_name = row['Name']

        # Skip if lineitem name is empty (probably a header continuation row)
        if not lineitem_name:
            continue

        # Check if SKU is missing or not in Odoo
        if not sku or sku not in odoo_skus:
            # Check cache first
            if lineitem_name in sku_cache:
                corrected_sku = sku_cache[lineitem_name]
                if corrected_sku:
                    print(f"✓ Auto-applying cached correction: {lineitem_name[:50]}... -> {corrected_sku}")
                    df.at[idx, 'Lineitem sku'] = corrected_sku
                    # Still record each occurrence
                    sku_corrections.append({
                        'Order': order_name,
                        'Product Name': lineitem_name,
                        'Shopify SKU': sku if sku else '(missing)',
                        'Corrected to Odoo SKU': corrected_sku,
                        'Action': 'Update SKU in Shopify'
                    })
                else:
                    # User previously skipped this product
                    sku_corrections.append({
                        'Order': order_name,
                        'Product Name': lineitem_name,
                        'Shopify SKU': sku if sku else '(missing)',
                        'Corrected to Odoo SKU': '(skipped)',
                        'Action': 'SKIPPED - Order line will not be imported'
                    })
                    df.at[idx, 'Lineitem sku'] = '__SKIP__'
            else:
                # Not in cache - prompt user
                corrected_sku = interactive_sku_lookup(lineitem_name, order_name, sku)
                if corrected_sku:
                    df.at[idx, 'Lineitem sku'] = corrected_sku
                else:
                    # User skipped - record it but mark for skipping
                    sku_corrections.append({
                        'Order': order_name,
                        'Product Name': lineitem_name,
                        'Shopify SKU': sku if sku else '(missing)',
                        'Corrected to Odoo SKU': '(skipped)',
                        'Action': 'SKIPPED - Order line will not be imported'
                    })
                    # Mark this row for removal
                    df.at[idx, 'Lineitem sku'] = '__SKIP__'

    # Check for skipped rows and offer second chance
    skipped_rows = df[df['Lineitem sku'] == '__SKIP__']
    auto_skip = os.environ.get('SHOPIFY_IMPORT_AUTO_SKIP', '0') == '1'

    if len(skipped_rows) > 0 and not auto_skip:
        print(f"\n{'='*80}")
        print(f"SECOND CHANCE: {len(skipped_rows)} line item(s) were skipped")
        print(f"{'='*80}")

        # Group by product name to avoid asking multiple times for same product
        unique_skipped_products = skipped_rows['Lineitem name'].unique()

        for product_name in unique_skipped_products:
            print(f"\nRetry resolution for: {product_name}")
            retry = input("'R'etry lookup, or press Enter to keep skipped: ").strip().lower()

            if retry == 'r':
                # Find a sample order for this product
                sample_row = skipped_rows[skipped_rows['Lineitem name'] == product_name].iloc[0]
                order_name = sample_row['Name']
                current_sku = sample_row['Lineitem sku'] if sample_row['Lineitem sku'] != '__SKIP__' else ''

                # Try lookup again
                corrected_sku = interactive_sku_lookup(product_name, order_name, current_sku)

                if corrected_sku:
                    # Apply correction to all rows with this product
                    mask = (df['Lineitem name'] == product_name) & (df['Lineitem sku'] == '__SKIP__')
                    df.loc[mask, 'Lineitem sku'] = corrected_sku
                    print(f"✓ Applied {corrected_sku} to all instances of this product")

    # Final check for remaining skipped rows
    still_skipped = df[df['Lineitem sku'] == '__SKIP__']
    skipped_order_names = []

    if len(still_skipped) > 0:
        # Get complete order records for skipped items
        skipped_order_names = still_skipped['Name'].unique()

        print(f"\n{'='*80}")
        print(f"UNRESOLVED: {len(skipped_order_names)} order(s) with unresolved SKU issues")
        print(f"{'='*80}")
        print(f"Orders: {', '.join(skipped_order_names)}")
        print("\nThese orders will be:")
        print("  1. REMOVED from import files (will not be uploaded to Odoo)")
        print("  2. SAVED back to orders_export.csv for next run")
        print("  3. Listed in failed_orders.txt for review")

        # Write failed orders back to orders_export.csv
        failed_order_records = df_in[df_in['Name'].isin(skipped_order_names)]
        failed_order_records.to_csv('orders_export.csv', index=False)
        print(f"\n✓ Saved {len(failed_order_records)} order records back to orders_export.csv")

        # Write human-readable summary
        with open('failed_orders.txt', 'w') as f:
            f.write("="*80 + "\n")
            f.write("FAILED ORDERS - Unresolved SKU Issues\n")
            f.write("="*80 + "\n\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            for order_name in sorted(skipped_order_names):
                f.write(f"\nOrder: {order_name}\n")
                f.write("-" * 40 + "\n")
                order_items = still_skipped[still_skipped['Name'] == order_name]
                for _, item in order_items.iterrows():
                    f.write(f"  Product: {item['Lineitem name']}\n")
                    f.write(f"  Quantity: {item['Lineitem quantity']}\n")
                    f.write(f"  Price: ${item['Lineitem price']}\n")
                    f.write(f"  Issue: SKU missing or invalid\n\n")

            f.write("\n" + "="*80 + "\n")
            f.write("TO RESOLVE:\n")
            f.write("="*80 + "\n")
            f.write("1. Create missing products in Odoo OR update SKUs in Shopify\n")
            f.write("2. Run the import script again\n")
            f.write("3. The script will reprocess orders_export.csv\n\n")
            f.write("To view this file: less failed_orders.txt\n")

        print(f"✓ Created failed_orders.txt (view with: less failed_orders.txt)")

        # Remove failed orders from processing
        df = df[~df['Name'].isin(skipped_order_names)]
        print(f"\n✓ Removed failed orders from import files")

    # Remove any remaining __SKIP__ markers (shouldn't be any, but safety check)
    df = df[df['Lineitem sku'] != '__SKIP__']

    # Count unique orders in remaining dataframe (after SKU filtering)
    remaining_orders = df['Name'].fillna('').replace('', pd.NA).dropna().unique()
    processed_order_count = len(remaining_orders)

    # Count from original input for reference
    total_orders_in_input = df_in['Name'].fillna('').replace('', pd.NA).dropna().unique()
    total_order_count = len(total_orders_in_input)
    skipped_order_count = len(skipped_order_names)
    excluded_order_count = len(excluded_orders)
    already_imported_count = len(already_imported)

    # Check if there are any line items left to process
    if len(df) == 0:
        print(f"\n{'='*80}")
        print("IMPORT INCOMPLETE - NO ITEMS TO PROCESS")
        print(f"{'='*80}")
        print(f"\nOrders processed: 0")
        if already_imported_count > 0:
            print(f"Already in Odoo:  {already_imported_count} (skipped)")
        if excluded_order_count > 0:
            print(f"Orders excluded:  {excluded_order_count} (refunded/unpaid/already fulfilled)")
        if skipped_order_count > 0:
            print(f"Orders skipped:   {skipped_order_count} (unresolved SKU issues)")
        total_in_file = total_order_count + excluded_order_count + skipped_order_count + already_imported_count
        print(f"Total in file:    {total_in_file}")
        print("\n! No import files were created.")
        print("\nNext steps:")
        if skipped_order_count > 0:
            print("  1. View failed orders in failed_orders.txt")
            print("  2. Fix SKU issues in Odoo or Shopify")
            print("  3. Re-run import to process the failed orders")
        else:
            print("  1. All orders were excluded (refunded/unpaid/already fulfilled)")
            print("  2. Clean up your Shopify export to include only paid, unfulfilled orders")
        print(f"{'='*80}")
        sys.exit(1)  # Exit with error code

    print(f"\nProcessing {len(df)} order line(s) from {processed_order_count} order(s)...")

    # Create the order structure where only the first line of each order has header info
    # v17 CHANGES: Customer = End customer, Invoice Address = Marketplace, Delivery Address = End customer
    df_final = pd.DataFrame({
        'Order Reference': df['Name'],
        'Customer': df['Billing Name'],  # v17: Use actual customer name
        'Invoice Address': 'Shopify',  # v17: Marketplace for billing
        'Delivery Address': df['Billing Name'],  # v17: Ship to customer
        'Order Date': df['Paid at'],
        'OrderLines/Quantity': df['Lineitem quantity'],
        'OrderLines/Price_unit': df['Lineitem price'],
        'Order Lines/Product': df['Lineitem sku']
    })

    # For multi-line orders, clear header info for subsequent lines
    df_final['is_first_line'] = ~df_final.duplicated(subset=['Order Reference'], keep='first')
    df_final.loc[~df_final['is_first_line'], ['Order Reference', 'Customer', 'Invoice Address', 'Delivery Address', 'Order Date']] = ''

    # Drop the helper column
    df_final = df_final.drop('is_first_line', axis=1)

    # Clean up date format
    df_final['Order Date'] = df_final['Order Date'].str.replace(r' -0500', r'')
    df_final['Order Date'] = df_final['Order Date'].str.replace(r' -0400', r'')

    df_final.to_csv('02_orders_upload.csv', index=False, header=True)
    print(f"✓ Created 02_orders_upload.csv ({len(df_final)} line items)")

    # Save counts for final summary
    final_order_line_count = len(df_final)

    #
    # CREATE Contacts Upload
    #
    print("Processing contacts...")

    # Create and refine contacts dataframe - use BILLING info for contacts
    keep_col = ['Email','Billing Name','Billing Street','Billing City','Billing Zip','Billing Province','Billing Country','Billing Phone']
    df = pd.DataFrame(df_in, columns=keep_col)
    df = df.fillna('')

    # Filter out rows with empty Billing Name
    df = df[df['Billing Name'] != ""]

    # Rename columns to match Odoo import format
    dict_rename = {
        'Billing Name': 'Name',
        'Billing Street': 'Street',
        'Billing City': 'City',
        'Billing Zip': 'Zip',
        'Billing Province': 'State',
        'Billing Country': 'Country',
        'Billing Phone': 'Phone'
    }
    df.rename(columns=dict_rename, inplace=True)

    # Remove duplicates within the CSV itself
    df = df.drop_duplicates(subset=['Name'], keep='first')

    # Add required fields
    df['Is a company'] = '0'
    df['Address type'] = 'Contact'

    # Check for duplicates against existing contacts
    if not df_contacts.empty and 'name' in df_contacts.columns:
        df['Exist'] = df['Name'].isin(df_contacts['name']).astype(int)
        df = df[df['Exist'] != 1]
        del df['Exist']

    df.to_csv('01_contacts_upload.csv', index=False, header=True)

    # Save contact count for final summary
    final_contact_count = len(df)

    if final_contact_count == 0:
        print(f"✓ Created 01_contacts_upload.csv (empty - all contacts already exist in Odoo)")
    else:
        print(f"✓ Created 01_contacts_upload.csv ({final_contact_count} contacts)")

    # Export SKU corrections if any were made
    if sku_corrections:
        corrections_file = 'sku_corrections.csv'
        with open(corrections_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['Order', 'Product Name', 'Shopify SKU', 'Corrected to Odoo SKU', 'Action'])
            writer.writeheader()
            writer.writerows(sku_corrections)
        print(f"\n✓ Created {corrections_file} ({len(sku_corrections)} corrections)")
        print("  Review sku_corrections.csv to update SKUs in Shopify")

    # Final summary
    print("\n" + "="*80)
    print("IMPORT COMPLETE")
    print("="*80)

    print(f"\nOrders processed: {processed_order_count}")
    if already_imported_count > 0:
        print(f"Already in Odoo:  {already_imported_count} (skipped)")
    if excluded_order_count > 0:
        print(f"Orders excluded:  {excluded_order_count} (refunded/unpaid/already fulfilled)")
    if skipped_order_count > 0:
        print(f"Orders skipped:   {skipped_order_count} (unresolved SKU issues)")
    total_in_file = total_order_count + excluded_order_count + skipped_order_count + already_imported_count
    print(f"Total in file:    {total_in_file}")

    if os.path.exists('failed_orders.txt'):
        print("\n⚠ SKIPPED ORDERS:")
        print("  • View: Menu option [2] or 'less failed_orders.txt'")
        print("  • Saved to orders_export.csv for next run")
        print("  • Fix issues in Odoo/Shopify and re-run import")

    print("\nFiles created:")
    if final_contact_count == 0:
        print(f"  • 01_contacts_upload.csv (empty - all contacts already exist)")
    else:
        print(f"  • 01_contacts_upload.csv ({final_contact_count} contacts)")
    print(f"  • 02_orders_upload.csv ({final_order_line_count} line items)")

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
    print("Run the script again when ready to continue.")
    sys.exit(1)
