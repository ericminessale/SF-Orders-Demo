# Salesforce Developer Edition Setup Guide

Step-by-step guide to get from zero to a working Salesforce org with API access for the demo. Follow every step in order.

---

## Part 1: Create the Developer Edition Org (~10 min)

### Step 1: Sign up
1. Go to **https://developer.salesforce.com/signup**
2. Fill out the form:
   - **First Name / Last Name**: your real name
   - **Email**: use your work email (you'll verify it)
   - **Company**: your company name
   - **Username**: must be in email format but does NOT need to be a real email. Example: `yourname@sf-demo.dev` — this is your login username forever, so make it memorable
   - **Country**: your country
3. Click **Sign Me Up**
4. Check your email for a verification link, click it
5. Set your password

### Step 2: Log in and note your instance URL
1. Log in at **https://login.salesforce.com** with your new credentials
2. Once logged in, the browser URL bar will show the **Lightning UI URL**, something like:
   ```
   https://orgfarm-XXXXXX-dev-ed.develop.lightning.force.com/lightning/...
   ```
3. Your **API instance URL** is different — take the subdomain prefix (everything before `.develop.lightning.force.com`) and swap it to `.develop.my.salesforce.com`:
   ```
   Lightning UI:  https://orgfarm-XXXXXX-dev-ed.develop.lightning.force.com
   API URL:       https://orgfarm-XXXXXX-dev-ed.develop.my.salesforce.com
   ```
4. **Save the API URL** — this is your `SALESFORCE_INSTANCE_URL`

---

## Part 2: Enable Orders (~2 min)

Orders might already be enabled on new orgs, but verify:

1. Click the **gear icon** (⚙️) in the top-right → **Setup**
2. In the **Quick Find** search box (left sidebar), type `Order Settings`
3. Click **Order Settings**
4. Make sure **Enable Orders** is checked
5. Optionally check **Enable Reduction Orders** (not required for our demo)
6. Click **Save**

---

## Part 3: Create the Integration User (~10 min)

Developer Edition orgs come with one **Salesforce Integration** user license. This is the user our API calls will "run as."

### Step 3a: Create the user
1. In Setup, Quick Find → type `Users`
2. Click **Users** → **New User**
3. Fill in:
   - **First Name**: `API`
   - **Last Name**: `Integration`
   - **Email**: your email (just for notifications, not login)
   - **Username**: something unique like `api-integration@sf-demo.dev`
   - **User License**: select **Salesforce Integration**
   - **Profile**: this will auto-set to **Minimum Access - API Only Integrations**
4. Click **Save**
5. You'll see a message about "Access Restricted for API Only Users" — **this is expected and correct**

### Step 3b: Give it permissions
The integration user starts with minimal access. We need to give it access to the objects we use.

1. In Setup, Quick Find → type `Permission Sets`
2. Click **Permission Sets** → **New**
3. Fill in:
   - **Label**: `Demo API Access`
   - **API Name**: `Demo_API_Access`
   - **License**: select **Salesforce API Integration** (NOT "Salesforce Integration" — the naming is confusing)
4. Click **Save**
5. Now configure the permission set:

   **Object Permissions** (click "Object Settings"):
   - Click each object below, click **Edit**, and enable the listed permissions:
   - **Accounts**: Read, Create, Edit, View All
   - **Contacts**: Read, Create, Edit, View All
   - **Orders**: Read, Create, Edit, View All
   - **Order Products** (OrderItem): Read, Create, Edit, View All
   - **Cases**: Read, Create, Edit, View All
   - **Products**: Read, Create, Edit, View All
   - **Price Books**: Read, View All
   - **Price Book Entries**: Read, Create, View All
   - **Tasks**: Read, Create, Edit

6. After saving all object permissions, go back to the permission set
7. Click **Manage Assignments** → **Add Assignment**
8. Select the `API Integration` user you created
9. Click **Assign** → **Done**

> **Why this matters**: Without these permissions, the API calls will return "insufficient access" errors even though you're authenticated. This is the #1 thing people miss.

---

## Part 4: Create the Connected App (~15 min)

### Step 4a: Create it
1. In Setup, Quick Find → type `App Manager`
2. Click **App Manager** → **New Connected App** (top right)
3. Fill in:
   - **Connected App Name**: `SignalWire Demo`
   - **API Name**: auto-fills (leave it)
   - **Contact Email**: your email
4. Scroll down to **API (Enable OAuth Settings)**:
   - Check **Enable OAuth Settings**
   - **Callback URL**: `https://localhost`
   - **Selected OAuth Scopes**: add **"Manage user data via APIs (api)"**
   - Check **Enable Client Credentials Flow** — click OK on the warning popup
5. Click **Save**, then **Continue**

### ⏳ IMPORTANT: Wait 2-10 minutes
Salesforce needs time to provision the Connected App. If you try to get tokens immediately, you'll get errors. Go get coffee.

### Step 4b: Get your Consumer Key and Secret
1. After waiting, go back to **App Manager**
2. Find "SignalWire Demo" in the list
3. Click the **dropdown arrow** (▼) on the right → **View**
4. Under "API (Enable OAuth Settings)", click **Manage Consumer Details**
5. You'll need to verify your identity (Salesforce sends a code to your email)
6. Copy the **Consumer Key** and **Consumer Secret**
7. **Save these somewhere safe** — you'll need them for the `.env` file:
   - Consumer Key = `SALESFORCE_CLIENT_ID`
   - Consumer Secret = `SALESFORCE_CLIENT_SECRET`

### Step 4c: Set the "Run As" user
1. Go back to **App Manager** → find "SignalWire Demo" → click dropdown → **Manage**
2. Click **Edit Policies**
3. Scroll down to **Client Credentials Flow**
4. Next to **Run As**, click the **magnifying glass** (🔍) icon
5. Search for and select the `API Integration` user you created in Part 3
6. Click **Save**

---

## Part 5: Configure Your .env File (~2 min)

1. In the project directory, copy the template:
   ```
   copy .env.example .env
   ```

2. Fill in the three Salesforce values:
   ```
   SALESFORCE_CLIENT_ID=paste_your_consumer_key_here
   SALESFORCE_CLIENT_SECRET=paste_your_consumer_secret_here
   SALESFORCE_INSTANCE_URL=https://yourname-dev-ed.develop.my.salesforce.com
   ```

---

## Part 6: Test the Connection (~2 min)

```bash
pip install simple-salesforce python-dotenv requests
python test_connection.py
```

You should see:
```
1. Requesting OAuth token... SUCCESS
2. Testing SOQL query... SUCCESS - 0 accounts in org
3. Checking if Orders are enabled... SUCCESS
4. Checking Standard Pricebook... SUCCESS
```

If anything fails, see Troubleshooting below.

---

## Part 7: Seed the Demo Data (~2 min)

```bash
python seed_salesforce.py
```

This creates 5 accounts, 5 contacts, 10 products, 15 orders, and 8 cases.

To verify in Salesforce: click the **App Launcher** (grid icon, top left) → search for "Accounts" or "Orders" and browse the data.

---

## Troubleshooting

### "invalid_client_id" or "invalid_client" error
- You didn't wait long enough after creating the Connected App. Wait 10 minutes and try again.
- Double-check you copied the Consumer Key correctly (no extra spaces).

### "invalid_grant" error
- The "Run As" user is not set. Go to App Manager → Manage → Edit Policies → set the Run As user.
- The Run As user doesn't have the right permission set assigned.

### "INSUFFICIENT_ACCESS" on API calls
- The integration user's permission set doesn't have access to the object. Go back to Part 3b and verify object permissions.
- Make sure the permission set is actually **assigned** to the integration user.

### "sObject type 'Order' is not supported"
- Orders aren't enabled. Go to Part 2.

### "No Standard Pricebook found"
- The Standard Pricebook exists but might be inactive. In Setup, Quick Find → "Price Books" → make sure the Standard Price Book is active.

### Token works but SOQL returns 0 records
- You haven't run the seed script yet. Run `python seed_salesforce.py`.
- Or the integration user doesn't have "View All" on the objects.

### "FIELD_CUSTOM_VALIDATION_EXCEPTION" on Orders
- Some orgs have validation rules on Orders. In Setup, Quick Find → "Orders" → "Validation Rules" → deactivate any that are blocking.

---

## Estimated Total Time

| Step | Time |
|------|------|
| Sign up for org | 5 min |
| Enable Orders | 2 min |
| Create integration user + permissions | 10 min |
| Create Connected App + wait | 15 min |
| Configure .env | 2 min |
| Test connection | 2 min |
| Seed data | 2 min |
| **Total** | **~40 min** |

The Permission Set setup (Part 3b) is the most tedious part — lots of clicking through object settings. Everything else is straightforward.
