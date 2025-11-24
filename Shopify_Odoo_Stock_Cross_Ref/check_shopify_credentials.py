#!/usr/bin/env python3
"""
Shopify Credentials Checker

This utility tests your Shopify API credentials and permissions.
It performs several checks to help diagnose connection issues.

Usage:
    python check_shopify_credentials.py                        # Use default shopify_export_cred.py
    python check_shopify_credentials.py -f alt_creds.py        # Use alternative credential file
    python check_shopify_credentials.py --file store2_cred.py  # Long form
"""

import sys
import os
import requests
import argparse
import importlib.util

# Add parent directory to path to import credentials
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def print_section(title):
    """Print a formatted section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)

def load_credentials_from_file(credential_file):
    """Load credentials from a specified Python file."""
    # Get absolute path
    if not os.path.isabs(credential_file):
        # Try relative to current directory first
        if os.path.exists(credential_file):
            credential_file = os.path.abspath(credential_file)
        else:
            # Try relative to parent directory (default location)
            parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            credential_file = os.path.join(parent_dir, credential_file)

    if not os.path.exists(credential_file):
        raise FileNotFoundError(f"Credential file not found: {credential_file}")

    # Load the module dynamically
    spec = importlib.util.spec_from_file_location("shopify_creds", credential_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module

def check_credential_file(credential_file=None):
    """Check if the credential file exists and can be imported."""
    print_section("Checking Credential File")

    if credential_file is None:
        credential_file = "shopify_export_cred.py"

    print(f"Loading credentials from: {credential_file}")

    try:
        creds = load_credentials_from_file(credential_file)

        # Extract required attributes
        access_token = getattr(creds, 'access_token', None)
        clean_shop_url = getattr(creds, 'clean_shop_url', None)
        db_name = getattr(creds, 'db_name', 'N/A')

        if not access_token or not clean_shop_url:
            print("✗ ERROR: Missing required credentials")
            print("  Required: access_token, clean_shop_url")
            return None, None

        print(f"✓ Credential file loaded successfully")
        print(f"  File: {os.path.basename(credential_file)}")
        print(f"  Shop URL: {clean_shop_url}")
        print(f"  Token: {access_token[:15]}..." if len(access_token) > 15 else "  Token: [too short]")
        print(f"  Database: {db_name}")
        return access_token, clean_shop_url

    except FileNotFoundError as e:
        print(f"✗ ERROR: {e}")
        print(f"\nPlease ensure the file exists at: {credential_file}")
        return None, None
    except Exception as e:
        print(f"✗ ERROR: Could not load credential file")
        print(f"  {e}")
        print("\nPlease create a credential file with:")
        print("  - access_token = 'your_token'")
        print("  - clean_shop_url = 'your-store.myshopify.com'")
        print("  - db_name = 'your_db.db'")
        return None, None

def test_basic_connection(access_token, shop_url):
    """Test basic connection to Shopify API."""
    print_section("Testing Basic API Connection")

    api_version = '2024-04'
    url = f"https://{shop_url}/admin/api/{api_version}/shop.json"
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            shop_data = response.json().get('shop', {})
            print("✓ Successfully connected to Shopify API")
            print(f"  Shop Name: {shop_data.get('name', 'Unknown')}")
            print(f"  Shop Owner: {shop_data.get('shop_owner', 'Unknown')}")
            print(f"  Email: {shop_data.get('email', 'Unknown')}")
            print(f"  Domain: {shop_data.get('domain', 'Unknown')}")
            print(f"  Plan: {shop_data.get('plan_name', 'Unknown')}")
            return True
        elif response.status_code == 401:
            print("✗ ERROR: Authentication failed (401 Unauthorized)")
            print("  - Your access token may be invalid or expired")
            print("  - Verify the token in your Shopify admin")
            return False
        elif response.status_code == 404:
            print("✗ ERROR: Shop not found (404)")
            print(f"  - Check that '{shop_url}' is correct")
            print("  - It should be: your-store-name.myshopify.com")
            return False
        else:
            print(f"✗ ERROR: Unexpected response ({response.status_code})")
            print(f"  Response: {response.text[:200]}")
            return False

    except requests.exceptions.Timeout:
        print("✗ ERROR: Connection timeout")
        print("  - Check your internet connection")
        print(f"  - Verify '{shop_url}' is accessible")
        return False
    except requests.exceptions.RequestException as e:
        print(f"✗ ERROR: Connection failed: {e}")
        return False

def test_products_access(access_token, shop_url):
    """Test if the token has products read access."""
    print_section("Testing Products Read Access")

    api_version = '2024-04'
    url = f"https://{shop_url}/admin/api/{api_version}/products.json?limit=1"
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            products = response.json().get('products', [])
            print("✓ Products read access: GRANTED")
            print(f"  Found {len(products)} product(s) in test query")
            return True
        elif response.status_code == 403:
            print("✗ Products read access: DENIED")
            print("  - Your access token lacks 'read_products' scope")
            print("  - Add this scope in your Shopify custom app settings")
            return False
        else:
            print(f"✗ Unexpected response ({response.status_code})")
            print(f"  Response: {response.text[:200]}")
            return False

    except requests.exceptions.RequestException as e:
        print(f"✗ ERROR: {e}")
        return False

def test_inventory_access(access_token, shop_url):
    """Test if the token has inventory read access."""
    print_section("Testing Inventory Read Access")

    api_version = '2024-04'
    url = f"https://{shop_url}/admin/api/{api_version}/inventory_levels.json?limit=1"
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            print("✓ Inventory read access: GRANTED")
            return True
        elif response.status_code == 403:
            print("✗ Inventory read access: DENIED")
            print("  - Your access token lacks 'read_inventory' scope")
            print("  - Add this scope in your Shopify custom app settings")
            return False
        else:
            print(f"✗ Unexpected response ({response.status_code})")
            print(f"  Response: {response.text[:200]}")
            return False

    except requests.exceptions.RequestException as e:
        print(f"✗ ERROR: {e}")
        return False

def test_bulk_operations(access_token, shop_url):
    """Test if bulk operations are supported."""
    print_section("Testing Bulk Operations Support")

    api_version = '2024-04'
    url = f"https://{shop_url}/admin/api/{api_version}/graphql.json"
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json"
    }

    # Simple test query to check GraphQL access
    query = """
    {
        shop {
            name
        }
    }
    """

    try:
        response = requests.post(url, json={'query': query}, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            if 'errors' in data:
                print("✗ GraphQL access: ERROR")
                print(f"  Errors: {data['errors']}")
                return False
            else:
                print("✓ GraphQL API access: GRANTED")
                print("  Note: Bulk operations may still require specific plan or permissions")
                return True
        elif response.status_code == 403:
            print("✗ GraphQL access: DENIED")
            print("  - Your access token may not support GraphQL API")
            return False
        else:
            print(f"✗ Unexpected response ({response.status_code})")
            print(f"  Response: {response.text[:200]}")
            return False

    except requests.exceptions.RequestException as e:
        print(f"✗ ERROR: {e}")
        return False

def print_summary(results):
    """Print a summary of all tests."""
    print_section("Summary")

    all_passed = all(results.values())

    print("\nTest Results:")
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {test_name}")

    print("\n" + "=" * 80)
    if all_passed:
        print("  ✓ ALL TESTS PASSED")
        print("  Your Shopify credentials are properly configured!")
    else:
        print("  ✗ SOME TESTS FAILED")
        print("\nNext Steps:")
        print("  1. Go to Shopify Admin > Settings > Apps and sales channels")
        print("  2. Select your custom app")
        print("  3. Click 'Configuration'")
        print("  4. Under 'Admin API access scopes', ensure these are enabled:")
        print("     - read_products")
        print("     - read_inventory")
        print("  5. Click 'Save'")
        print("  6. Reinstall the app (this applies the new scopes)")
        print("  7. If needed, regenerate your access token")
        print("  8. Update shopify_export_cred.py with the new token")
        print("\n  Note: If bulk operations still fail, use the manual CSV export workaround")
    print("=" * 80)

def main():
    """Main function to run all credential checks."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Test Shopify API credentials and permissions',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                           # Use default shopify_export_cred.py
  %(prog)s -f store2_cred.py         # Test alternative credential file
  %(prog)s --file ../my_creds.py     # Use file with relative path
  %(prog)s -f /full/path/creds.py    # Use file with absolute path
        """
    )
    parser.add_argument(
        '-f', '--file',
        dest='credential_file',
        default=None,
        help='Path to alternative credential file (default: shopify_export_cred.py)'
    )
    args = parser.parse_args()

    print("\n" + "=" * 80)
    print("  SHOPIFY CREDENTIALS CHECKER")
    print("=" * 80)

    results = {}

    # Step 1: Check credential file
    access_token, shop_url = check_credential_file(args.credential_file)
    if not access_token or not shop_url:
        print("\n✗ Cannot proceed without valid credentials")
        return 1

    # Step 2: Test basic connection
    results['Basic Connection'] = test_basic_connection(access_token, shop_url)
    if not results['Basic Connection']:
        print("\n✗ Cannot proceed without basic connection")
        print_summary(results)
        return 1

    # Step 3: Test products access
    results['Products Read Access'] = test_products_access(access_token, shop_url)

    # Step 4: Test inventory access
    results['Inventory Read Access'] = test_inventory_access(access_token, shop_url)

    # Step 5: Test bulk operations
    results['GraphQL/Bulk Operations'] = test_bulk_operations(access_token, shop_url)

    # Print summary
    print_summary(results)

    return 0 if all(results.values()) else 1

if __name__ == "__main__":
    sys.exit(main())
