"""
Pre-flight check for Shopify import process

Detects potential anomalies in orders_export.csv before running the full import,
giving users the option to review and correct issues or auto-skip them.
"""

import pandas as pd
import xmlrpc.client
import ssl
import os
import sys

try:
    from odoosys import url, db, username, password
except ImportError:
    print("ERROR: odoosys.py not found!")
    sys.exit(1)

def get_preflight_status():
    """
    Check for anomalies in orders_export.csv
    Returns: (has_anomalies, anomaly_count, anomaly_details)
    """
    csv_file = "orders_export.csv"

    if not os.path.exists(csv_file):
        return False, 0, "File not found"

    try:
        df_in = pd.read_csv(csv_file, sep=",")
    except PermissionError:
        return False, 0, f"{csv_file} is open in another program"
    except Exception as e:
        return False, 0, f"Error reading {csv_file}: {e}"

    # Connect to Odoo to get SKU list
    try:
        common = xmlrpc.client.ServerProxy(
            '{}/xmlrpc/2/common'.format(url),
            use_datetime=True,
            context=ssl._create_unverified_context()
        )
        uid = common.authenticate(db, username, password, {})
        models = xmlrpc.client.ServerProxy(
            '{}/xmlrpc/2/object'.format(url),
            use_datetime=True,
            context=ssl._create_unverified_context()
        )
    except Exception as e:
        return False, 0, f"Cannot connect to Odoo: {e}"

    # Load Odoo products
    try:
        all_products = models.execute_kw(db, uid, password, 'product.template', 'search_read',
            [[]], {'fields': ['default_code'], 'limit': 10000})
        odoo_skus = set([p.get('default_code') for p in all_products if p.get('default_code')])
    except Exception as e:
        return False, 0, f"Error querying Odoo products: {e}"

    # Load Odoo orders
    try:
        polling = models.execute_kw(db, uid, password, 'sale.order', 'search', [[]])
        if len(polling) > 0:
            orders = models.execute_kw(db, uid, password, 'sale.order', 'read',
                [polling], {'fields': ['name']})
            odoo_orders = set([o['name'] for o in orders])
        else:
            odoo_orders = set()
    except Exception as e:
        return False, 0, f"Error querying Odoo orders: {e}"

    # Analyze for anomalies
    anomalies = []

    # Check for orders already in Odoo
    all_order_names = df_in['Name'].fillna('').replace('', pd.NA).dropna().unique()
    already_imported = [o for o in all_order_names if o in odoo_orders]

    if already_imported:
        anomalies.append({
            'type': 'Already in Odoo',
            'count': len(already_imported),
            'orders': already_imported[:3]  # Show first 3
        })

    # Check for SKU issues
    sku_issue_orders = set()
    for idx, row in df_in.iterrows():
        sku = row.get('Lineitem sku', '')
        order_name = row.get('Name', '')
        if order_name and (not sku or sku not in odoo_skus):
            sku_issue_orders.add(order_name)

    if sku_issue_orders:
        anomalies.append({
            'type': 'SKU Issues',
            'count': len(sku_issue_orders),
            'orders': list(sku_issue_orders)[:3]  # Show first 3
        })

    # Check for excluded orders
    excluded_orders = set()
    for order_name in all_order_names:
        order_rows = df_in[df_in['Name'] == order_name]
        if len(order_rows) == 0:
            continue

        first_row = order_rows.iloc[0]

        # Check refunded
        refunded_amount = first_row.get('Refunded Amount', 0)
        try:
            if pd.notna(refunded_amount) and refunded_amount != '' and float(refunded_amount) > 0:
                excluded_orders.add(order_name)
                continue
        except (ValueError, TypeError):
            pass

        # Check financial status
        financial_status = first_row.get('Financial Status', '')
        if financial_status.lower() != 'paid':
            excluded_orders.add(order_name)
            continue

        # Check fulfillment
        fulfilled_at = first_row.get('Fulfilled at', '')
        if pd.notna(fulfilled_at) and fulfilled_at != '':
            excluded_orders.add(order_name)
            continue

    if excluded_orders:
        anomalies.append({
            'type': 'Excluded Orders',
            'count': len(excluded_orders),
            'orders': list(excluded_orders)[:3]  # Show first 3
        })

    has_anomalies = len(anomalies) > 0
    total_anomalies = sum(a['count'] for a in anomalies)

    return has_anomalies, total_anomalies, anomalies


def display_preflight_menu():
    """Display preflight check results and get user choice"""
    print("\n" + "="*80)
    print("SHOPIFY IMPORT - PRE-FLIGHT CHECK")
    print("="*80)

    has_anomalies, count, details = get_preflight_status()

    if isinstance(details, str):
        # Error message
        print(f"\nWarning: {details}")
        print("\nProceeding with standard import mode.")
        return 'run_interactive'

    if not has_anomalies:
        print("\n✓ No anomalies detected in orders_export.csv")
        print("Ready to proceed with import.\n")
        return 'run_interactive'

    # Display anomalies found
    print(f"\n⚠ Found {count} anomaly/anomalies to review:\n")

    for anomaly in details:
        print(f"  • {anomaly['type']}: {anomaly['count']} issue(s)")
        for order in anomaly['orders']:
            print(f"    - {order}")
        if anomaly['count'] > 3:
            print(f"    ... and {anomaly['count'] - 3} more")

    print("\n" + "-"*80)
    print("How would you like to proceed?\n")
    print(f"[1] Review & Fix Issues")
    print(f"    Interactively review each issue and make corrections")
    print()
    print(f"[2] Auto-Skip All Issues")
    print(f"    Skip all problematic items without prompting")
    print()
    print(f"[3] Cancel")
    print(f"    Don't run import")
    print()

    while True:
        choice = input("Enter your choice (1-3): ").strip()

        if choice == '1':
            return 'run_interactive'
        elif choice == '2':
            return 'run_skip_all'
        elif choice == '3':
            return 'cancel'
        else:
            print("Invalid choice. Please enter 1, 2, or 3.")


if __name__ == "__main__":
    choice = display_preflight_menu()

    # Output choice as exit code or environment variable approach
    # We'll use print to communicate with the wrapper script
    if choice == 'run_interactive':
        print("CHOICE:RUN_INTERACTIVE")
        sys.exit(0)
    elif choice == 'run_skip_all':
        print("CHOICE:RUN_SKIP_ALL")
        sys.exit(0)
    else:  # cancel
        print("CHOICE:CANCEL")
        sys.exit(0)
