import xmlrpc.client
import importlib.util
import sys

def load_config(filepath):
    """Loads Odoo connection details from a Python file."""
    spec = importlib.util.spec_from_file_location("config_module", filepath)
    if spec is None or spec.loader is None:
        print(f"Error: Could not load spec for {filepath}")
        return None
    config_module = importlib.util.module_from_spec(spec)
    sys.modules["config_module"] = config_module # Add to sys.modules temporarily
    try:
        spec.loader.exec_module(config_module)
        # Clean up from sys.modules after loading
        del sys.modules["config_module"]
        return config_module
    except FileNotFoundError:
        print(f"Error: Configuration file not found at {filepath}")
        return None
    except Exception as e:
        print(f"Error loading configuration from {filepath}: {e}")
        # Clean up from sys.modules in case of error during exec_module
        if "config_module" in sys.modules:
            del sys.modules["config_module"]
        return None


def test_odoo_connection(name, config):
    """Tests the connection to an Odoo server."""
    if not config:
        print(f"Skipping connection test for {name} due to config loading error.")
        return

    print(f"--- Testing connection for {name} ({config.systemname}) ---")
    print(f"URL: {config.url}")
    print(f"DB: {config.db}")
    print(f"User: {config.username}")

    try:
        # 1. Connect to common endpoint to authenticate
        common = xmlrpc.client.ServerProxy(f'{config.url}/xmlrpc/2/common')
        version_info = common.version()
        print(f"Connected to common endpoint. Odoo Version Info: {version_info}")

        uid = common.authenticate(config.db, config.username, config.password, {})
        if not uid:
            print(f"Authentication failed for user '{config.username}' on database '{config.db}'. Check credentials.")
            print(f"--- Connection test for {name} FAILED ---")
            return

        print(f"Authentication successful. UID: {uid}")

        # 2. Connect to object endpoint to execute methods (optional check)
        models = xmlrpc.client.ServerProxy(f'{config.url}/xmlrpc/2/object')
        # Example: Check access rights for a common model like res.partner
        can_read = models.execute_kw(config.db, uid, config.password,
                                     'res.partner', 'check_access_rights',
                                     ['read'], {'raise_exception': False})
        if can_read:
            print("Successfully executed a test method (check_access_rights for res.partner).")
        else:
            print("Executed test method, but user might lack read access to res.partner (this is not necessarily an error).")

        print(f"--- Connection test for {name} SUCCEEDED ---")

    except xmlrpc.client.Fault as e:
        print(f"XML-RPC Fault: {e.faultCode} - {e.faultString}")
        print(f"--- Connection test for {name} FAILED ---")
    except ConnectionRefusedError:
        print(f"Connection Refused: Could not connect to {config.url}. Is the server running and accessible?")
        print(f"--- Connection test for {name} FAILED ---")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        print(f"--- Connection test for {name} FAILED ---")
    print("") # Add a newline for separation

# --- Main Execution ---
if __name__ == "__main__":
    print("Loading source server configuration (odoosys.py)...")
    source_config = load_config('odoosys.py')

    print("\nLoading target server configuration (odoosys2.py)...")
    target_config = load_config('odoosys2.py')

    print("\nStarting connection tests...\n")

    if source_config:
        test_odoo_connection("Source Server", source_config)
    else:
        print("Could not load source configuration. Skipping test.")

    if target_config:
        test_odoo_connection("Target Server", target_config)
    else:
        print("Could not load target configuration. Skipping test.")

    print("--- All tests finished ---")