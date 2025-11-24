#!/usr/bin/env python3
"""
Diagnose Shopify Orders - Export Problem Orders for Analysis

This script exports detailed information about Sales Orders where the Customer field
is set to "Shopify" instead of the actual ordering party. This helps identify where
the correct customer information is stored so we can design an update script.

Usage:
    python3 diagnose_shopify_orders.py [--output filename.csv]
"""

import pandas as pd
import xmlrpc.client
import ssl
import sys
import argparse
from datetime import datetime

# Import credentials
try:
    from odoosys import url, db, username, password
except ImportError:
    print("ERROR: odoosys.py not found")
    print("Make sure you're running this from the shopify_order_flow directory")
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='Export Sales Orders with Shopify as customer')
    parser.add_argument('--output', default='shopify_orders_diagnosis.csv',
                       help='Output CSV filename (default: shopify_orders_diagnosis.csv)')
    args = parser.parse_args()

    print("="*80)
    print("SHOPIFY ORDERS DIAGNOSTIC TOOL")
    print("="*80)
    print(f"\nConnecting to Odoo at {url}...")
    print(f"Database: {db}")
    print(f"User: {username}")

    # Connect to Odoo
    try:
        common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(url),
                                          use_datetime=True,
                                          context=ssl._create_unverified_context())
        uid = common.authenticate(db, username, password, {})

        if not uid:
            print("ERROR: Failed to authenticate with Odoo")
            sys.exit(1)

        models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(url),
                                          use_datetime=True,
                                          context=ssl._create_unverified_context())
        print(f"✓ Connected successfully (user ID: {uid})\n")

    except Exception as e:
        print(f"ERROR: Failed to connect to Odoo: {e}")
        sys.exit(1)

    # Find the 'Shopify' partner
    print("Searching for 'Shopify' contact...")
    try:
        shopify_ids = models.execute_kw(db, uid, password, 'res.partner', 'search',
            [[['name', '=', 'Shopify']]])

        if not shopify_ids:
            print("ERROR: No contact named 'Shopify' found in Odoo")
            print("This may mean the issue has been resolved or the contact has a different name.")
            sys.exit(1)

        shopify_id = shopify_ids[0]
        shopify_info = models.execute_kw(db, uid, password, 'res.partner', 'read',
            [[shopify_id]], {'fields': ['name', 'is_company', 'street', 'city', 'state_id', 'zip']})[0]

        print(f"✓ Found 'Shopify' contact (ID: {shopify_id})")
        print(f"  Type: {'Company' if shopify_info['is_company'] else 'Individual'}")
        print(f"  Address: {shopify_info.get('street', 'N/A')}, {shopify_info.get('city', 'N/A')}\n")

    except Exception as e:
        print(f"ERROR: Failed to search for Shopify contact: {e}")
        sys.exit(1)

    # Find all Sales Orders with partner_id = Shopify
    print("Searching for Sales Orders with Customer = 'Shopify'...")
    try:
        order_ids = models.execute_kw(db, uid, password, 'sale.order', 'search',
            [[['partner_id', '=', shopify_id],
              ['state', 'in', ['draft', 'sale', 'sent']]]])

        print(f"✓ Found {len(order_ids)} orders in draft/sale/sent state\n")

        if not order_ids:
            print("No problematic orders found!")
            print("All orders appear to have correct customer assignments.")
            sys.exit(0)

    except Exception as e:
        print(f"ERROR: Failed to search for orders: {e}")
        sys.exit(1)

    # Extract detailed information about each order
    print("Extracting order details...")
    print("-"*80)

    order_data = []

    for order_id in order_ids:
        try:
            # Get order details
            order = models.execute_kw(db, uid, password, 'sale.order', 'read',
                [[order_id]],
                {'fields': ['name', 'state', 'date_order', 'amount_total',
                           'partner_id', 'partner_invoice_id', 'partner_shipping_id',
                           'invoice_status', 'delivery_status']})[0]

            # Get partner names
            customer_name = order['partner_id'][1] if order['partner_id'] else 'N/A'
            invoice_name = order['partner_invoice_id'][1] if order['partner_invoice_id'] else 'N/A'
            shipping_name = order['partner_shipping_id'][1] if order['partner_shipping_id'] else 'N/A'

            # Get order lines
            line_ids = models.execute_kw(db, uid, password, 'sale.order.line', 'search',
                [[['order_id', '=', order_id]]])

            lines = []
            if line_ids:
                line_data = models.execute_kw(db, uid, password, 'sale.order.line', 'read',
                    [line_ids],
                    {'fields': ['product_id', 'name', 'product_uom_qty', 'price_unit']})
                lines = [f"{l['name']} (qty: {l['product_uom_qty']})" for l in line_data]

            # Check for related pickings/deliveries
            picking_ids = models.execute_kw(db, uid, password, 'stock.picking', 'search',
                [[['origin', '=', order['name']]]])

            picking_status = "No deliveries"
            if picking_ids:
                pickings = models.execute_kw(db, uid, password, 'stock.picking', 'read',
                    [picking_ids], {'fields': ['state', 'name']})
                picking_status = ", ".join([f"{p['name']}:{p['state']}" for p in pickings])

            # Print summary
            print(f"\nOrder: {order['name']}")
            print(f"  State: {order['state']}")
            print(f"  Customer (partner_id): {customer_name}")
            print(f"  Invoice Address: {invoice_name}")
            print(f"  Shipping Address: {shipping_name}")
            print(f"  Delivery Status: {picking_status}")

            # Add to data list
            order_data.append({
                'Order Reference': order['name'],
                'State': order['state'],
                'Date': order['date_order'],
                'Amount': order['amount_total'],
                'Current Customer (partner_id)': customer_name,
                'Invoice Address': invoice_name,
                'Shipping Address': shipping_name,
                'Invoice Status': order.get('invoice_status', 'N/A'),
                'Delivery Status': picking_status,
                'Order Lines': "; ".join(lines),
                'Customer ID': order['partner_id'][0] if order['partner_id'] else None,
                'Invoice Partner ID': order['partner_invoice_id'][0] if order['partner_invoice_id'] else None,
                'Shipping Partner ID': order['partner_shipping_id'][0] if order['partner_shipping_id'] else None,
            })

        except Exception as e:
            print(f"ERROR processing order {order_id}: {e}")
            continue

    # Export to CSV
    print("\n" + "-"*80)
    print(f"\nExporting to {args.output}...")

    df = pd.DataFrame(order_data)
    df.to_csv(args.output, index=False)

    print(f"✓ Exported {len(order_data)} orders to {args.output}")

    # Summary analysis
    print("\n" + "="*80)
    print("ANALYSIS SUMMARY")
    print("="*80)

    # Check where the correct customer might be stored
    shipping_addresses = df['Shipping Address'].unique()

    print(f"\nTotal problematic orders: {len(order_data)}")
    print(f"States: {df['State'].value_counts().to_dict()}")
    print(f"\nUnique Shipping Addresses found: {len(shipping_addresses)}")

    if len(shipping_addresses) <= 10:
        print("\nShipping addresses (potential actual customers):")
        for addr in shipping_addresses:
            count = len(df[df['Shipping Address'] == addr])
            print(f"  - {addr} ({count} order(s))")

    # Check if shipping address matches invoice address
    matches = df[df['Shipping Address'] == df['Invoice Address']]
    if len(matches) > 0:
        print(f"\n⚠ Warning: {len(matches)} order(s) have Shipping = Invoice Address")
        print("  This means we cannot use shipping address to find the correct customer")

    # Recommendations
    print("\n" + "="*80)
    print("RECOMMENDATIONS")
    print("="*80)

    if len(df[df['Shipping Address'] != 'Shopify']) > 0:
        print("\n✓ SOLUTION IDENTIFIED:")
        print("  The 'Shipping Address' (partner_shipping_id) contains the actual customers.")
        print("  An update script can safely copy partner_shipping_id → partner_id")
        print("  while preserving the invoice address as 'Shopify'.")
    else:
        print("\n⚠ MANUAL INVESTIGATION NEEDED:")
        print("  The shipping addresses also show 'Shopify' or don't contain customer info.")
        print("  You may need to manually review the Shopify export CSV to match orders")
        print("  to their correct customers, then update them individually.")

    # Check for safe vs risky updates
    safe_orders = df[df['Delivery Status'] == 'No deliveries']
    print(f"\n✓ {len(safe_orders)} order(s) are SAFE to update (no deliveries)")

    if len(safe_orders) < len(df):
        print(f"⚠ {len(df) - len(safe_orders)} order(s) have deliveries - need careful handling")

    print("\n" + "="*80)
    print(f"Review the exported file: {args.output}")
    print("="*80)

if __name__ == "__main__":
    main()
