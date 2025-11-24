# Linux Usage Guide

## Quick Start

Launch the menu system:

```bash
./RUN_MENU.sh
```

## Menu Options

```
[1] Import Shopify Data
    Process Shopify exports and update the database

[2] Run Order Flow
    Synchronize and report on orders between Shopify and Odoo

[3] Stock Cross Reference
    Generate inventory reconciliation between Shopify and Odoo

[4] Generate Pull Sheet
    Create a pull sheet for fulfilling orders

[0] Exit
```

## Individual Scripts

You can also run the scripts directly:

```bash
./RUN_IMPORT.sh        # Import Shopify Data
./RUN_ORDER_FLOW.sh    # Run Order Flow
./RUN_STOCK_XREF.sh    # Stock Cross Reference
./RUN_PULL.sh          # Generate Pull Sheet
```

## First Time Setup

If scripts aren't executable:

```bash
chmod +x *.sh
```

## Notes

- The menu system automatically detects the OS and uses `.sh` files on Linux
- The same Python menu (`materials_menu.py`) works on both Windows and Linux
- All output files open automatically when generated
