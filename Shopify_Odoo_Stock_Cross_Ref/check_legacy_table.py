#!/usr/bin/env python3
"""
Check if the legacy_lookup table exists in the materials.db database.
"""

import os
import sqlite3
import sys

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    materials_db = os.path.join(script_dir, '..', 'materials.db')
    
    if not os.path.exists(materials_db):
        print(f"Error: materials.db not found at {materials_db}")
        sys.exit(1)
    
    try:
        # Connect to the database
        conn = sqlite3.connect(materials_db)
        cursor = conn.cursor()
        
        # Check if the table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='legacy_lookup'")
        result = cursor.fetchone()
        
        if result:
            print("legacy_lookup table exists in the database")
            
            # Count rows
            cursor.execute("SELECT COUNT(*) FROM legacy_lookup")
            count = cursor.fetchone()[0]
            print(f"The table contains {count} rows")
            
            # Show sample data
            if count > 0:
                cursor.execute("SELECT * FROM legacy_lookup LIMIT 5")
                columns = [description[0] for description in cursor.description]
                print("\nSample data (first 5 rows):")
                print(", ".join(columns))
                for row in cursor.fetchall():
                    print(row)
        else:
            print("legacy_lookup table does NOT exist in the database")
        
        conn.close()
    except Exception as e:
        print(f"Error checking database: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()