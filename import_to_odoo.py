#!/usr/bin/env python3
"""
Import to Odoo from CSV Files

This script reads the generated CSV files (01_contacts_upload.csv and 02_orders_upload.csv)
and imports them directly into Odoo via XML-RPC API.

Automates the manual CSV import process.
"""

import pandas as pd
import xmlrpc.client
import ssl
import sys
import os
import argparse
from datetime import datetime
from dateutil import parser as date_parser

# Import credentials
try:
    from odoosys import url, db, username, password
except ImportError:
    print("ERROR: odoosys.py not found")
    sys.exit(1)

# Configuration
CONTACTS_FILE = '01_contacts_upload.csv'
ORDERS_FILE = '02_orders_upload.csv'

# Odoo connection
print("Connecting to Odoo...")
common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(url), use_datetime=True, context=ssl._create_unverified_context())
uid = common.authenticate(db, username, password, {})

if not uid:
    print("ERROR: Failed to authenticate with Odoo")
    sys.exit(1)

models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(url), use_datetime=True, context=ssl._create_unverified_context())
print(f"✓ Connected to Odoo as user ID: {uid}")

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def format_datetime_for_odoo(date_string):
    """
    Convert various datetime formats to Odoo's expected format: YYYY-MM-DD HH:MM:SS
    Handles ISO 8601 with timezone, and returns timezone-naive datetime.

    Args:
        date_string: Date string in various formats (e.g., '2025-11-13T12:54:25-05:00')

    Returns:
        String in format 'YYYY-MM-DD HH:MM:SS' or None if parsing fails
    """
    if not date_string:
        return None

    try:
        # Parse the datetime string (handles timezone automatically)
        dt = date_parser.parse(date_string)

        # Convert to naive datetime (remove timezone) and format for Odoo
        return dt.replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S')
    except Exception as e:
        print(f"    WARNING: Could not parse date '{date_string}': {e}")
        # Fallback to current datetime
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def get_or_create_partner(name, email='', street='', city='', zip_code='', state='', country='', phone=''):
    """
    Get existing partner by name or create new one.
    Returns partner ID.
    """
    # Search for existing partner by name
    partner_ids = models.execute_kw(db, uid, password, 'res.partner', 'search',
        [[['name', '=', name]]])

    if partner_ids:
        return partner_ids[0]

    # Create new partner
    partner_data = {
        'name': name,
        'email': email or False,
        'street': street or False,
        'city': city or False,
        'zip': zip_code or False,
        'phone': phone or False,
        'is_company': False,
        'type': 'contact'
    }

    # Handle state (need to find state ID by code or name)
    if state:
        state_ids = models.execute_kw(db, uid, password, 'res.country.state', 'search',
            [[['code', '=', state]]])
        if state_ids:
            partner_data['state_id'] = state_ids[0]

    # Handle country (need to find country ID by code)
    if country:
        country_ids = models.execute_kw(db, uid, password, 'res.country', 'search',
            [[['code', '=', country]]])
        if country_ids:
            partner_data['country_id'] = country_ids[0]

    partner_id = models.execute_kw(db, uid, password, 'res.partner', 'create', [partner_data])
    return partner_id

def get_product_by_sku(sku):
    """
    Get product.product ID by SKU (default_code).
    Returns product ID or None if not found.
    """
    # First search product.template
    template_ids = models.execute_kw(db, uid, password, 'product.template', 'search',
        [[['default_code', '=', sku]]])

    if not template_ids:
        return None

    # Get product.product variant
    product_ids = models.execute_kw(db, uid, password, 'product.product', 'search',
        [[['product_tmpl_id', '=', template_ids[0]], ['default_code', '=', sku]]])

    if product_ids:
        return product_ids[0]

    return None

def get_product_available_qty(product_id):
    """
    Get available quantity for a product across all internal locations.
    Returns total available quantity.
    """
    try:
        # Query stock.quant for this product in internal locations
        quants = models.execute_kw(db, uid, password, 'stock.quant', 'search_read',
            [[['product_id', '=', product_id],
              ['location_id.usage', '=', 'internal']]],
            {'fields': ['quantity', 'reserved_quantity']})

        # Calculate available = on_hand - reserved
        total_available = 0
        for quant in quants:
            on_hand = float(quant.get('quantity', 0))
            reserved = float(quant.get('reserved_quantity', 0))
            available = on_hand - reserved
            total_available += available

        return total_available
    except Exception as e:
        print(f"    WARNING: Could not check stock for product ID {product_id}: {e}")
        return 0

def check_order_availability(line_items_with_products):
    """
    Check if all line items have sufficient stock.

    Args:
        line_items_with_products: List of dicts with keys: product_id, product_sku, quantity

    Returns:
        Tuple (all_available: bool, availability_details: list of dicts)
    """
    availability_details = []
    all_available = True

    for line in line_items_with_products:
        product_id = line['product_id']
        sku = line['product_sku']
        qty_needed = float(line['quantity'])

        qty_available = get_product_available_qty(product_id)
        is_available = qty_available >= qty_needed

        if not is_available:
            all_available = False

        availability_details.append({
            'sku': sku,
            'qty_needed': qty_needed,
            'qty_available': qty_available,
            'is_available': is_available
        })

    return all_available, availability_details

def create_sale_order(order_ref, customer_name, invoice_address_name, delivery_address_name,
                      order_date, line_items, auto_confirm=False):
    """
    Create a sale order (quotation) in Odoo.

    Args:
        order_ref: Order reference (e.g., #10992)
        customer_name: Customer name
        invoice_address_name: Invoice address (e.g., "Shopify")
        delivery_address_name: Delivery address name
        order_date: Order date string
        line_items: List of dicts with keys: product_sku, quantity, price_unit
        auto_confirm: If True, confirm order if all items are in stock

    Returns:
        Tuple (Sale order ID or None if failed, order_status: 'confirmed' or 'quotation')
    """
    # Get or create customer partner
    customer_id = get_or_create_partner(customer_name)

    # Get or create invoice address partner
    invoice_id = get_or_create_partner(invoice_address_name)

    # Get or create delivery address partner (same as customer for now)
    delivery_id = customer_id

    # Prepare order data
    order_data = {
        'name': order_ref,  # Use Shopify order number as the order name (e.g., #11119)
        'partner_id': customer_id,
        'partner_invoice_id': invoice_id,
        'partner_shipping_id': delivery_id,
        'date_order': format_datetime_for_odoo(order_date) or datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }

    # Create the sale order first (without lines)
    try:
        order_id = models.execute_kw(db, uid, password, 'sale.order', 'create', [order_data])
    except Exception as e:
        print(f"  ERROR creating order {order_ref}: {e}")
        return None, None

    # Add order lines
    lines_created = 0
    lines_with_products = []  # Track products for availability check

    for line in line_items:
        product_id = get_product_by_sku(line['product_sku'])

        if not product_id:
            print(f"  WARNING: Product SKU '{line['product_sku']}' not found in Odoo - skipping line")
            continue

        line_data = {
            'order_id': order_id,
            'product_id': product_id,
            'product_uom_qty': float(line['quantity']),
            'price_unit': float(line['price_unit']),
        }

        try:
            models.execute_kw(db, uid, password, 'sale.order.line', 'create', [line_data])
            lines_created += 1

            # Track for availability check
            lines_with_products.append({
                'product_id': product_id,
                'product_sku': line['product_sku'],
                'quantity': line['quantity']
            })
        except Exception as e:
            print(f"  ERROR creating order line for {line['product_sku']}: {e}")

    if lines_created == 0:
        print(f"  WARNING: No lines created for order {order_ref} - deleting order")
        models.execute_kw(db, uid, password, 'sale.order', 'unlink', [[order_id]])
        return None, None

    # Track order status
    order_status = 'quotation'

    # Check availability and confirm if requested
    if auto_confirm and lines_with_products:
        all_available, availability_details = check_order_availability(lines_with_products)

        # Show availability status
        print(f"    Stock check:")
        for detail in availability_details:
            status_icon = '✓' if detail['is_available'] else '✗'
            print(f"      {status_icon} {detail['sku']}: need {int(detail['qty_needed'])}, available {int(detail['qty_available'])}")

        if all_available:
            try:
                # Confirm the order (convert quotation to sales order)
                models.execute_kw(db, uid, password, 'sale.order', 'action_confirm', [[order_id]])
                print(f"    ✓ Order CONFIRMED (all items in stock)")
                order_status = 'confirmed'
            except Exception as e:
                print(f"    WARNING: Could not confirm order: {e}")
        else:
            print(f"    ⊘ Order left as QUOTATION (insufficient stock)")

    return order_id, order_status

# ============================================================================
# IMPORT CONTACTS
# ============================================================================

def import_contacts():
    """Import contacts from 01_contacts_upload.csv"""
    if not os.path.exists(CONTACTS_FILE):
        print(f"\n⚠ {CONTACTS_FILE} not found - skipping contact import")
        return 0

    print(f"\n{'='*80}")
    print("IMPORTING CONTACTS")
    print(f"{'='*80}")

    try:
        df = pd.read_csv(CONTACTS_FILE)
        df = df.fillna('')

        if len(df) == 0:
            print("  No contacts to import (file is empty)")
            return 0

        print(f"  Found {len(df)} contact(s) to import")

        created = 0
        skipped = 0

        for idx, row in df.iterrows():
            name = row.get('Name', '')
            if not name:
                continue

            # Check if already exists
            existing = models.execute_kw(db, uid, password, 'res.partner', 'search',
                [[['name', '=', name]]])

            if existing:
                print(f"  ⊘ Skipped: {name} (already exists)")
                skipped += 1
                continue

            # Create contact
            try:
                partner_id = get_or_create_partner(
                    name=name,
                    email=row.get('Email', ''),
                    street=row.get('Street', ''),
                    city=row.get('City', ''),
                    zip_code=row.get('Zip', ''),
                    state=row.get('State', ''),
                    country=row.get('Country', ''),
                    phone=row.get('Phone', '')
                )
                print(f"  ✓ Created: {name} (ID: {partner_id})")
                created += 1
            except Exception as e:
                print(f"  ✗ Failed: {name} - {e}")

        print(f"\n  Summary: {created} created, {skipped} skipped")
        return created

    except Exception as e:
        print(f"  ERROR reading {CONTACTS_FILE}: {e}")
        return 0

# ============================================================================
# IMPORT ORDERS
# ============================================================================

def import_orders(auto_confirm=False):
    """Import orders from 02_orders_upload.csv"""
    if not os.path.exists(ORDERS_FILE):
        print(f"\n⚠ {ORDERS_FILE} not found - skipping order import")
        return 0, 0, 0

    print(f"\n{'='*80}")
    print("IMPORTING ORDERS")
    if auto_confirm:
        print("(Auto-confirm enabled: orders with all items in stock will be confirmed)")
    print(f"{'='*80}")

    try:
        df = pd.read_csv(ORDERS_FILE)
        df = df.fillna('')

        if len(df) == 0:
            print("  No orders to import (file is empty)")
            return 0, 0, 0

        print(f"  Found {len(df)} line(s) to process")

        # Group by order (when Order Reference is not blank, it's a new order)
        current_order = None
        current_customer = None
        current_invoice_addr = None
        current_delivery_addr = None
        current_date = None
        current_lines = []

        orders_created = 0
        orders_confirmed = 0
        orders_quotation = 0
        orders_skipped = 0

        for idx, row in df.iterrows():
            order_ref = row.get('Order Reference', '').strip()

            # Check if this is a new order header (has order reference)
            if order_ref:
                # Save previous order if exists
                if current_order and current_lines:
                    # Check if order already exists by name
                    existing = models.execute_kw(db, uid, password, 'sale.order', 'search',
                        [[['name', '=', current_order]]])

                    if existing:
                        print(f"  ⊘ Skipped: {current_order} (already exists)")
                        orders_skipped += 1
                    else:
                        order_id, order_status = create_sale_order(
                            current_order, current_customer, current_invoice_addr,
                            current_delivery_addr, current_date, current_lines,
                            auto_confirm=auto_confirm
                        )
                        if order_id:
                            print(f"  ✓ Created: {current_order} (ID: {order_id}, {len(current_lines)} line(s))")
                            orders_created += 1
                            if order_status == 'confirmed':
                                orders_confirmed += 1
                            else:
                                orders_quotation += 1
                        else:
                            print(f"  ✗ Failed: {current_order}")

                # Start new order
                current_order = order_ref
                current_customer = row.get('Customer', '').strip()
                current_invoice_addr = row.get('Invoice Address', '').strip()
                current_delivery_addr = row.get('Delivery Address', '').strip()
                current_date = row.get('Order Date', '').strip()
                current_lines = []

            # Add line item to current order
            sku = row.get('Order Lines/Product', '').strip()
            qty = row.get('OrderLines/Quantity', 0)
            price = row.get('OrderLines/Price_unit', 0)

            if sku and qty:
                current_lines.append({
                    'product_sku': sku,
                    'quantity': qty,
                    'price_unit': price
                })

        # Don't forget the last order
        if current_order and current_lines:
            # Check if order already exists by name
            existing = models.execute_kw(db, uid, password, 'sale.order', 'search',
                [[['name', '=', current_order]]])

            if existing:
                print(f"  ⊘ Skipped: {current_order} (already exists)")
                orders_skipped += 1
            else:
                order_id, order_status = create_sale_order(
                    current_order, current_customer, current_invoice_addr,
                    current_delivery_addr, current_date, current_lines,
                    auto_confirm=auto_confirm
                )
                if order_id:
                    print(f"  ✓ Created: {current_order} (ID: {order_id}, {len(current_lines)} line(s))")
                    orders_created += 1
                    if order_status == 'confirmed':
                        orders_confirmed += 1
                    else:
                        orders_quotation += 1
                else:
                    print(f"  ✗ Failed: {current_order}")

        print(f"\n  Summary: {orders_created} created ({orders_confirmed} ORDERS, {orders_quotation} QUOTATIONS), {orders_skipped} skipped")
        return orders_created, orders_confirmed, orders_quotation

    except Exception as e:
        print(f"  ERROR reading {ORDERS_FILE}: {e}")
        import traceback
        traceback.print_exc()
        return 0, 0, 0

# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main execution"""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='Import contacts and orders from CSV files to Odoo',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python import_to_odoo.py                    # Import without auto-confirmation
  python import_to_odoo.py --confirm          # Auto-confirm orders with all items in stock
  python import_to_odoo.py --confirm-if-available  # Same as --confirm
        """
    )
    parser.add_argument('--confirm', '--confirm-if-available',
                        dest='auto_confirm',
                        action='store_true',
                        help='Auto-confirm orders if ALL line items are available in stock (default: NO)')

    args = parser.parse_args()

    print("\n" + "="*80)
    print("ODOO IMPORT FROM CSV FILES")
    if args.auto_confirm:
        print("Auto-confirm: YES (orders with all items in stock will be confirmed)")
    else:
        print("Auto-confirm: NO (all orders will remain as quotations)")
    print("="*80)

    # Import contacts first
    contacts_imported = import_contacts()

    # Then import orders
    orders_imported, orders_confirmed, orders_quotation = import_orders(auto_confirm=args.auto_confirm)

    # Final summary
    print("\n" + "="*80)
    print("IMPORT COMPLETE")
    print("="*80)
    print(f"  Contacts imported: {contacts_imported}")
    print(f"  Orders imported:   {orders_imported}")
    if orders_imported > 0:
        print(f"    - ORDERS (confirmed):   {orders_confirmed}")
        print(f"    - QUOTATIONS:           {orders_quotation}")
    print("="*80)

    if orders_imported > 0:
        if args.auto_confirm:
            print("\n✓ Orders with all items in stock were CONFIRMED")
            print("✓ Orders with insufficient stock remain as QUOTATIONS")
        else:
            print("\n✓ Orders are now in Odoo as QUOTATIONS")
        print("  Go to Sales → Orders to view them")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nImport cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
