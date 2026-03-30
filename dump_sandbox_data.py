"""Dump all seeded Salesforce data to a JSON file for reference."""

import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "signalwire-agents-python"))
from dotenv import load_dotenv
load_dotenv()
from salesforce_client import get_salesforce_client

sf = get_salesforce_client()
print("Connected to Salesforce. Dumping data...")

data = {}

# Accounts
result = sf.query("SELECT Id, Name, Phone, Industry, BillingCity, BillingState FROM Account ORDER BY Name")
data["accounts"] = result["records"]
print(f"  Accounts: {len(data['accounts'])}")

# Contacts
result = sf.query("SELECT Id, FirstName, LastName, Email, Phone, Account.Name FROM Contact ORDER BY LastName")
data["contacts"] = result["records"]
print(f"  Contacts: {len(data['contacts'])}")

# Products
result = sf.query("SELECT Id, Name, ProductCode, Description, Family FROM Product2 ORDER BY Name")
data["products"] = result["records"]
print(f"  Products: {len(data['products'])}")

# Orders with line items
result = sf.query("""
    SELECT Id, OrderNumber, Status, TotalAmount, EffectiveDate, Description,
           Account.Name, ShippingCity, ShippingState
    FROM Order ORDER BY OrderNumber
""")
data["orders"] = result["records"]
print(f"  Orders: {len(data['orders'])}")

# Order items
result = sf.query("""
    SELECT Id, OrderId, Order.OrderNumber, Product2.Name, Quantity, UnitPrice, TotalPrice
    FROM OrderItem ORDER BY Order.OrderNumber
""")
data["order_items"] = result["records"]
print(f"  Order Items: {len(data['order_items'])}")

# Cases
result = sf.query("SELECT Id, CaseNumber, Subject, Status, Priority, Account.Name FROM Case ORDER BY CaseNumber")
data["cases"] = result["records"]
print(f"  Cases: {len(data['cases'])}")

# Clean out Salesforce metadata from all records
def clean(obj):
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items() if k != "attributes"}
    if isinstance(obj, list):
        return [clean(i) for i in obj]
    return obj

data = clean(data)

with open("sandbox_data.json", "w") as f:
    json.dump(data, f, indent=2)

print(f"\nSaved to sandbox_data.json")
