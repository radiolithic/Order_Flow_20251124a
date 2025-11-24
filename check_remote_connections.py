#!/usr/bin/env python3
"""
Remote Connections Checker

This script tests connections to both Odoo and Shopify to ensure all credentials
and API access are properly configured. Can be run standalone or from the menu.

Tests performed:
- Odoo XML-RPC connection and authentication
- Odoo database access and permissions
- Shopify API connection
- Shopify access token validity
- Shopify API scopes (products, inventory)

Usage:
    python3 check_remote_connections.py           # Test both Odoo and Shopify
    python3 check_remote_connections.py --odoo    # Test only Odoo
    python3 check_remote_connections.py --shopify # Test only Shopify
"""

import sys
import os
import xmlrpc.client
import ssl
import argparse
from datetime import datetime

# Color codes for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_header(title):
    """Print a formatted header."""
    print("\n" + "=" * 80)
    print(f"{Colors.BOLD}{title}{Colors.END}")
    print("=" * 80)

def print_section(title):
    """Print a formatted section header."""
    print(f"\n{Colors.BLUE}{'─' * 80}{Colors.END}")
    print(f"{Colors.BOLD}{title}{Colors.END}")
    print(f"{Colors.BLUE}{'─' * 80}{Colors.END}")

def print_success(message):
    """Print success message."""
    print(f"{Colors.GREEN}✓{Colors.END} {message}")

def print_error(message):
    """Print error message."""
    print(f"{Colors.RED}✗{Colors.END} {message}")

def print_warning(message):
    """Print warning message."""
    print(f"{Colors.YELLOW}⚠{Colors.END} {message}")

def print_info(message):
    """Print info message."""
    print(f"  {message}")

# ============================================================================
# ODOO CONNECTION TESTS
# ============================================================================

def test_odoo_connection():
    """Test connection to Odoo server."""
    print_section("Testing Odoo Connection")

    try:
        from odoosys import url, db, username, password, systemname
    except ImportError:
        print_error("Could not import Odoo credentials from odoosys.py")
        print_info("Make sure odoosys.py exists in the current directory")
        return False

    print_info(f"System: {systemname}")
    print_info(f"URL: {url}")
    print_info(f"Database: {db}")
    print_info(f"User: {username}")

    # Test 1: Connect to common endpoint
    try:
        print("\n  Testing XML-RPC connection...")
        common = xmlrpc.client.ServerProxy(
            f'{url}/xmlrpc/2/common',
            use_datetime=True,
            context=ssl._create_unverified_context()
        )

        version_info = common.version()
        print_success("Connected to Odoo server")
        print_info(f"Odoo Version: {version_info.get('server_version', 'Unknown')}")
        print_info(f"Protocol: {version_info.get('protocol_version', 'Unknown')}")

    except ConnectionRefusedError:
        print_error(f"Connection refused to {url}")
        print_info("Is the Odoo server running and accessible?")
        return False
    except Exception as e:
        print_error(f"Failed to connect: {e}")
        return False

    # Test 2: Authenticate
    try:
        print("\n  Testing authentication...")
        uid = common.authenticate(db, username, password, {})

        if not uid:
            print_error(f"Authentication failed for user '{username}' on database '{db}'")
            print_info("Check your username and password in odoosys.py")
            return False

        print_success(f"Authentication successful (User ID: {uid})")

    except Exception as e:
        print_error(f"Authentication error: {e}")
        return False

    # Test 3: Test object endpoint and permissions
    try:
        print("\n  Testing database access...")
        models = xmlrpc.client.ServerProxy(
            f'{url}/xmlrpc/2/object',
            use_datetime=True,
            context=ssl._create_unverified_context()
        )

        # Check if we can read partners
        can_read_partners = models.execute_kw(
            db, uid, password,
            'res.partner', 'check_access_rights',
            ['read'], {'raise_exception': False}
        )

        if can_read_partners:
            print_success("Read access to contacts (res.partner): YES")
        else:
            print_warning("Read access to contacts (res.partner): NO")
            print_info("Limited permissions - some features may not work")

        # Check if we can read sale orders
        can_read_orders = models.execute_kw(
            db, uid, password,
            'sale.order', 'check_access_rights',
            ['read'], {'raise_exception': False}
        )

        if can_read_orders:
            print_success("Read access to sales orders (sale.order): YES")
        else:
            print_warning("Read access to sales orders (sale.order): NO")

        # Check if we can create sale orders
        can_create_orders = models.execute_kw(
            db, uid, password,
            'sale.order', 'check_access_rights',
            ['create'], {'raise_exception': False}
        )

        if can_create_orders:
            print_success("Create access to sales orders: YES")
        else:
            print_warning("Create access to sales orders: NO")
            print_info("You may not be able to import new orders")

        # Get a count of partners to verify data access
        partner_count = models.execute_kw(
            db, uid, password,
            'res.partner', 'search_count',
            [[]]
        )
        print_info(f"Total contacts in database: {partner_count}")

        # Get a count of sale orders
        order_count = models.execute_kw(
            db, uid, password,
            'sale.order', 'search_count',
            [[]]
        )
        print_info(f"Total sales orders in database: {order_count}")

    except Exception as e:
        print_error(f"Database access error: {e}")
        return False

    print_success("\nOdoo connection test: PASSED")
    return True

# ============================================================================
# SHOPIFY CONNECTION TESTS
# ============================================================================

def test_shopify_connection():
    """Test connection to Shopify API."""
    print_section("Testing Shopify Connection")

    # Try to import requests
    try:
        import requests
    except ImportError:
        print_error("Python 'requests' library not installed")
        print_info("Install with: pip install requests")
        return False

    # Load credentials
    try:
        from shopify_export_cred import access_token, clean_shop_url
    except ImportError:
        print_error("Could not import Shopify credentials from shopify_export_cred.py")
        print_info("Make sure shopify_export_cred.py exists in the current directory")
        return False

    if not access_token or not clean_shop_url:
        print_error("Missing required Shopify credentials")
        print_info("Ensure access_token and clean_shop_url are set in shopify_export_cred.py")
        return False

    print_info(f"Shop URL: {clean_shop_url}")
    print_info(f"Token: {access_token[:20]}..." if len(access_token) > 20 else f"Token: [SHORT]")

    # Test 1: Basic API connection
    try:
        print("\n  Testing Shopify API connection...")
        api_version = '2024-04'
        url = f"https://{clean_shop_url}/admin/api/{api_version}/shop.json"
        headers = {
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json"
        }

        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            shop_data = response.json().get('shop', {})
            print_success("Connected to Shopify API")
            print_info(f"Shop Name: {shop_data.get('name', 'Unknown')}")
            print_info(f"Shop Owner: {shop_data.get('shop_owner', 'Unknown')}")
            print_info(f"Domain: {shop_data.get('domain', 'Unknown')}")
            print_info(f"Plan: {shop_data.get('plan_name', 'Unknown')}")
        elif response.status_code == 401:
            print_error("Authentication failed (401 Unauthorized)")
            print_info("Your access token may be invalid or expired")
            return False
        elif response.status_code == 404:
            print_error(f"Shop not found (404): {clean_shop_url}")
            print_info("Check that the shop URL is correct")
            return False
        else:
            print_error(f"Unexpected response ({response.status_code})")
            print_info(f"Response: {response.text[:200]}")
            return False

    except requests.exceptions.Timeout:
        print_error("Connection timeout")
        print_info("Check your internet connection")
        return False
    except requests.exceptions.RequestException as e:
        print_error(f"Connection failed: {e}")
        return False

    # Test 2: Products access
    try:
        print("\n  Testing products read access...")
        url = f"https://{clean_shop_url}/admin/api/{api_version}/products.json?limit=1"
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            products = response.json().get('products', [])
            print_success("Products read access: GRANTED")
            if products:
                print_info(f"Sample product found: {products[0].get('title', 'Unknown')}")
        elif response.status_code == 403:
            print_error("Products read access: DENIED")
            print_info("Add 'read_products' scope in Shopify app settings")
            return False
        else:
            print_warning(f"Products access test: Unexpected response ({response.status_code})")

    except Exception as e:
        print_warning(f"Products access test error: {e}")

    # Test 3: Orders access
    try:
        print("\n  Testing orders read access...")
        url = f"https://{clean_shop_url}/admin/api/{api_version}/orders.json?limit=1&status=any"
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            orders = response.json().get('orders', [])
            print_success("Orders read access: GRANTED")
            if orders:
                print_info(f"Sample order found: {orders[0].get('name', 'Unknown')}")
        elif response.status_code == 403:
            print_error("Orders read access: DENIED")
            print_info("Add 'read_orders' scope in Shopify app settings")
            return False
        else:
            print_warning(f"Orders access test: Unexpected response ({response.status_code})")

    except Exception as e:
        print_warning(f"Orders access test error: {e}")

    # Test 4: Inventory access (optional)
    try:
        print("\n  Testing inventory read access...")
        url = f"https://{clean_shop_url}/admin/api/{api_version}/inventory_levels.json?limit=1"
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            print_success("Inventory read access: GRANTED")
        elif response.status_code == 403:
            print_warning("Inventory read access: DENIED")
            print_info("This is optional - needed only for inventory sync features")
        else:
            print_warning(f"Inventory access test: Unexpected response ({response.status_code})")

    except Exception as e:
        print_warning(f"Inventory access test error: {e}")

    print_success("\nShopify connection test: PASSED")
    return True

# ============================================================================
# MAIN FUNCTION
# ============================================================================

def main():
    """Main function to run connection tests."""
    parser = argparse.ArgumentParser(
        description='Test connections to Odoo and Shopify',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        '--odoo',
        action='store_true',
        help='Test only Odoo connection'
    )
    parser.add_argument(
        '--shopify',
        action='store_true',
        help='Test only Shopify connection'
    )
    args = parser.parse_args()

    # Determine what to test
    test_odoo = args.odoo or not args.shopify
    test_shopify = args.shopify or not args.odoo

    print_header("REMOTE CONNECTIONS CHECKER")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    results = {}

    # Test Odoo
    if test_odoo:
        results['Odoo'] = test_odoo_connection()

    # Test Shopify
    if test_shopify:
        results['Shopify'] = test_shopify_connection()

    # Print summary
    print_section("Summary")

    all_passed = all(results.values())

    for system, passed in results.items():
        if passed:
            print_success(f"{system}: PASSED")
        else:
            print_error(f"{system}: FAILED")

    print("\n" + "=" * 80)
    if all_passed:
        print(f"{Colors.GREEN}{Colors.BOLD}✓ ALL CONNECTION TESTS PASSED{Colors.END}")
        print("All remote systems are accessible and properly configured.")
    else:
        print(f"{Colors.RED}{Colors.BOLD}✗ SOME CONNECTION TESTS FAILED{Colors.END}")
        print("\nTroubleshooting steps:")
        print("  1. Verify credentials in odoosys.py and shopify_export_cred.py")
        print("  2. Check network connectivity to remote servers")
        print("  3. Ensure API tokens have required permissions")
        print("  4. Check firewall settings")
    print("=" * 80)

    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
