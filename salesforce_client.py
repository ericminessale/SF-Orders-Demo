"""
Salesforce client module for the order management demo.
Handles OAuth authentication and CRUD operations against the Salesforce REST API.
"""

import os
import requests
from simple_salesforce import Salesforce
from dotenv import load_dotenv

load_dotenv()


def get_salesforce_client() -> Salesforce:
    """Authenticate via Client Credentials Flow and return a Salesforce client."""
    client_id = os.getenv("SALESFORCE_CLIENT_ID")
    client_secret = os.getenv("SALESFORCE_CLIENT_SECRET")
    instance_url = os.getenv("SALESFORCE_INSTANCE_URL")

    if not all([client_id, client_secret, instance_url]):
        raise ValueError("Missing SALESFORCE_CLIENT_ID, SALESFORCE_CLIENT_SECRET, or SALESFORCE_INSTANCE_URL in .env")

    # Request token via Client Credentials Flow
    token_url = f"{instance_url}/services/oauth2/token"
    resp = requests.post(token_url, data={
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    })

    if resp.status_code != 200:
        raise Exception(f"OAuth failed ({resp.status_code}): {resp.text}")

    token_data = resp.json()
    access_token = token_data["access_token"]
    # Use the instance_url from the token response (canonical)
    canonical_url = token_data.get("instance_url", instance_url)

    return Salesforce(instance_url=canonical_url, session_id=access_token)


# --- Query helpers ---

def lookup_account_by_phone(sf: Salesforce, phone: str) -> dict | None:
    """Find an account by phone number. Normalizes E.164 and other formats."""
    # Strip +1 prefix and any non-digit characters for matching
    digits = ''.join(c for c in phone if c.isdigit())
    if digits.startswith('1') and len(digits) == 11:
        digits = digits[1:]  # Remove country code
    result = sf.query(f"SELECT Id, Name, Phone, BillingAddress, AccountNumber FROM Account WHERE Phone = '{digits}' LIMIT 1")
    return result["records"][0] if result["records"] else None


def lookup_account_by_name(sf: Salesforce, name: str) -> dict | None:
    """Find an account by name (partial match)."""
    result = sf.query(f"SELECT Id, Name, Phone, BillingAddress, AccountNumber FROM Account WHERE Name LIKE '%{name}%' LIMIT 1")
    return result["records"][0] if result["records"] else None


def get_orders_for_account(sf: Salesforce, account_id: str) -> list:
    """Get all orders for an account with their line items."""
    orders = sf.query(f"""
        SELECT Id, OrderNumber, Status, TotalAmount, EffectiveDate,
               ShippingAddress, Description
        FROM Order
        WHERE AccountId = '{account_id}'
        ORDER BY EffectiveDate DESC
        LIMIT 10
    """)
    return orders["records"]


def get_order_by_number(sf: Salesforce, order_number: str) -> dict | None:
    """Look up a specific order by its order number."""
    result = sf.query(f"""
        SELECT Id, OrderNumber, Status, TotalAmount, EffectiveDate,
               ShippingAddress, Description,
               Account.Name, Account.Phone
        FROM Order
        WHERE OrderNumber = '{order_number}'
        LIMIT 1
    """)
    return result["records"][0] if result["records"] else None


def get_order_items(sf: Salesforce, order_id: str) -> list:
    """Get line items for an order."""
    items = sf.query(f"""
        SELECT Id, OrderItemNumber, Quantity, UnitPrice, TotalPrice,
               Product2.Name, Product2.ProductCode
        FROM OrderItem
        WHERE OrderId = '{order_id}'
    """)
    return items["records"]


def update_order_status(sf: Salesforce, order_id: str, new_status: str) -> bool:
    """Update the status of an order."""
    try:
        sf.Order.update(order_id, {"Status": new_status})
        return True
    except Exception as e:
        print(f"Error updating order status: {e}")
        return False


US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire",
    "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee",
    "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}


def update_order_shipping_address(sf: Salesforce, order_id: str, street: str, city: str, state: str, postal_code: str) -> bool:
    """Update the shipping address on an order. Normalizes state codes to full names for Salesforce picklists."""
    try:
        # Salesforce State & Country picklists require full state name and country
        state_full = US_STATES.get(state.upper(), state) if len(state) == 2 else state
        sf.Order.update(order_id, {
            "ShippingStreet": street,
            "ShippingCity": city,
            "ShippingState": state_full,
            "ShippingPostalCode": postal_code,
            "ShippingCountry": "United States",
        })
        return True
    except Exception as e:
        print(f"Error updating shipping address: {e}")
        return False


def create_case(sf: Salesforce, account_id: str, subject: str, description: str, order_id: str = None) -> str:
    """Create a support case linked to an account and optionally an order."""
    case_data = {
        "AccountId": account_id,
        "Subject": subject,
        "Description": description,
        "Status": "New",
        "Priority": "Medium",
        "Origin": "Phone",
    }
    result = sf.Case.create(case_data)
    return result["id"]


def get_cases_for_account(sf: Salesforce, account_id: str) -> list:
    """Get open cases for an account."""
    cases = sf.query(f"""
        SELECT Id, CaseNumber, Subject, Status, Priority, Description, CreatedDate
        FROM Case
        WHERE AccountId = '{account_id}' AND IsClosed = false
        ORDER BY CreatedDate DESC
        LIMIT 5
    """)
    return cases["records"]


def add_case_comment(sf: Salesforce, case_id: str, comment: str) -> bool:
    """Add a comment to a case (post-call summary)."""
    try:
        sf.CaseComment.create({
            "ParentId": case_id,
            "CommentBody": comment,
            "IsPublished": False,
        })
        return True
    except Exception as e:
        print(f"Error adding case comment: {e}")
        return False


def create_task(sf: Salesforce, account_id: str, subject: str, description: str) -> str:
    """Create a follow-up task linked to an account."""
    task_data = {
        "WhatId": account_id,
        "Subject": subject,
        "Description": description,
        "Status": "Not Started",
        "Priority": "Normal",
        "ActivityDate": None,  # No due date
    }
    result = sf.Task.create(task_data)
    return result["id"]
