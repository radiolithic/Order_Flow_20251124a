#!/bin/bash

# Check if Python is available
if ! command -v python &> /dev/null; then
    echo "Python is not found in your PATH. Please ensure Python is installed."
    read -p "Press Enter to exit..."
    exit 1
fi

# Check if materials.db exists and create it if it doesn't
if [ ! -f "materials.db" ]; then
    echo "Creating materials database..."
    python create_materials_db.py
fi

# Run the menu
python materials_menu.py
