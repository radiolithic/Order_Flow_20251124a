# Proposed .gitignore File for Shopify Queries Project

Below is a recommended `.gitignore` file for this project. This will ensure that generated files, sensitive information, and environment-specific files are not committed to version control.

```
# Generated output files
*.xlsx
*.csv
!plant_sizes.csv  # Keep this specific CSV file in version control
stock_cross_reference_*.xlsx
inventory_mismatch_report_*.xlsx
shopify_items_at_zero_stock_*.xlsx
odoostock.xlsx
shopifyproducts.xlsx

# Database files
*.db
*.sqlite
*.sqlite3
woodlanders.db

# Python-specific files
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
*.egg-info/
.installed.cfg
*.egg

# Sensitive information
odoosys.py  # Contains database credentials
shopify_export_cred.py  # Contains API credentials
*_cred.py
*_config.json
!shopify_export_config.json  # Keep this specific config file in version control

# Temporary files
*.tmp
*.temp
*.log
*.bak
.DS_Store
Thumbs.db

# IDE-specific files
.idea/
.vscode/
*.swp
*.swo
*~

# Virtual environment
venv/
ENV/

# Odoo module specific (for future integration)
woodlanders_reports/scripts/external/

# Temporary directories that might be created by the scripts
temp/
tmp/
```

## Notes on Usage

1. **CSV Files**: By default, all CSV files are ignored except for `plant_sizes.csv`, which should be kept in version control as it contains reference data.

2. **Configuration Files**: Most configuration files are ignored to prevent committing sensitive information, but `shopify_export_config.json` is kept as it contains non-sensitive field mappings.

3. **External Scripts**: When integrating with the Odoo module, the external scripts directory is ignored as these will be copies of the original scripts.

4. **Database Files**: All database files are ignored as they should be generated locally and not shared through version control.

To use this `.gitignore` file:

1. Create a file named `.gitignore` in the root of your project
2. Copy the content above into the file
3. Commit the `.gitignore` file to your repository

This will ensure that only the essential source code and configuration files are tracked, while generated outputs and sensitive information remain private.