@echo off
echo Cleaning up duplicate credential and database files...

REM Delete credential files from Order_Flow
if exist "Order_Flow\odoosys.py" (
    echo Deleting Order_Flow\odoosys.py
    del "Order_Flow\odoosys.py"
)

if exist "Order_Flow\shopify_export_cred.py" (
    echo Deleting Order_Flow\shopify_export_cred.py
    del "Order_Flow\shopify_export_cred.py"
)

REM Delete credential files from Shopify_Odoo_Stock_Cross_Ref
if exist "Shopify_Odoo_Stock_Cross_Ref\odoosys.py" (
    echo Deleting Shopify_Odoo_Stock_Cross_Ref\odoosys.py
    del "Shopify_Odoo_Stock_Cross_Ref\odoosys.py"
)

if exist "Shopify_Odoo_Stock_Cross_Ref\shopify_export_cred.py" (
    echo Deleting Shopify_Odoo_Stock_Cross_Ref\shopify_export_cred.py
    del "Shopify_Odoo_Stock_Cross_Ref\shopify_export_cred.py"
)

REM Delete database files from subdirectories
if exist "Order_Flow\order_sync.db" (
    echo Deleting Order_Flow\order_sync.db
    del "Order_Flow\order_sync.db"
)

if exist "Shopify_Odoo_Stock_Cross_Ref\woodlanders.db" (
    echo Deleting Shopify_Odoo_Stock_Cross_Ref\woodlanders.db
    del "Shopify_Odoo_Stock_Cross_Ref\woodlanders.db"
)

echo Cleanup completed.
pause