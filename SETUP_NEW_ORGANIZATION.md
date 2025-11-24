# Setting Up the System for a New Organization

This guide explains how to configure the Shopify-Odoo integration system for a new organization.

## Prerequisites

- Python 3.x installed
- Access to your organization's Shopify Admin
- Access to your organization's Odoo instance
- Git (optional, for version control)

## Step 1: Clone or Copy the Repository

If you're using Git:
```bash
git clone <repository-url>
cd order_flow_01
```

Otherwise, simply copy the entire `order_flow_01` directory to your location (e.g., Google Drive).

## Step 2: Configure Odoo Credentials

1. Copy the example file: `cp odoosys_example.py odoosys.py` (or manually create it)
2. Edit `odoosys.py` and fill in your organization's values:

```python
# Odoo server details
url = "http://your-odoo-server:port"
db = 'your_database_name'
user = 'your-email@example.com'
username = 'your-email@example.com'
password = 'your_odoo_password'
systemname = 'Your Organization Name'  # Used in system banners and reports
```

**Important:**
- Never commit this file to version control. It's already in `.gitignore`.
- The `systemname` field will appear in system banners (e.g., "YOUR ORGANIZATION NAME INVENTORY SYNC")

## Step 3: Configure Shopify Credentials

### 3.1 Create a Shopify Custom App

1. Log in to your Shopify Admin
2. Go to **Settings → Apps and sales channels**
3. Click **Develop apps** → **Create an app**
4. Give it a name (e.g., "Odoo Integration")
5. Click **Configure Admin API scopes**
6. Enable the following scopes:
   - `read_products`
   - `read_inventory`
   - `write_inventory` (if you need to update inventory from Odoo)
7. Click **Save**
8. Click **Install app**
9. Copy the **Admin API access token** (starts with `shpat_`)

### 3.2 Create Credentials File

1. Create a file named `shopify_export_cred.py` in the root directory
2. Use this template:

```python
# Shopify Store Credentials
shop_url = "https://your-store-name.myshopify.com"
access_token = 'shpat_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
clean_shop_url = 'your-store-name.myshopify.com'
db_name = "your_org_name.db"
```

**Important:** Never commit this file to version control. It's already in `.gitignore`.

## Step 4: Install Python Dependencies

```bash
pip install pandas xmlrpc openpyxl requests sqlite3
```

## Step 5: Initial Database Setup

Run the menu system:
```bash
python materials_menu.py
```

Or on Windows, double-click `RUN_MENU.bat`

## Step 6: Test the Integration

### Test Odoo Connection
From the menu, try option 2 (Run Order Flow) or option 4 (Generate Pull Sheet) to verify Odoo connectivity.

### Test Shopify Connection
From the menu, try option 3 (Stock Cross Reference) to test the Shopify API connection.

## Troubleshooting

### Shopify API Fails with "FAILED" Status

If the Shopify bulk operation fails, it could be due to:

1. **Insufficient API Permissions**
   - Verify your custom app has `read_products` and `read_inventory` scopes
   - Reinstall the app if you added scopes after initial installation

2. **Shopify Plan Limitations**
   - Bulk operations require a Shopify plan that supports GraphQL Admin API
   - Consider using manual CSV export as a workaround (see below)

3. **API Version Compatibility**
   - The script uses API version `2024-04`
   - Check if your Shopify store supports this version
   - Update `api_version` in `get_shopify_data_current.py` if needed

### Workaround: Manual CSV Export

If the API method fails:

1. In Shopify Admin, go to **Products → Inventory**
2. Click **Export** → Select "Current page" or "All inventory"
3. Choose CSV format
4. Save the file as `inventory_export_latest.csv`
5. Place it in `shared-data/input/` directory
6. Run the Stock Cross Reference again - it will use the CSV file

### Odoo Connection Issues

1. Verify the Odoo server URL is accessible from your machine
2. Check that the database name is correct
3. Verify the username and password
4. Ensure your Odoo user has the necessary permissions

### Path Issues on Windows (Google Drive)

If you get errors about file paths with spaces:
- Ensure you're using the latest version of the scripts
- The `main.py` files have been updated to handle paths with spaces correctly

## Directory Structure

```
order_flow_01/
├── odoosys.py                    # Your Odoo credentials (not in git)
├── shopify_export_cred.py        # Your Shopify credentials (not in git)
├── materials_menu.py             # Main menu system
├── process_shopify_exports.py   # Order processing script
├── create_pullsheet.py           # Pull sheet generator
├── shared-data/
│   ├── input/                    # Place CSV exports here
│   └── sqlite/                   # Database files
├── Order_Flow/
│   └── output/                   # Order flow reports
└── Shopify_Odoo_Stock_Cross_Ref/
    ├── get_shopify_data_current.py
    ├── get_odoo_stock_current.py
    └── output/                   # Stock cross-reference reports
```

## Security Best Practices

1. **Never commit credentials** - They're already in `.gitignore`
2. **Use environment variables** - For production deployments, consider using environment variables instead of credential files
3. **Rotate tokens regularly** - Regenerate Shopify access tokens periodically
4. **Limit permissions** - Only grant the minimum required API scopes
5. **Backup your data** - Regularly backup the SQLite databases

## Getting Help

If you encounter issues:

1. Check the error messages in the console output
2. Review this troubleshooting guide
3. Verify your credentials are correct
4. Check that all required Python packages are installed
5. Ensure network connectivity to both Shopify and Odoo

## Notes for Multi-Organization Deployments

If you're managing multiple organizations:

1. Create separate directories for each organization
2. Each directory should have its own `odoosys.py` and `shopify_export_cred.py`
3. Keep the code files synchronized across organizations
4. Use version control (Git) for the code, but exclude credentials
5. Consider using a configuration management system for credentials
