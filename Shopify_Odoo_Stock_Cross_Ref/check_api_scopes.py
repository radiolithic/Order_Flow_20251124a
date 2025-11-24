#!/usr/bin/env python3
"""
Shopify API Scopes Checker

This script queries the Shopify API to determine exactly what scopes (permissions)
are granted to your custom app's access token. This helps identify permission
differences between multiple Shopify stores.

Usage:
    python check_api_scopes.py                    # Check default credentials
    python check_api_scopes.py -f creds.py       # Check alternative credentials
"""

import sys
import os
import argparse
import importlib.util
import requests
import json

# Add parent directory to path to import credentials
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def load_credentials_from_file(credential_file):
    """Dynamically load credentials from a Python file."""
    if not os.path.isabs(credential_file):
        # Try relative to parent directory first
        parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        abs_path = os.path.join(parent_dir, credential_file)
        if os.path.exists(abs_path):
            credential_file = abs_path
        else:
            # Try relative to current directory
            credential_file = os.path.abspath(credential_file)

    if not os.path.exists(credential_file):
        print(f"Error: Credential file not found: {credential_file}")
        sys.exit(1)

    spec = importlib.util.spec_from_file_location("shopify_creds", credential_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return {
        'shop_url': getattr(module, 'clean_shop_url', None),
        'access_token': getattr(module, 'access_token', None),
        'db_name': getattr(module, 'db_name', None)
    }

def print_section(title):
    """Print a formatted section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)

def check_api_version(shop_url, access_token):
    """Check what API version is being used."""
    print_section("API Version Information")

    # Try to get shop info which includes the API version
    api_version = '2024-04'  # Default
    url = f"https://{shop_url}/admin/api/{api_version}/shop.json"
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json"
    }

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        print(f"✓ Using API version: {api_version}")
        shop_data = response.json().get('shop', {})
        print(f"  Shop: {shop_data.get('name')}")
        print(f"  Plan: {shop_data.get('plan_name')}")
        return api_version
    else:
        print(f"✗ Could not determine API version")
        return api_version

def check_rest_api_scopes(shop_url, access_token, api_version):
    """Test various REST API endpoints to infer permissions."""
    print_section("REST API Endpoint Tests")

    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json"
    }

    tests = [
        {
            'name': 'Products (read_products)',
            'url': f"https://{shop_url}/admin/api/{api_version}/products.json?limit=1",
            'scope': 'read_products'
        },
        {
            'name': 'Inventory Levels (read_inventory)',
            'url': f"https://{shop_url}/admin/api/{api_version}/inventory_levels.json?limit=1",
            'scope': 'read_inventory'
        },
        {
            'name': 'Locations (read_locations)',
            'url': f"https://{shop_url}/admin/api/{api_version}/locations.json",
            'scope': 'read_locations'
        },
        {
            'name': 'Orders (read_orders)',
            'url': f"https://{shop_url}/admin/api/{api_version}/orders.json?limit=1&status=any",
            'scope': 'read_orders'
        }
    ]

    results = {}
    for test in tests:
        response = requests.get(test['url'], headers=headers)
        if response.status_code == 200:
            print(f"✓ {test['name']}: GRANTED")
            results[test['scope']] = True
        elif response.status_code == 403:
            print(f"✗ {test['name']}: DENIED (403 Forbidden)")
            results[test['scope']] = False
        else:
            print(f"? {test['name']}: UNKNOWN (Status {response.status_code})")
            results[test['scope']] = None

    return results

def check_graphql_introspection(shop_url, access_token, api_version):
    """Use GraphQL introspection to check what queries are available."""
    print_section("GraphQL API Introspection")

    url = f"https://{shop_url}/admin/api/{api_version}/graphql.json"
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json"
    }

    # Simple query to test GraphQL access
    query = """
    {
      shop {
        name
        plan {
          displayName
        }
      }
    }
    """

    response = requests.post(url, json={'query': query}, headers=headers)

    if response.status_code == 200:
        data = response.json()
        if 'errors' in data:
            print(f"✗ GraphQL API: ERROR")
            print(f"  Errors: {data['errors']}")
            return False
        else:
            print(f"✓ GraphQL API: ACCESSIBLE")
            shop_data = data.get('data', {}).get('shop', {})
            if shop_data:
                print(f"  Shop: {shop_data.get('name')}")
                plan = shop_data.get('plan', {})
                if plan:
                    print(f"  Plan: {plan.get('displayName')}")
            return True
    else:
        print(f"✗ GraphQL API: HTTP {response.status_code}")
        return False

def test_bulk_operation_start(shop_url, access_token, api_version):
    """Test if we can START a bulk operation (doesn't wait for completion)."""
    print_section("Bulk Operations Test (START only)")

    url = f"https://{shop_url}/admin/api/{api_version}/graphql.json"
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json"
    }

    # Simplified bulk operation query (just products, no inventory)
    mutation = """
    mutation {
      bulkOperationRunQuery(
       query: \"\"\"
        {
          products(first: 10) {
            edges {
              node {
                id
                title
              }
            }
          }
        }
        \"\"\"
      ) {
        bulkOperation {
          id
          status
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    print("Attempting to start a simple bulk operation...")
    response = requests.post(url, json={'query': mutation}, headers=headers)

    if response.status_code != 200:
        print(f"✗ HTTP Error: {response.status_code}")
        print(f"  Response: {response.text}")
        return False

    data = response.json()

    if 'errors' in data:
        print(f"✗ GraphQL Errors:")
        for error in data['errors']:
            print(f"  - {error.get('message')}")
        return False

    bulk_op = data.get('data', {}).get('bulkOperationRunQuery', {})
    user_errors = bulk_op.get('userErrors', [])

    if user_errors:
        print(f"✗ User Errors:")
        for error in user_errors:
            print(f"  - {error.get('message')} (field: {error.get('field')})")
        return False

    operation = bulk_op.get('bulkOperation', {})
    if operation:
        op_id = operation.get('id')
        status = operation.get('status')
        print(f"✓ Bulk operation started successfully!")
        print(f"  Operation ID: {op_id}")
        print(f"  Initial Status: {status}")

        # Now poll once to see if it immediately fails
        print("\nPolling operation status once...")
        query = """
        query {
          node(id: "%s") {
            ... on BulkOperation {
              id
              status
              errorCode
              objectCount
            }
          }
        }
        """ % op_id

        import time
        time.sleep(2)  # Give it a moment

        poll_response = requests.post(url, json={'query': query}, headers=headers)
        if poll_response.status_code == 200:
            poll_data = poll_response.json().get('data', {}).get('node', {})
            poll_status = poll_data.get('status')
            error_code = poll_data.get('errorCode')

            print(f"  Current Status: {poll_status}")
            if error_code:
                print(f"  ✗ Error Code: {error_code}")
                if error_code == 'ACCESS_DENIED':
                    print("\n  This means the bulk operation API requires additional permissions")
                    print("  that are not granted to this access token, even though basic")
                    print("  GraphQL queries work.")
                return False
            else:
                print(f"  ✓ No errors detected (operation {poll_status})")
                return True
        else:
            print(f"  ? Could not poll status (HTTP {poll_response.status_code})")
            return None
    else:
        print(f"✗ No bulk operation returned in response")
        return False

def test_inventory_bulk_operation(shop_url, access_token, api_version):
    """Test the specific bulk operation used in the actual script."""
    print_section("Full Inventory Bulk Operation Test")

    url = f"https://{shop_url}/admin/api/{api_version}/graphql.json"
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json"
    }

    # This is the ACTUAL query from get_shopify_data_current.py
    mutation = """
    mutation {
      bulkOperationRunQuery(
       query: \"\"\"
        {
          products {
            edges {
              node {
                id
                title
                handle
                status
                variants {
                  edges {
                    node {
                      id
                      sku
                      title
                      inventoryQuantity
                      inventoryItem {
                        id
                        tracked
                        inventoryLevels {
                          edges {
                            node {
                              id
                              quantities(names: ["available", "on_hand", "committed", "incoming"]) {
                                name
                                quantity
                              }
                              location {
                                id
                                name
                              }
                            }
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
        \"\"\"
      ) {
        bulkOperation {
          id
          status
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    print("Starting the EXACT bulk operation from get_shopify_data_current.py...")
    response = requests.post(url, json={'query': mutation}, headers=headers)

    if response.status_code != 200:
        print(f"✗ HTTP Error: {response.status_code}")
        print(f"  Response: {response.text}")
        return False

    data = response.json()

    if 'errors' in data:
        print(f"✗ GraphQL Errors:")
        for error in data['errors']:
            print(f"  - {error.get('message')}")
        return False

    bulk_op = data.get('data', {}).get('bulkOperationRunQuery', {})
    user_errors = bulk_op.get('userErrors', [])

    if user_errors:
        print(f"✗ User Errors:")
        for error in user_errors:
            print(f"  - {error.get('message')} (field: {error.get('field')})")
        return False

    operation = bulk_op.get('bulkOperation', {})
    if operation:
        op_id = operation.get('id')
        status = operation.get('status')
        print(f"✓ Full inventory bulk operation started!")
        print(f"  Operation ID: {op_id}")
        print(f"  Initial Status: {status}")

        # Poll once
        print("\nPolling operation status...")
        query = """
        query {
          node(id: "%s") {
            ... on BulkOperation {
              id
              status
              errorCode
              objectCount
            }
          }
        }
        """ % op_id

        import time
        time.sleep(2)

        poll_response = requests.post(url, json={'query': query}, headers=headers)
        if poll_response.status_code == 200:
            poll_data = poll_response.json().get('data', {}).get('node', {})
            poll_status = poll_data.get('status')
            error_code = poll_data.get('errorCode')

            print(f"  Current Status: {poll_status}")
            if error_code:
                print(f"  ✗ Error Code: {error_code}")
                if error_code == 'ACCESS_DENIED':
                    print("\n  DIAGNOSIS: The inventory bulk query requires read_inventory scope")
                    print("  but your access token does not have this permission.")
                    print("\n  FIX:")
                    print("  1. Go to Shopify Admin > Settings > Apps and sales channels")
                    print("  2. Select your custom app")
                    print("  3. Go to Configuration > Admin API access scopes")
                    print("  4. Enable: read_inventory")
                    print("  5. Save and reinstall the app")
                return False
            else:
                print(f"  ✓ No errors! Operation is proceeding ({poll_status})")
                if poll_status == 'COMPLETED':
                    print(f"  Objects found: {poll_data.get('objectCount', 'unknown')}")
                return True

    return None

def main():
    parser = argparse.ArgumentParser(
        description='Check Shopify API scopes and permissions in detail',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python check_api_scopes.py                          # Check default credentials
  python check_api_scopes.py -f ../woodlanders_shopify_cred.py
  python check_api_scopes.py -f ../nucar_shopify_cred.py
        """
    )
    parser.add_argument(
        '-f', '--file',
        dest='credential_file',
        default=None,
        help='Path to alternative credential file (default: shopify_export_cred.py)'
    )

    args = parser.parse_args()

    # Determine credential file
    if args.credential_file:
        credential_file = args.credential_file
    else:
        parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        credential_file = os.path.join(parent_dir, 'shopify_export_cred.py')

    print("=" * 80)
    print("  SHOPIFY API SCOPES DETAILED CHECKER")
    print("=" * 80)

    # Load credentials
    print_section("Loading Credentials")
    print(f"Credential file: {credential_file}")

    try:
        creds = load_credentials_from_file(credential_file)
    except Exception as e:
        print(f"\n✗ Error loading credentials: {e}")
        sys.exit(1)

    shop_url = creds['shop_url']
    access_token = creds['access_token']

    print(f"✓ Loaded credentials")
    print(f"  Shop: {shop_url}")
    print(f"  Token: {access_token[:15]}...")

    # Run tests
    api_version = check_api_version(shop_url, access_token)
    rest_results = check_rest_api_scopes(shop_url, access_token, api_version)
    graphql_ok = check_graphql_introspection(shop_url, access_token, api_version)

    if graphql_ok:
        bulk_simple = test_bulk_operation_start(shop_url, access_token, api_version)
        bulk_inventory = test_inventory_bulk_operation(shop_url, access_token, api_version)
    else:
        print("\nSkipping bulk operation tests (GraphQL not accessible)")
        bulk_simple = False
        bulk_inventory = False

    # Summary
    print_section("Summary")
    print("\nREST API Scopes:")
    for scope, granted in rest_results.items():
        status = "✓ GRANTED" if granted else "✗ DENIED" if granted is False else "? UNKNOWN"
        print(f"  {scope:20s} {status}")

    print("\nGraphQL API:")
    print(f"  Basic Access:        {'✓ YES' if graphql_ok else '✗ NO'}")
    print(f"  Bulk Ops (Simple):   {'✓ YES' if bulk_simple else '✗ NO' if bulk_simple is False else '? UNKNOWN'}")
    print(f"  Bulk Ops (Inventory): {'✓ YES' if bulk_inventory else '✗ NO' if bulk_inventory is False else '? UNKNOWN'}")

    print("\n" + "=" * 80)

    if bulk_inventory:
        print("✓ ALL TESTS PASSED - This credential can run full inventory sync")
    elif bulk_simple and not bulk_inventory:
        print("⚠ PARTIAL ACCESS - Bulk operations work but inventory queries fail")
        print("  You need to add 'read_inventory' scope to your Shopify custom app")
    elif graphql_ok and not bulk_simple:
        print("⚠ LIMITED ACCESS - GraphQL works but bulk operations denied")
        print("  Your Shopify plan or app configuration may not support bulk operations")
    else:
        print("✗ INSUFFICIENT ACCESS - Basic GraphQL queries fail")
        print("  Check your access token and app permissions")

    print("=" * 80)

if __name__ == "__main__":
    main()
