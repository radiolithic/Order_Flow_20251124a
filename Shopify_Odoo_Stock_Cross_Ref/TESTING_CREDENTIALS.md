# Testing Shopify Credentials

This guide explains how to use the credential checker to test multiple Shopify configurations.

## Basic Usage

Test the default credential file (`shopify_export_cred.py`):
```bash
python check_shopify_credentials.py
```

## Testing Alternative Credential Files

If you manage multiple Shopify stores or want to test different configurations:

### 1. Create Alternative Credential Files

```bash
# Copy the example template
cp shopify_cred_store2_example.py shopify_cred_store2.py

# Edit with your store's credentials
nano shopify_cred_store2.py
```

### 2. Test the Alternative Credentials

```bash
# Test store 2 credentials
python check_shopify_credentials.py -f shopify_cred_store2.py

# Or use the long form
python check_shopify_credentials.py --file shopify_cred_store2.py
```

### 3. Use Relative or Absolute Paths

```bash
# Relative path from current directory
python check_shopify_credentials.py -f ../shopify_export_cred.py

# Absolute path
python check_shopify_credentials.py -f /full/path/to/creds.py

# Parent directory (default location)
python check_shopify_credentials.py -f shopify_export_cred.py
```

## Multi-Store Setup Example

If you're managing multiple Shopify stores:

```
order_flow_01/
├── shopify_export_cred.py           # Store 1 (production)
├── shopify_cred_store2.py           # Store 2 (another brand)
├── shopify_cred_test.py             # Test/staging environment
└── Shopify_Odoo_Stock_Cross_Ref/
    └── check_shopify_credentials.py
```

Test each store:
```bash
cd Shopify_Odoo_Stock_Cross_Ref

# Test production store
python check_shopify_credentials.py

# Test store 2
python check_shopify_credentials.py -f ../shopify_cred_store2.py

# Test staging environment
python check_shopify_credentials.py -f ../shopify_cred_test.py
```

## What the Checker Tests

1. **Credential File** - Verifies the file exists and has required fields
2. **Basic Connection** - Tests authentication and displays shop info
3. **Products Access** - Verifies `read_products` scope
4. **Inventory Access** - Verifies `read_inventory` scope
5. **GraphQL/Bulk Operations** - Tests bulk operation support

## Example Output

```
================================================================================
  SHOPIFY CREDENTIALS CHECKER
================================================================================

================================================================================
  Checking Credential File
================================================================================
Loading credentials from: shopify_cred_store2.py
✓ Credential file loaded successfully
  File: shopify_cred_store2.py
  Shop URL: store2.myshopify.com
  Token: shpat_abc123456...
  Database: store2_shopify.db

================================================================================
  Testing Basic API Connection
================================================================================
✓ Successfully connected to Shopify API
  Shop Name: Store 2
  Shop Owner: John Doe
  Email: john@store2.com
  Domain: store2.myshopify.com
  Plan: Shopify Plus

================================================================================
  Testing Products Read Access
================================================================================
✓ Products read access: GRANTED
  Found 1 product(s) in test query

================================================================================
  Testing Inventory Read Access
================================================================================
✓ Inventory read access: GRANTED

================================================================================
  Testing Bulk Operations Support
================================================================================
✓ GraphQL API access: GRANTED
  Note: Bulk operations may still require specific plan or permissions

================================================================================
  Summary
================================================================================

Test Results:
  ✓ PASS: Basic Connection
  ✓ PASS: Products Read Access
  ✓ PASS: Inventory Read Access
  ✓ PASS: GraphQL/Bulk Operations

================================================================================
  ✓ ALL TESTS PASSED
  Your Shopify credentials are properly configured!
================================================================================
```

## Common Scenarios

### Scenario 1: Testing New Store Credentials

Before deploying to a new store:
```bash
# Create credential file
cp shopify_cred_store2_example.py shopify_cred_newstore.py
# Edit with new store's credentials
nano shopify_cred_newstore.py
# Test
python check_shopify_credentials.py -f ../shopify_cred_newstore.py
```

### Scenario 2: Comparing Production vs Test

```bash
# Test production
python check_shopify_credentials.py

# Test staging
python check_shopify_credentials.py -f ../shopify_cred_staging.py
```

### Scenario 3: Troubleshooting Permission Issues

When you get ACCESS_DENIED errors:
```bash
# Test current credentials
python check_shopify_credentials.py

# Fix permissions in Shopify Admin
# Regenerate token
# Update credential file
# Test again
python check_shopify_credentials.py
```

## Tips

- **Keep credential files organized** - Use descriptive names like `shopify_cred_[storename].py`
- **Never commit credentials** - All `*_cred.py` files (except examples) are in `.gitignore`
- **Document your stores** - Add comments in credential files about the store/environment
- **Test regularly** - Run checks after updating API permissions or regenerating tokens
- **Save test output** - Redirect output to a file for records: `python check_shopify_credentials.py > test_results.txt`

## Automation

You can use this in scripts to validate credentials before running operations:

```bash
#!/bin/bash
# deploy_to_store2.sh

echo "Testing Store 2 credentials..."
python check_shopify_credentials.py -f ../shopify_cred_store2.py

if [ $? -eq 0 ]; then
    echo "Credentials valid! Proceeding with deployment..."
    # Run your deployment scripts here
else
    echo "Credential check failed! Aborting."
    exit 1
fi
```

## Help

For more options:
```bash
python check_shopify_credentials.py --help
```
