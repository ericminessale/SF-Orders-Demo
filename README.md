# SF Orders Demo

AI voice agent for order management, powered by SignalWire and backed by a live Salesforce org.

A caller phones in, identifies themselves by company name, and the agent looks up their account, lists orders, provides order details, validates and updates shipping addresses via Google Maps, requests cancellations, and creates support cases — all in real-time against Salesforce.

## What it does

- **Account lookup** — find customers by company name via Salesforce Accounts
- **Order management** — list recent orders, get line-item details, cancel draft orders
- **Address validation** — validate new shipping addresses via Google Maps Geocoding before applying, with customer confirmation
- **Case creation** — create support cases for escalations, cancellations, and issues
- **Post-call summary** — automatically writes a structured call summary back to Salesforce as a Case after every call

## Setup

### 1. Salesforce org

Follow [SETUP_GUIDE.md](SETUP_GUIDE.md) to create a free Developer Edition org, configure OAuth, and seed demo data.

### 2. Install dependencies

```bash
pip install -r requirements.txt
pip install signalwire
```

### 3. Configure environment

```bash
cp .env.example .env
# Fill in your SignalWire credentials, Salesforce OAuth credentials, and Google Maps API key
```

### 4. Test Salesforce connection

```bash
python test_connection.py
```

### 5. Seed demo data

```bash
python seed_salesforce.py
```

### 6. Run the agent

```bash
python order_agent.py
```

The agent starts on port 3000. Expose it with ngrok or deploy to a server, then point a SignalWire phone number at `https://your-url/order-agent`.

## Files

| File | Purpose |
|------|---------|
| `order_agent.py` | The voice AI agent with all SWAIG tools |
| `salesforce_client.py` | Salesforce REST API client (OAuth + CRUD + address normalization) |
| `seed_salesforce.py` | Seeds the SF org with demo accounts, orders, products, cases |
| `test_connection.py` | Verifies Salesforce API connectivity |
| `SETUP_GUIDE.md` | Step-by-step Salesforce org setup guide |
