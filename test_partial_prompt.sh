#!/bin/bash

# Test script to demonstrate partial prompt fill functionality
# This script shows how to pre-fill part of the input when using the read command

echo "=== Partial Prompt Fill Demo ==="
echo "This demonstrates how to pre-fill part of the input when prompting for user input."
echo ""

# Example 1: Pre-filling an IP address
echo "Example 1: Pre-filling an IP address"
echo "-----------------------------------"
read -e -i "192.168.100." -p "Enter source IP address: " source_ip
echo "You entered: $source_ip"
echo ""

# Example 2: Pre-filling a file path
echo "Example 2: Pre-filling a file path"
echo "---------------------------------"
read -e -i "/home/user/" -p "Enter file path: " file_path
echo "You entered: $file_path"
echo ""

# Example 3: Pre-filling with a default value that can be edited
echo "Example 3: Pre-filling with a default value"
echo "------------------------------------------"
read -e -i "default_value" -p "Enter value (edit as needed): " user_value
echo "You entered: $user_value"
echo ""

echo "=== End of Demo ==="
echo ""
echo "Note: The '-e' flag enables readline editing, allowing you to use arrow keys to edit the pre-filled text."
echo "The '-i' flag sets the initial input text that can be edited by the user."