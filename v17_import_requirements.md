# Odoo v17 Sales Order Import Requirements

## Overview
This document outlines the requirements for importing Sales Orders into Odoo v17, specifically for scenarios where the billing party differs from the end customer (e.g., marketplace orders like Shopify, Amazon, etc.).

## Key Differences from v15

In Odoo v15, you could set:
- **Customer** = Marketplace (e.g., "Shopify")
- **Delivery Address** = End Customer Name

In Odoo v17, this approach causes the delivery address to default back to the marketplace's address, losing the actual shipping destination.

## v17 Solution: Customer Addresses Feature

Odoo v17 uses a **Customer Addresses** feature that separates three distinct partner relationships:

1. **Customer** (`partner_id`) - The primary customer relationship
2. **Invoice Address** (`partner_invoice_id`) - The billing/payment party
3. **Delivery Address** (`partner_shipping_id`) - The shipping destination

## Configuration Requirements

### Step 1: Enable Customer Addresses Feature

Before importing, enable this feature in Odoo v17:

1. Go to **Accounting → Configuration → Settings**
2. Scroll to the **Customer Invoices** section
3. Enable **"Customer Addresses"**
4. Click **Save**

Once enabled, Sales Order forms will display separate fields for Invoice Address and Delivery Address.

## Import File Structure

### Contacts Import (`01_contacts_upload.csv`)

**No changes required** - continue using the same structure as v15:

```csv
Email,Name,Street,City,Zip,State,Country,Phone,Is a company,Address type
customer@email.com,Customer Name,123 Main St,City,12345,ST,US,,0,Contact
```

### Orders Import (`02_orders_upload.csv`)

**Modified structure** - add the Invoice Address column:

```csv
Order Reference,Customer,Invoice Address,Delivery Address,Order Date,OrderLines/Quantity,OrderLines/Price_unit,Order Lines/Product
#10840,Customer Name,Marketplace Name,Customer Name,2025-10-02 08:32:16,1,22.0,PRODUCT-SKU
```

## Field Mapping Principles

### For Marketplace Orders (Shopify, Amazon, etc.):

| Field | Value | Purpose | What Team Sees |
|-------|-------|---------|----------------|
| **Customer** | End customer name (e.g., "Susan Wynn") | Primary customer relationship | Sales team sees actual customer |
| **Invoice Address** | Marketplace name (e.g., "Shopify") | Billing/payment party | Accounting invoices marketplace |
| **Delivery Address** | End customer name (e.g., "Susan Wynn") | Shipping destination | Warehouse ships to customer |

### For Direct Orders (No Marketplace):

| Field | Value | Purpose |
|-------|-------|---------|
| **Customer** | Customer name | Primary customer relationship |
| **Invoice Address** | Customer name (or leave blank to default) | Billing party |
| **Delivery Address** | Customer name (or shipping address if different) | Shipping destination |

## Benefits of This Approach

1. **CRM & Analytics** - Customer relationship tracking shows the actual end customer, not the marketplace
2. **Sales Team Visibility** - Sales orders display the real customer name, making it clear who the order is for
3. **Accounting Accuracy** - Invoices are correctly directed to the payment party (marketplace)
4. **Shipping Clarity** - Warehouse sees the correct shipping destination
5. **Email Routing** - Quotations go to customers, invoices go to billing party

## Data Integrity Notes

### Prerequisites:
- **All contacts must exist** before importing orders
- Import contacts first (`01_contacts_upload.csv`), then orders (`02_orders_upload.csv`)
- The marketplace contact (e.g., "Shopify") must be pre-created with its invoice address

### Contact Name Matching:
- Field values must **exactly match** contact names in the system
- Case-sensitive matching
- Watch for extra spaces or punctuation differences

## Example Workflow

### 1. Prepare Marketplace Contact
Create a contact record for your marketplace:
- **Name**: Shopify
- **Address**: Marketplace's billing address
- **Type**: Company

### 2. Import Customer Contacts
Import all end customers from marketplace orders:
```csv
Email,Name,Street,City,Zip,State,Country,Phone,Is a company,Address type
customer1@email.com,Customer One,123 Main St,City,12345,ST,US,,0,Contact
customer2@email.com,Customer Two,456 Oak Ave,Town,67890,ST,US,,0,Contact
```

### 3. Import Orders with Proper Field Mapping
```csv
Order Reference,Customer,Invoice Address,Delivery Address,Order Date,OrderLines/Quantity,OrderLines/Price_unit,Order Lines/Product
#10001,Customer One,Shopify,Customer One,2025-10-01 10:00:00,2,25.0,PROD-001
#10002,Customer Two,Shopify,Customer Two,2025-10-02 14:30:00,1,50.0,PROD-002
```

## Troubleshooting

### Issue: Delivery address reverts to marketplace address
**Cause**: Customer Addresses feature not enabled
**Solution**: Enable in Accounting → Configuration → Settings → Customer Addresses

### Issue: "Customer not found" error during import
**Cause**: Contact doesn't exist in system yet
**Solution**: Import contacts before orders, ensure exact name matching

### Issue: Invoice goes to wrong party
**Cause**: Invoice Address field not properly set
**Solution**: Verify marketplace contact exists and is referenced in Invoice Address column

## Script Modifications Required

When updating your `ProcessShopifyExports.py` or similar scripts:

### Old Logic (v15):
```python
df['Customer'] = "Shopify"
df['Delivery Address'] = df['Shipping Name']
```

### New Logic (v17):
```python
df['Customer'] = df['Shipping Name']  # Use actual customer
df['Invoice Address'] = "Shopify"     # Marketplace for billing
df['Delivery Address'] = df['Shipping Name']  # Ship to customer
```

### Column Rename Dictionary:
```python
dict = {
    'Name': 'Order Reference',
    'Shipping Name': 'Customer',           # Changed!
    'Paid at': 'Order Date',
    'Lineitem quantity': 'OrderLines/Quantity',
    'Lineitem price': 'OrderLines/Price_unit',
    'Lineitem sku': 'Order Lines/Product'
}
```

Then manually add the Invoice Address column:
```python
df['Invoice Address'] = 'Shopify'
```

## Validation Checklist

Before going live with bulk imports:

- [ ] Customer Addresses feature enabled in Odoo v17
- [ ] Marketplace contact (e.g., Shopify) exists with proper billing address
- [ ] Test import with 1-2 sample orders
- [ ] Verify Customer field shows end customer name
- [ ] Verify Invoice Address shows marketplace name
- [ ] Verify Delivery Address shows end customer name
- [ ] Check that invoice email routing works correctly
- [ ] Confirm CRM reports show end customers, not marketplace

## Additional Resources

- Odoo v17 Documentation: Customer Addresses feature
- Forum: "How to invoice another partner than the customer"
- Related settings: Accounting → Configuration → Settings → Customer Invoices
