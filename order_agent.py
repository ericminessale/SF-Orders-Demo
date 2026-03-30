"""
Order Management AI Agent for the Salesforce demo.
Handles order lookups, status checks, address changes, cancellations,
returns, case creation, and escalation — all backed by a live Salesforce org.
"""

import sys
import os
from typing import Optional, Dict, Any

# Add the SDK to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "signalwire-agents-python"))

from dotenv import load_dotenv
load_dotenv()

from signalwire_agents import AgentBase
from signalwire_agents.core.function_result import SwaigFunctionResult
from salesforce_client import (
    get_salesforce_client,
    lookup_account_by_phone,
    lookup_account_by_name,
    get_orders_for_account,
    get_order_by_number,
    get_order_items,
    update_order_status,
    update_order_shipping_address,
    create_case,
    get_cases_for_account,
    add_case_comment,
    create_task,
)


class OrderManagementAgent(AgentBase):
    def __init__(self):
        super().__init__(
            name="sf-order-agent",
            route="/order-agent",
        )

        # Connect to Salesforce at startup
        self.sf = get_salesforce_client()

        # --- Voice & Speech Config ---
        self.add_language(
            "English", "en-US", "openai.alloy",
            speech_fillers=False,
            function_fillers=False,
        )

        # Speech recognition hints for company names in our CRM
        self.add_hints([
            "Acme", "Acme Corporation",
            "Globex", "Globex Industries",
            "Initech", "Initech Solutions",
            "Wayne", "Wayne Enterprises",
            "Stark", "Stark Solutions",
            "Salesforce", "SignalWire",
        ])

        # Pronunciation help for tricky terms
        self.add_pronunciation("SOQL", "so-quel")

        # --- AI Parameters ---
        self.set_params({
            "temperature": 0.6,
            "top_p": 0.9,
            "barge_confidence": 0.3,
            "barge_min_words": 2,
            "end_of_speech_timeout": 500,
        })

        # --- Debug Events (disabled for now — was causing webhook errors) ---
        # self.enable_debug_events(level=1)

        # --- Prompt (POM) ---
        self.prompt_add_section("Role", body=(
            "You are a helpful customer service agent for a technology company. "
            "You have access to the company's Salesforce CRM and can look up accounts, "
            "orders, cases, and perform actions like updating shipping addresses or "
            "creating support cases. You are professional, concise, and empathetic."
        ))

        self.prompt_add_section("Conversation Flow", bullets=[
            "Start by greeting the customer warmly and asking how you can help.",
            "If they want to check on an order, ask for their company name or phone number to pull up their account.",
            "Once you have their account, you can look up orders, check statuses, update addresses, or create cases.",
            "Always confirm details back to the customer before making changes.",
            "If the customer is frustrated, empathize and offer to escalate by creating a high-priority case.",
            "At the end of the call, summarize what was done and ask if there's anything else.",
        ])

        self.prompt_add_section("Important Rules", bullets=[
            "Never make up order numbers or account details. Always look them up.",
            "Confirm with the customer before making any changes to orders.",
            "If you can't find their account, ask them to verify the name or phone number.",
            "For cancellations, explain that Draft orders can be cancelled but Activated orders may need a return process.",
            "When reading order numbers, say each digit clearly (e.g. 'zero zero zero zero zero one zero zero').",
        ])

        # --- Post-prompt for call summary ---
        self.set_post_prompt(
            "Summarize the call in JSON format with these fields: "
            "account_name, actions_taken (list of strings), issues_resolved (boolean), "
            "follow_up_needed (boolean), follow_up_notes (string or null), "
            "customer_sentiment (positive/neutral/negative)."
        )
        self.set_post_prompt_llm_params(temperature=0.1)

        # --- Initial global data ---
        self.set_global_data({
            "account_id": "",
            "account_name": "",
            "verified": False,
        })

        # --- Debug event handler (disabled — was causing webhook errors on call start) ---
        # @self.on_debug_event
        # def handle_debug(event_type: str, data: dict):
        #     print(f"[DEBUG EVENT] {event_type}: {data}")

    # =========================================================================
    # Post-call summary — method override, NOT a tool
    # =========================================================================

    def on_summary(self, summary, raw_data=None):
        """Called automatically after the call ends with post-prompt results."""
        print(f"[on_summary] Received: {summary}")
        try:
            description = str(summary) if summary else "No summary available"
            # Try Case comment first (more reliable), then Task as fallback
            try:
                case_data = {
                    "Subject": "AI Agent Call Summary",
                    "Description": description,
                    "Status": "New",
                    "Priority": "Low",
                    "Origin": "Phone",
                }
                result = self.sf.Case.create(case_data)
                print(f"[on_summary] Case created in Salesforce: {result['id']}")
            except Exception as e1:
                print(f"[on_summary] Case creation failed ({e1}), trying Task...")
                task_data = {
                    "Subject": "AI Agent Call Summary",
                    "Description": description,
                    "Status": "Completed",
                    "Priority": "Normal",
                }
                self.sf.Task.create(task_data)
                print("[on_summary] Task created in Salesforce")
        except Exception as e:
            print(f"[on_summary] Error writing summary to Salesforce: {e}")
            print("[on_summary] Summary was still captured in logs above.")

    # =========================================================================
    # Account Lookup Tools
    # =========================================================================

    @AgentBase.tool(
        name="lookup_customer_by_phone",
        description="Look up a customer account by their phone number",
        parameters={
            "phone": {
                "type": "string",
                "description": "The customer's phone number (digits only, e.g. 5551001000)",
            }
        },
    )
    def lookup_customer_by_phone(self, args, raw_data):
        phone = args.get("phone", "")
        account = lookup_account_by_phone(self.sf, phone)
        if not account:
            return SwaigFunctionResult(
                "I couldn't find an account with that phone number. "
                "Could you try your company name instead?"
            )

        # After finding account, add order numbers as dynamic hints for better STT
        orders = get_orders_for_account(self.sf, account["Id"])
        order_hints = [o["OrderNumber"] for o in orders] if orders else []

        return (
            SwaigFunctionResult(
                f"I found the account for {account['Name']}. "
                f"Account number: {account.get('AccountNumber', 'N/A')}. "
                f"How can I help you today?"
            )
            .update_global_data({
                "account_id": account["Id"],
                "account_name": account["Name"],
                "verified": True,
            })
            .add_dynamic_hints(order_hints)
        )

    @AgentBase.tool(
        name="lookup_customer_by_name",
        description="Look up a customer account by company name",
        parameters={
            "company_name": {
                "type": "string",
                "description": "The customer's company name (partial match supported)",
            }
        },
    )
    def lookup_customer_by_name(self, args, raw_data):
        company_name = args.get("company_name", "")
        account = lookup_account_by_name(self.sf, company_name)
        if not account:
            return SwaigFunctionResult(
                f"I couldn't find an account matching '{company_name}'. "
                "Could you double-check the name or try a phone number?"
            )

        # After finding account, add order numbers as dynamic hints
        orders = get_orders_for_account(self.sf, account["Id"])
        order_hints = [o["OrderNumber"] for o in orders] if orders else []

        return (
            SwaigFunctionResult(
                f"I found the account for {account['Name']}. "
                f"Phone on file: {account.get('Phone', 'N/A')}. "
                f"How can I help you today?"
            )
            .update_global_data({
                "account_id": account["Id"],
                "account_name": account["Name"],
                "verified": True,
            })
            .add_dynamic_hints(order_hints)
        )

    # =========================================================================
    # Order Tools
    # =========================================================================

    @AgentBase.tool(
        name="list_recent_orders",
        description="List the customer's recent orders. The account_id is automatically retrieved from the verified account.",
        parameters={},
    )
    def list_recent_orders(self, args, raw_data):
        # Pull account_id from global_data (set during lookup), not from AI args
        global_data = raw_data.get("global_data", {}) if raw_data else {}
        account_id = global_data.get("account_id", "")
        orders = get_orders_for_account(self.sf, account_id)
        if not orders:
            return SwaigFunctionResult("I don't see any orders on this account.")

        order_summaries = []
        for i, o in enumerate(orders, 1):
            total = f"${o['TotalAmount']:,.2f}" if o.get("TotalAmount") else "pending"
            desc = o.get('Description', 'No description')
            date = o.get('EffectiveDate', 'unknown date')
            order_summaries.append(
                f"{i}. Order number {o['OrderNumber']}, {desc}, "
                f"totaling {total}, placed on {date}, status is {o['Status']}"
            )

        count = len(orders)
        summary = (
            f"The customer has {count} recent order{'s' if count != 1 else ''}. "
            + ". ".join(order_summaries)
            + ". Ask the customer if they'd like details on any of these orders."
        )
        return SwaigFunctionResult(summary)

    @AgentBase.tool(
        name="get_order_details",
        description="Get full details of a specific order including line items",
        parameters={
            "order_number": {
                "type": "string",
                "description": "The order number (e.g. 00000101)",
            }
        },
    )
    def get_order_details(self, args, raw_data):
        order_number = args.get("order_number", "")
        order = get_order_by_number(self.sf, order_number)
        if not order:
            return SwaigFunctionResult(
                f"I couldn't find order {order_number}. Could you verify the number?"
            )

        items = get_order_items(self.sf, order["Id"])
        item_lines = []
        for item in items:
            product_name = item.get("Product2", {}).get("Name", "Unknown") if item.get("Product2") else "Unknown"
            qty = int(item.get("Quantity", 0))
            price = item.get("TotalPrice", 0)
            item_lines.append(f"{qty} of {product_name} at ${price:,.2f}")

        shipping = order.get("ShippingAddress")
        ship_str = "no shipping address on file"
        if shipping:
            parts = [shipping.get("street", ""), shipping.get("city", ""),
                     shipping.get("state", ""), shipping.get("postalCode", "")]
            ship_str = ", ".join(p for p in parts if p)

        total = f"${order['TotalAmount']:,.2f}" if order.get("TotalAmount") else "pending"

        items_str = ", ".join(item_lines) if item_lines else "no line items"
        details = (
            f"Order number {order['OrderNumber']} is for {order.get('Description', 'no description')}, "
            f"with a total of {total}, placed on {order['EffectiveDate']}. "
            f"The current status is {order['Status']}. "
            f"Shipping address is {ship_str}. "
            f"Line items include: {items_str}."
            f"  Shipping: {ship_str}\n"
            f"  Items:\n" + "\n".join(item_lines)
        )
        return SwaigFunctionResult(details)

    @AgentBase.tool(
        name="update_shipping_address",
        description="Update the shipping address on an order. Only works for Draft orders.",
        parameters={
            "order_number": {
                "type": "string",
                "description": "The order number to update",
            },
            "street": {"type": "string", "description": "New street address"},
            "city": {"type": "string", "description": "New city"},
            "state": {"type": "string", "description": "New state (2-letter code)"},
            "postal_code": {"type": "string", "description": "New postal/zip code"},
        },
    )
    def update_shipping_address(self, args, raw_data):
        order_number = args.get("order_number", "")
        street = args.get("street", "")
        city = args.get("city", "")
        state = args.get("state", "")
        postal_code = args.get("postal_code", "")

        order = get_order_by_number(self.sf, order_number)
        if not order:
            return SwaigFunctionResult(f"I couldn't find order {order_number}.")

        if order["Status"] != "Draft":
            return SwaigFunctionResult(
                f"Order {order_number} is currently {order['Status']}. "
                "I can only update the address on Draft orders. "
                "Would you like me to create a support case for this instead?"
            )

        success = update_order_shipping_address(
            self.sf, order["Id"], street, city, state, postal_code
        )
        if success:
            return SwaigFunctionResult(
                f"I've updated the shipping address on order {order_number} to "
                f"{street}, {city}, {state} {postal_code}."
            )
        else:
            return SwaigFunctionResult(
                "I wasn't able to update the address. Let me create a support case for this."
            )

    @AgentBase.tool(
        name="cancel_order",
        description="Cancel a Draft order. Activated orders cannot be directly cancelled.",
        parameters={
            "order_number": {
                "type": "string",
                "description": "The order number to cancel",
            },
            "reason": {
                "type": "string",
                "description": "The reason for cancellation",
            },
        },
    )
    def cancel_order(self, args, raw_data):
        order_number = args.get("order_number", "")
        reason = args.get("reason", "")

        order = get_order_by_number(self.sf, order_number)
        if not order:
            return SwaigFunctionResult(f"I couldn't find order {order_number}.")

        if order["Status"] != "Draft":
            return SwaigFunctionResult(
                f"Order {order_number} is {order['Status']} and can't be cancelled directly. "
                "I can create a return/cancellation case for our fulfillment team to process. "
                "Would you like me to do that?"
            )

        account_id = order.get("Account", {}).get("Id", "") if order.get("Account") else ""
        if not account_id:
            full_order = self.sf.query(f"SELECT AccountId FROM Order WHERE Id = '{order['Id']}' LIMIT 1")
            account_id = full_order["records"][0]["AccountId"] if full_order["records"] else ""

        case_id = create_case(
            self.sf,
            account_id=account_id,
            subject=f"Order Cancellation Request - {order_number}",
            description=f"Customer requested cancellation of order {order_number}. Reason: {reason}",
            order_id=order["Id"],
        )

        return SwaigFunctionResult(
            f"I've created a cancellation request for order {order_number}. "
            f"A support case has been opened and our team will process the cancellation. "
            f"Reason recorded: {reason}."
        )

    # =========================================================================
    # Case Tools
    # =========================================================================

    @AgentBase.tool(
        name="check_open_cases",
        description="Check if the customer has any open support cases. The account is automatically identified from the verified session.",
        parameters={},
    )
    def check_open_cases(self, args, raw_data):
        global_data = raw_data.get("global_data", {}) if raw_data else {}
        account_id = global_data.get("account_id", "")
        cases = get_cases_for_account(self.sf, account_id)
        if not cases:
            return SwaigFunctionResult("There are no open cases on this account.")

        case_summaries = []
        for c in cases:
            case_summaries.append(
                f"Case {c['CaseNumber']}: {c['Subject']} "
                f"(Priority: {c['Priority']}, Status: {c['Status']})"
            )

        summary = f"I found {len(cases)} open case(s):\n" + "\n".join(case_summaries)
        return SwaigFunctionResult(summary)

    @AgentBase.tool(
        name="create_support_case",
        description="Create a new support case for the customer. The account is automatically identified from the verified session.",
        parameters={
            "subject": {
                "type": "string",
                "description": "Brief subject line for the case",
            },
            "description": {
                "type": "string",
                "description": "Detailed description of the issue",
            },
        },
    )
    def create_support_case(self, args, raw_data):
        global_data = raw_data.get("global_data", {}) if raw_data else {}
        account_id = global_data.get("account_id", "")
        subject = args.get("subject", "")
        description = args.get("description", "")

        case_id = create_case(self.sf, account_id, subject, description)

        case_detail = self.sf.query(f"SELECT CaseNumber FROM Case WHERE Id = '{case_id}' LIMIT 1")
        case_number = case_detail["records"][0]["CaseNumber"] if case_detail["records"] else "N/A"

        return SwaigFunctionResult(
            f"I've created support case {case_number}: {subject}. "
            "Our team will review this and follow up. "
            "Is there anything else I can help with?"
        )


def main():
    agent = OrderManagementAgent()
    agent.run(port=3001)


if __name__ == "__main__":
    main()
