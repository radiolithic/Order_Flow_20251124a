# Analytics Script Development Guidelines

This document provides guidelines and best practices for developing scripts within the analytics container. Adhering to these standards will ensure that our scripts are secure, reliable, and easy to maintain.

## 1. Credential Management

Proper credential management is critical to protect our systems. The following practices are mandatory for all scripts that require access to external services like Odoo or Shopify.

### 1.1. Centralized Credentials

All credentials (API keys, usernames, passwords) **must** be stored in a central, secure location. For this project, the `odoosys.py` file in each script's directory serves as the temporary central store for Odoo credentials.

**DO NOT** hardcode credentials directly into your scripts.

**Example:**

```python
# odoosys.py
url = "http://odoo:8069"
db = "wd250721d1"
username = "admin"
password = "password"
```

### 1.2. Secure Loading

Credentials should be loaded into your scripts by importing them from the central `odoosys.py` file.

**Example:**

```python
# your_script.py
from odoosys import url, db, username, password

# Now you can use these variables to connect to Odoo
common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
uid = common.authenticate(db, username, password, {})
```

### 1.3. Environment Variables (Future)

For enhanced security, we will be transitioning to a system where credentials are provided as environment variables to the container. This will be the standard for all future scripts and will be retrofitted to existing ones.

## 2. Script Reliability

To ensure our scripts are reliable and produce consistent results, please follow these guidelines.

### 2.1. File Hand-off via API

When a script needs to hand off a file (e.g., a report) to Odoo, it **must** do so by passing the file's content directly through the API. This method is more robust than relying on shared file volumes, which can be a source of errors.

The `report_manager` addon in Odoo is designed to accept file content as a base64-encoded string.

**The standard process is:**

1.  The script generates the file and saves it to a local `output` directory.
2.  The script reads the generated file's content.
3.  The content is encoded in base64.
4.  The encoded content is passed to the `report.file` model's `create_from_analytics` method in Odoo.

### 2.2. Use the `upload_to_odoo.py` Wrapper

A wrapper script, `upload_to_odoo.py`, is provided to handle the API communication. This script reads the file, encodes it, and calls the Odoo API with the correct arguments.

**Usage:**

```python
# your_script.py
from upload_to_odoo import upload_report

# ... generate your report ...
report_path = os.path.join(OUTPUT_DIR, 'my_report.xlsx')
df.to_excel(report_path, index=False)

# Upload the report to Odoo
upload_report('YourPackageName', report_path)
```

### 2.3. Correct API Call Format

The `create_from_analytics` method in the `report.file` model expects **three separate arguments**:

1. `package_name`: The name of the package/module that generated the report
2. `file_name`: The name of the file
3. `file_content_b64`: The base64-encoded content of the file

**CORRECT example:**

```python
# Correct way to call the API
result = models.execute_kw(
    db, uid, password,
    'report.file', 'create_from_analytics',
    [package_name, file_name, file_content_b64]  # Three separate arguments
)
```

**INCORRECT example:**

```python
# Incorrect way - passing a dictionary instead of three separate arguments
report_data = {
    'name': file_name,
    'package_name': package_name,
    'report_data': file_content_b64,
}
result = models.execute_kw(
    db, uid, password,
    'report.file', 'create_from_analytics',
    [report_data]  # Wrong! This is a dictionary
)
```

### 2.4. Error Handling

All scripts should include robust error handling, especially around API calls and file operations. Use `try...except` blocks to catch potential exceptions and provide clear, informative error messages.

**Example:**

```python
try:
    # Code that might raise an exception
    result = api.call()
except Exception as e:
    print(f"An error occurred: {e}")
    sys.exit(1)
```

## 3. Script Structure

For consistency and maintainability, all scripts should follow a similar structure.

### 3.1. Directory Structure

Each script or related set of scripts should be contained within its own directory inside `analytics/scripts`. This directory should include:

-   `main.py`: The main entry point for the script.
-   `odoosys.py`: Odoo connection credentials.
-   `upload_to_odoo.py`: The API upload wrapper.
-   `output/`: A directory to store any generated files.

### 3.2. Path Management

Use the `os` module to construct absolute paths. This ensures that your scripts will run correctly regardless of the directory from which they are called.

**Example:**

```python
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'output')

os.makedirs(OUTPUT_DIR, exist_ok=True)
```

By following these guidelines, we can build a library of analytics scripts that are secure, reliable, and easy to manage.