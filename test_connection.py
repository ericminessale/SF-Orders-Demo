"""
Test Salesforce connection and API access.
Run this after setting up your .env file to verify everything works.
"""

from salesforce_client import get_salesforce_client


def main():
    print("=" * 50)
    print("Salesforce Connection Test")
    print("=" * 50)

    # Step 1: Auth
    print("\n1. Requesting OAuth token...", end=" ")
    try:
        sf = get_salesforce_client()
        print("SUCCESS")
    except Exception as e:
        print(f"FAILED\n   Error: {e}")
        return

    # Step 2: SOQL query
    print("2. Testing SOQL query (Accounts)...", end=" ")
    try:
        result = sf.query("SELECT COUNT() FROM Account")
        count = result["totalSize"]
        print(f"SUCCESS - {count} accounts in org")
    except Exception as e:
        print(f"FAILED\n   Error: {e}")

    # Step 3: Orders enabled
    print("3. Checking Orders access...", end=" ")
    try:
        result = sf.query("SELECT COUNT() FROM Order")
        count = result["totalSize"]
        print(f"SUCCESS - {count} orders in org")
    except Exception as e:
        print(f"FAILED\n   Error: {e}")
        print("   → Make sure Orders are enabled in Setup > Order Settings")

    # Step 4: Cases access
    print("4. Checking Cases access...", end=" ")
    try:
        result = sf.query("SELECT COUNT() FROM Case")
        count = result["totalSize"]
        print(f"SUCCESS - {count} cases in org")
    except Exception as e:
        print(f"FAILED\n   Error: {e}")

    # Step 5: Products access
    print("5. Checking Products access...", end=" ")
    try:
        result = sf.query("SELECT COUNT() FROM Product2")
        count = result["totalSize"]
        print(f"SUCCESS - {count} products in org")
    except Exception as e:
        print(f"FAILED\n   Error: {e}")

    # Step 6: Standard Pricebook
    print("6. Checking Standard Pricebook...", end=" ")
    try:
        result = sf.query("SELECT Id, Name, IsActive FROM Pricebook2 WHERE IsStandard = true")
        if result["records"]:
            pb = result["records"][0]
            status = "Active" if pb["IsActive"] else "INACTIVE (needs activation)"
            print(f"SUCCESS - {pb['Name']} ({status})")
        else:
            print("WARNING - No Standard Pricebook found")
    except Exception as e:
        print(f"FAILED\n   Error: {e}")

    print("\n" + "=" * 50)
    print("Connection test complete!")
    print("=" * 50)


if __name__ == "__main__":
    main()
