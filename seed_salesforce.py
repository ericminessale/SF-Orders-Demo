"""
Seed the Salesforce Developer Edition org with realistic demo data
for the order management demo.

Creates: Accounts, Contacts, Products, PricebookEntries, Orders, OrderItems, Cases
"""

import random
from datetime import datetime, timedelta
from salesforce_client import get_salesforce_client


def main():
    print("Connecting to Salesforce...")
    sf = get_salesforce_client()

    # Get Standard Pricebook
    pb_result = sf.query("SELECT Id FROM Pricebook2 WHERE IsStandard = true LIMIT 1")
    if not pb_result["records"]:
        print("ERROR: No Standard Pricebook found. Enable it in Setup > Price Books.")
        return
    pricebook_id = pb_result["records"][0]["Id"]

    # Check if pricebook is active
    pb_detail = sf.query(f"SELECT IsActive FROM Pricebook2 WHERE Id = '{pricebook_id}'")
    if not pb_detail["records"][0]["IsActive"]:
        print("ERROR: Standard Pricebook is inactive. Activate it first.")
        print("  → App Launcher > Price Books > Standard Price Book > Edit > Active = checked")
        return

    # --- Accounts ---
    print("\nCreating accounts...")
    accounts_data = [
        {"Name": "Acme Corporation", "Phone": "5551001000", "Industry": "Technology",
         "BillingStreet": "100 Innovation Dr", "BillingCity": "San Francisco", "BillingStateCode": "CA", "BillingPostalCode": "94105", "BillingCountryCode": "US"},
        {"Name": "Globex Industries", "Phone": "5551002000", "Industry": "Manufacturing",
         "BillingStreet": "250 Industrial Blvd", "BillingCity": "Austin", "BillingStateCode": "TX", "BillingPostalCode": "73301", "BillingCountryCode": "US"},
        {"Name": "Initech Solutions", "Phone": "5551003000", "Industry": "Consulting",
         "BillingStreet": "500 Business Park Way", "BillingCity": "Chicago", "BillingStateCode": "IL", "BillingPostalCode": "60601", "BillingCountryCode": "US"},
        {"Name": "Wayne Enterprises", "Phone": "5551004000", "Industry": "Finance",
         "BillingStreet": "1 Gotham Plaza", "BillingCity": "New York", "BillingStateCode": "NY", "BillingPostalCode": "10001", "BillingCountryCode": "US"},
        {"Name": "Stark Solutions", "Phone": "5551005000", "Industry": "Technology",
         "BillingStreet": "200 Malibu Point", "BillingCity": "Malibu", "BillingStateCode": "CA", "BillingPostalCode": "90265", "BillingCountryCode": "US"},
    ]

    account_ids = []
    for acct in accounts_data:
        # Check if account already exists
        existing = sf.query(f"SELECT Id FROM Account WHERE Name = '{acct['Name']}' LIMIT 1")
        if existing["records"]:
            account_ids.append(existing["records"][0]["Id"])
            print(f"  [exists] {acct['Name']}")
        else:
            result = sf.Account.create(acct)
            account_ids.append(result["id"])
            print(f"  [created] {acct['Name']}")

    # --- Contacts ---
    print("\nCreating contacts...")
    contacts_data = [
        {"FirstName": "John", "LastName": "Smith", "Email": "john.smith@acme.com", "Phone": "5551001001", "AccountIdx": 0},
        {"FirstName": "Sarah", "LastName": "Johnson", "Email": "sarah.j@globex.com", "Phone": "5551002001", "AccountIdx": 1},
        {"FirstName": "Mike", "LastName": "Williams", "Email": "mike.w@initech.com", "Phone": "5551003001", "AccountIdx": 2},
        {"FirstName": "Diana", "LastName": "Prince", "Email": "diana.p@wayne.com", "Phone": "5551004001", "AccountIdx": 3},
        {"FirstName": "Tony", "LastName": "Parker", "Email": "tony.p@stark.com", "Phone": "5551005001", "AccountIdx": 4},
    ]

    for contact in contacts_data:
        acct_idx = contact.pop("AccountIdx")
        contact["AccountId"] = account_ids[acct_idx]
        existing = sf.query(f"SELECT Id FROM Contact WHERE Email = '{contact['Email']}' LIMIT 1")
        if existing["records"]:
            print(f"  [exists] {contact['FirstName']} {contact['LastName']}")
        else:
            sf.Contact.create(contact)
            print(f"  [created] {contact['FirstName']} {contact['LastName']}")

    # --- Products ---
    print("\nCreating products...")
    products_data = [
        {"Name": "Enterprise Server License", "ProductCode": "ENT-SRV-001", "Description": "Annual enterprise server license", "IsActive": True, "Price": 4999.00},
        {"Name": "Cloud Storage - 1TB", "ProductCode": "CLD-STR-001", "Description": "1TB cloud storage annual plan", "IsActive": True, "Price": 1200.00},
        {"Name": "API Gateway Pro", "ProductCode": "API-GW-001", "Description": "API gateway with 10M requests/month", "IsActive": True, "Price": 2499.00},
        {"Name": "Security Suite Premium", "ProductCode": "SEC-STE-001", "Description": "Advanced security and compliance suite", "IsActive": True, "Price": 3499.00},
        {"Name": "Analytics Dashboard", "ProductCode": "ANL-DSH-001", "Description": "Real-time analytics and reporting", "IsActive": True, "Price": 899.00},
        {"Name": "Support Plan - Gold", "ProductCode": "SUP-GLD-001", "Description": "24/7 support with 1-hour SLA", "IsActive": True, "Price": 1999.00},
        {"Name": "DevOps Toolkit", "ProductCode": "DEV-TK-001", "Description": "CI/CD pipeline and monitoring", "IsActive": True, "Price": 1599.00},
        {"Name": "Data Migration Service", "ProductCode": "DAT-MIG-001", "Description": "One-time data migration package", "IsActive": True, "Price": 7500.00},
        {"Name": "Training Package - 10 seats", "ProductCode": "TRN-PKG-001", "Description": "10-seat training and certification", "IsActive": True, "Price": 2999.00},
        {"Name": "Custom Integration Setup", "ProductCode": "CUS-INT-001", "Description": "Custom API integration development", "IsActive": True, "Price": 12000.00},
    ]

    product_ids = []
    product_prices = {}
    for prod in products_data:
        price = prod.pop("Price")
        existing = sf.query(f"SELECT Id FROM Product2 WHERE ProductCode = '{prod['ProductCode']}' LIMIT 1")
        if existing["records"]:
            pid = existing["records"][0]["Id"]
            product_ids.append(pid)
            product_prices[pid] = price
            print(f"  [exists] {prod['Name']}")
        else:
            result = sf.Product2.create(prod)
            pid = result["id"]
            product_ids.append(pid)
            product_prices[pid] = price
            print(f"  [created] {prod['Name']}")

    # --- Pricebook Entries ---
    print("\nCreating pricebook entries...")
    for pid in product_ids:
        price = product_prices[pid]
        existing = sf.query(
            f"SELECT Id FROM PricebookEntry WHERE Product2Id = '{pid}' AND Pricebook2Id = '{pricebook_id}' LIMIT 1"
        )
        if existing["records"]:
            print(f"  [exists] PBE for product {pid[:8]}...")
        else:
            sf.PricebookEntry.create({
                "Pricebook2Id": pricebook_id,
                "Product2Id": pid,
                "UnitPrice": price,
                "IsActive": True,
            })
            print(f"  [created] PBE for product {pid[:8]}... @ ${price}")

    # --- Orders ---
    print("\nCreating orders...")
    statuses = ["Draft", "Activated"]
    descriptions = [
        "Annual license renewal",
        "New infrastructure setup",
        "Security compliance upgrade",
        "Q2 expansion order",
        "Emergency capacity increase",
        "Platform migration package",
        "New department onboarding",
        "Disaster recovery setup",
    ]

    # Get pricebook entries for order items
    pbe_result = sf.query(f"""
        SELECT Id, Product2Id, UnitPrice
        FROM PricebookEntry
        WHERE Pricebook2Id = '{pricebook_id}' AND IsActive = true
    """)
    pbe_list = pbe_result["records"]

    order_ids = []
    for i in range(15):
        acct_idx = i % len(account_ids)
        account_id = account_ids[acct_idx]
        days_ago = random.randint(1, 90)
        effective_date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        status = statuses[i % 2]
        desc = descriptions[i % len(descriptions)]

        try:
            order_result = sf.Order.create({
                "AccountId": account_id,
                "Pricebook2Id": pricebook_id,
                "EffectiveDate": effective_date,
                "Status": "Draft",
                "Description": desc,
                "ShippingStreet": accounts_data[acct_idx]["BillingStreet"],
                "ShippingCity": accounts_data[acct_idx]["BillingCity"],
                "ShippingStateCode": accounts_data[acct_idx]["BillingStateCode"],
                "ShippingPostalCode": accounts_data[acct_idx]["BillingPostalCode"],
                "ShippingCountryCode": "US",
            })
            order_id = order_result["id"]
            order_ids.append((order_id, status))

            # Add 1-3 line items
            num_items = random.randint(1, 3)
            selected_pbes = random.sample(pbe_list, min(num_items, len(pbe_list)))
            for pbe in selected_pbes:
                qty = random.randint(1, 5)
                sf.OrderItem.create({
                    "OrderId": order_id,
                    "PricebookEntryId": pbe["Id"],
                    "Quantity": qty,
                    "UnitPrice": pbe["UnitPrice"],
                })

            # Activate if needed
            if status == "Activated":
                try:
                    sf.Order.update(order_id, {"Status": "Activated"})
                except Exception:
                    pass  # Some orders may not be activatable

            # Get order number for display
            order_detail = sf.query(f"SELECT OrderNumber FROM Order WHERE Id = '{order_id}' LIMIT 1")
            order_num = order_detail["records"][0]["OrderNumber"] if order_detail["records"] else "?"
            print(f"  [created] Order #{order_num} - {desc} ({status})")

        except Exception as e:
            print(f"  [error] Order {i+1}: {e}")

    # --- Cases ---
    print("\nCreating cases...")
    cases_data = [
        {"Subject": "Order not received - 2 weeks overdue", "Priority": "High",
         "Description": "Customer reports order placed 2 weeks ago has not arrived. Tracking shows delivered but customer denies receipt."},
        {"Subject": "Wrong items shipped", "Priority": "High",
         "Description": "Customer received Enterprise Server License instead of Cloud Storage. Requesting exchange."},
        {"Subject": "Request for bulk discount", "Priority": "Medium",
         "Description": "Customer interested in ordering 50+ licenses and asking about volume pricing."},
        {"Subject": "Invoice discrepancy", "Priority": "Medium",
         "Description": "Invoice amount doesn't match agreed pricing. Customer expects $4,999 but was charged $5,499."},
        {"Subject": "Cancel order - changed requirements", "Priority": "Low",
         "Description": "Customer's project scope changed and they no longer need the Data Migration Service."},
        {"Subject": "Delivery address change request", "Priority": "Medium",
         "Description": "Customer relocated office. Needs shipping address updated on pending order."},
        {"Subject": "Product compatibility question", "Priority": "Low",
         "Description": "Customer asking if API Gateway Pro is compatible with their existing Security Suite."},
        {"Subject": "Urgent: Production system down", "Priority": "High",
         "Description": "Customer's production environment is experiencing outages. Support Plan Gold customer expecting immediate response."},
    ]

    for i, case in enumerate(cases_data):
        acct_idx = i % len(account_ids)
        case["AccountId"] = account_ids[acct_idx]
        case["Status"] = "New"
        case["Origin"] = "Phone"
        try:
            result = sf.Case.create(case)
            case_detail = sf.query(f"SELECT CaseNumber FROM Case WHERE Id = '{result['id']}' LIMIT 1")
            case_num = case_detail["records"][0]["CaseNumber"] if case_detail["records"] else "?"
            print(f"  [created] Case #{case_num} - {case['Subject'][:50]}...")
        except Exception as e:
            print(f"  [error] Case: {e}")

    print("\n" + "=" * 50)
    print("Seeding complete!")
    print(f"  Accounts: {len(account_ids)}")
    print(f"  Contacts: {len(contacts_data)}")
    print(f"  Products: {len(products_data)}")
    print(f"  Orders: {len(order_ids)}")
    print(f"  Cases: {len(cases_data)}")
    print("=" * 50)


if __name__ == "__main__":
    main()
