#!/usr/bin/env python3
"""
Check the ACTUAL scopes granted to a Shopify access token.

This uses the access_scopes endpoint to see exactly what permissions
the token has, rather than inferring from API calls.
"""

import sys
import os
import argparse
import importlib.util
import requests

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def load_credentials_from_file(credential_file):
    """Dynamically load credentials from a Python file."""
    if not os.path.isabs(credential_file):
        parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        abs_path = os.path.join(parent_dir, credential_file)
        if os.path.exists(abs_path):
            credential_file = abs_path
        else:
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
    }

def get_access_scopes(shop_url, access_token):
    """Get the actual scopes granted to this access token."""
    api_version = '2024-04'
    url = f"https://{shop_url}/admin/oauth/access_scopes.json"
    headers = {
        "X-Shopify-Access-Token": access_token,
    }

    print("Querying Shopify for actual token scopes...")
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        scopes = data.get('access_scopes', [])
        return scopes
    else:
        print(f"Error getting scopes: HTTP {response.status_code}")
        print(f"Response: {response.text}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Check actual scopes of Shopify access token')
    parser.add_argument('-f', '--file', dest='credential_file',
                       help='Path to credential file')
    args = parser.parse_args()

    if args.credential_file:
        credential_file = args.credential_file
    else:
        parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        credential_file = os.path.join(parent_dir, 'shopify_export_cred.py')

    print("=" * 80)
    print("  SHOPIFY ACCESS TOKEN SCOPE CHECKER")
    print("=" * 80)
    print(f"\nCredential file: {credential_file}")

    creds = load_credentials_from_file(credential_file)
    shop_url = creds['shop_url']
    access_token = creds['access_token']

    print(f"Shop: {shop_url}")
    print(f"Token: {access_token[:15]}...")

    print("\n" + "=" * 80)
    scopes = get_access_scopes(shop_url, access_token)

    if scopes:
        print(f"\n✓ Found {len(scopes)} scope(s) granted to this token:\n")
        for scope_info in scopes:
            handle = scope_info.get('handle', 'unknown')
            print(f"  • {handle}")

        print("\n" + "=" * 80)
        print("SCOPE ANALYSIS:")
        print("=" * 80)

        scope_handles = [s.get('handle') for s in scopes]

        required_scopes = {
            'read_products': 'Required for product data',
            'read_inventory': 'Required for inventory levels and quantities',
            'read_locations': 'Required for location data in bulk operations'
        }

        print("\nRequired scopes for inventory sync:")
        for scope, purpose in required_scopes.items():
            if scope in scope_handles:
                print(f"  ✓ {scope:20s} - {purpose}")
            else:
                print(f"  ✗ {scope:20s} - {purpose} [MISSING]")

        missing = [s for s in required_scopes.keys() if s not in scope_handles]
        if missing:
            print(f"\n⚠ WARNING: Missing required scopes: {', '.join(missing)}")
            print("\nTo fix:")
            print("1. Go to Shopify Admin > Settings > Apps and sales channels")
            print("2. Select your custom app > Configuration")
            print("3. Add the missing scopes listed above")
            print("4. Save and reinstall the app")
            print("5. Update your credential file with the new access token")
        else:
            print("\n✓ All required scopes are granted!")

        print("=" * 80)
    else:
        print("\n✗ Could not retrieve scope information")
        print("\nThis might mean:")
        print("  - The access token is invalid")
        print("  - The /admin/oauth/access_scopes.json endpoint is not available")
        print("  - Network/connectivity issue")

if __name__ == "__main__":
    main()
