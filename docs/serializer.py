"""
CSV to JSON Serializer Utility

This module provides a utility function to convert CSV files to JSON format.
It includes an example usage that demonstrates how to create a sample CSV file
and convert it to JSON for demonstration or testing purposes.
"""

import csv
import json

def csv_to_json(csv_file_path, json_file_path):
    """
    Converts a CSV file to a JSON file.

    Args:
        csv_file_path (str): The path to the input CSV file.
        json_file_path (str): The path to the output JSON file.
    """
    data = []
    with open(csv_file_path, mode='r', encoding='utf-8') as csv_file:
        # Use DictReader to read each row as a dictionary where keys are CSV headers
        csv_reader = csv.DictReader(csv_file)
        for row in csv_reader:
            data.append(row)

    with open(json_file_path, mode='w', encoding='utf-8') as json_file:
        # Write the list of dictionaries to the JSON file
        # indent=4 for pretty-printing the JSON output
        json.dump(data, json_file, indent=4)

# Example usage:
# Create a dummy CSV file for demonstration
with open('input.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['Name', 'Age', 'City'])
    writer.writerow(['John', '28', 'New York'])
    writer.writerow(['Alice', '24', 'Los Angeles'])

# Convert the CSV to JSON
csv_to_json('input.csv', 'output.json')

print("CSV file successfully converted to JSON.")
