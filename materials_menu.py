#!/usr/bin/env python3
"""
Materials Management Menu System

This script provides a simple menu interface for running the various 
Materials management tasks for stock and orders across Shopify and Odoo.

Simply select an option from the menu to execute the corresponding task.
"""

import os
import sys
import subprocess
import time
from datetime import datetime

# ANSI color codes for terminal output (Windows-compatible empty strings)
class Colors:
    HEADER = ''
    BLUE = ''
    GREEN = ''
    YELLOW = ''
    RED = ''
    ENDC = ''
    BOLD = ''
    UNDERLINE = ''

# Get the directory containing this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def clear_screen():
    """Clear the terminal screen."""
    if os.name == 'nt':
        os.system('cls')
    else:
        os.system('clear')

def print_header():
    """Print the header for the menu."""
    clear_screen()
    print(f"{Colors.HEADER}{Colors.BOLD}{'=' * 80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'MATERIALS MANAGEMENT SYSTEM':^80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{datetime.now().strftime('%Y-%m-%d %H:%M:%S'):^80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'=' * 80}{Colors.ENDC}")
    print()

def run_script(script_name, description):
    """Run a script (.bat on Windows, .sh on Linux) and wait for it to complete."""
    print(f"\n{Colors.BLUE}Running: {description}...{Colors.ENDC}")
    print(f"{Colors.YELLOW}{'=' * 80}{Colors.ENDC}")

    # Determine script extension based on OS
    if os.name == 'nt':
        script_file = script_name + '.bat'
    else:
        script_file = script_name + '.sh'

    # Full path to the script file
    script_path = os.path.join(SCRIPT_DIR, script_file)

    exit_code = 0
    try:
        # Use subprocess.call so the output appears in the terminal
        if os.name == 'nt':
            # On Windows, shell=True is required for batch files
            exit_code = subprocess.call(script_path, shell=True)
        else:
            # On Linux, make executable and run with bash
            exit_code = subprocess.call(['bash', script_path])

        # Show appropriate completion message based on exit code
        if exit_code == 0:
            print(f"\n{Colors.GREEN}Completed: {description}{Colors.ENDC}")
        else:
            print(f"\n{Colors.YELLOW}Task ended with warnings or incomplete: {description}{Colors.ENDC}")
    except Exception as e:
        print(f"\n{Colors.RED}Error executing {script_file}: {e}{Colors.ENDC}")

    # Pause to let user see the results
    input(f"\n{Colors.YELLOW}Press Enter to return to the menu...{Colors.ENDC}")

def main_menu():
    """Display the main menu and handle user input."""
    while True:
        print_header()
        
        # Display menu options
        print(f"{Colors.BOLD}[1] {Colors.BLUE}Import Shopify Data{Colors.ENDC}")
        print(f"    Process Shopify exports and update the database")
        print()

        print(f"{Colors.BOLD}[2] {Colors.BLUE}View Failed Orders{Colors.ENDC}")
        print(f"    Review orders with unresolved SKU issues")
        print()

        print(f"{Colors.BOLD}[3] {Colors.BLUE}Run Order Flow{Colors.ENDC}")
        print(f"    Synchronize and report on orders between Shopify and Odoo")
        print()

        print(f"{Colors.BOLD}[4] {Colors.BLUE}Stock Cross Reference{Colors.ENDC}")
        print(f"    Generate inventory reconciliation between Shopify and Odoo")
        print()

        print(f"{Colors.BOLD}[5] {Colors.BLUE}Generate Pull Sheet{Colors.ENDC}")
        print(f"    Create pull sheet from Transfer (stock.picking).csv file")
        print()

        print(f"{Colors.BOLD}[6] {Colors.BLUE}Create import files from latest orders{Colors.ENDC}")
        print(f"    Fetch from Shopify API, view sync status, generate CSV files")
        print()

        print(f"{Colors.BOLD}[7] {Colors.BLUE}Import to Odoo (as Quotations){Colors.ENDC}")
        print(f"    Import CSV files to Odoo without auto-confirmation")
        print()

        print(f"{Colors.BOLD}[8] {Colors.BLUE}Import to Odoo (Confirm if in Stock){Colors.ENDC}")
        print(f"    Import CSV files and auto-confirm orders with all items available")
        print()

        print(f"{Colors.BOLD}[0] {Colors.RED}Exit{Colors.ENDC}")
        print()

        # Get user selection
        choice = input(f"{Colors.GREEN}Enter your choice (0-8): {Colors.ENDC}")
        
        if choice == '0':
            print(f"\n{Colors.YELLOW}Exiting Materials Management System. Goodbye!{Colors.ENDC}")
            break
        elif choice == '1':
            run_script("RUN_IMPORT", "Importing Shopify Data")
        elif choice == '2':
            # View failed orders file
            failed_orders_file = os.path.join(SCRIPT_DIR, 'failed_orders.txt')
            if os.path.exists(failed_orders_file):
                print(f"\n{Colors.BLUE}Viewing failed orders...{Colors.ENDC}")
                print(f"{Colors.YELLOW}{'=' * 80}{Colors.ENDC}")
                try:
                    subprocess.call(['less', failed_orders_file])
                except Exception as e:
                    # If less fails, just cat the file
                    print(f"\n{Colors.YELLOW}Could not open with 'less', displaying file:{Colors.ENDC}\n")
                    with open(failed_orders_file, 'r') as f:
                        print(f.read())
                input(f"\n{Colors.YELLOW}Press Enter to return to the menu...{Colors.ENDC}")
            else:
                print(f"\n{Colors.GREEN}No failed orders found. All orders processed successfully!{Colors.ENDC}")
                time.sleep(2)
        elif choice == '3':
            run_script("RUN_ORDER_FLOW", "Order Flow Process")
        elif choice == '4':
            run_script("RUN_STOCK_XREF", "Stock Cross Reference")
        elif choice == '5':
            run_script("RUN_PULL", "Generating Pull Sheet")
        elif choice == '6':
            run_script("RUN_LIVE_IMPORT", "Create import files from latest orders")
        elif choice == '7':
            run_script("RUN_IMPORT_TO_ODOO", "Import to Odoo (as Quotations)")
        elif choice == '8':
            run_script("RUN_IMPORT_TO_ODOO_CONFIRM", "Import to Odoo (Confirm if in Stock)")
        else:
            print(f"\n{Colors.RED}Invalid choice. Please try again.{Colors.ENDC}")
            time.sleep(1.5)

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Operation cancelled by user. Exiting...{Colors.ENDC}")
        sys.exit(0)
    except Exception as e:
        print(f"\n{Colors.RED}An unexpected error occurred: {e}{Colors.ENDC}")
        input("Press Enter to exit...")
        sys.exit(1)