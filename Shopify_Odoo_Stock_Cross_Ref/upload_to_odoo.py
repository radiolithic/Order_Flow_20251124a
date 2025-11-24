import xmlrpc.client
import argparse
import sys
import os
import base64
import sys
import os

# Add parent directory to path to import from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from odoosys import url, db, username, password

def upload_report(package_name, file_path):
    """
    Reads a file, encodes it as base64, and calls the create_from_analytics method in Odoo.
    """
    try:
        # Read and encode the file
        with open(file_path, 'rb') as f:
            file_content = f.read()
        file_content_b64 = base64.b64encode(file_content).decode('utf-8')
        
        # Extract the base filename from the path
        file_name = os.path.basename(file_path)

        # Connect to Odoo
        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        uid = common.authenticate(db, username, password, {})
        models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')

        print(f"Connected to Odoo as user ID {uid}.")
        print(f"Calling 'create_from_analytics' for package '{package_name}', file '{file_name}'...")

        # Call the custom method with three arguments
        result = models.execute_kw(
            db, uid, password,
            'report.file', 'create_from_analytics',
            [package_name, file_name, file_content_b64]
        )

        print(f"Odoo API response: {result}")

        if result.get('status') == 'success':
            print("Report successfully uploaded to Odoo.")
            return True
        else:
            print(f"Error uploading report to Odoo: {result.get('message')}")
            return False

    except FileNotFoundError:
        print(f"Error: The file was not found at path: {file_path}")
        return False
    except xmlrpc.client.Fault as e:
        if "report.file" in str(e) and "doesn't exist" in str(e):
            print(f"Note: Report upload skipped - 'report.file' module not installed in this Odoo instance")
            print(f"      The report was saved locally to: {file_path}")
            print(f"      This is optional - the script completed successfully")
            return True  # Return True since this is not a critical error
        else:
            print(f"Odoo XML-RPC error: {e}")
            return False
    except Exception as e:
        print(f"An unexpected error occurred during XML-RPC call: {e}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload a generated report to Odoo by passing its content.")
    parser.add_argument("package_name", help="The name of the package that generated the report.")
    parser.add_argument("file_path", help="The full path to the file to upload.")
    
    args = parser.parse_args()

    success = upload_report(args.package_name, args.file_path)
    
    if not success:
        sys.exit(1)