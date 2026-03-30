"""
Order Management AI Agent — PGI Pattern
Uses steps to gate function availability. The LLM handles understanding
and data extraction. Code enforces workflow, business rules, and transitions.
"""

import sys
import os

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
    update_order_shipping_address,
    create_case,
    get_cases_for_account,
)


def format_order_number(num: str) -> str:
    """Convert '00000100' to 'zero zero zero zero zero one zero zero' for TTS."""
    digit_words = {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
                   "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine"}
    return " ".join(digit_words.get(d, d) for d in num)


class OrderManagementAgent(AgentBase):
    def __init__(self):
        super().__init__(
            name="sf-order-agent",
            route="/order-agent",
        )

        self.sf = get_salesforce_client()

        # --- Voice ---
        self.add_language("English", "en-US", "openai.alloy")

        # --- Speech recognition hints ---
        self.add_hints([
            "Acme", "Acme Corporation",
            "Globex", "Globex Industries",
            "Initech", "Initech Solutions",
            "Wayne", "Wayne Enterprises",
            "Stark", "Stark Solutions",
        ])

        # --- AI Parameters ---
        self.set_params({
            "temperature": 0.6,
            "top_p": 0.9,
            "barge_confidence": 0.3,
            "barge_min_words": 2,
            "end_of_speech_timeout": 500,
        })

        # --- Prompt: ONLY persona and tone ---
        self.prompt_add_section("Role", body=(
            "You are a customer service agent for a technology company. "
            "You are professional, concise, and empathetic. "
            "If a customer sounds frustrated, acknowledge their frustration before proceeding."
        ))

        # --- Post-prompt for call summary ---
        self.set_post_prompt(
            "Summarize the call in JSON format with these fields: "
            "account_name, actions_taken (list of strings), issues_resolved (boolean), "
            "follow_up_needed (boolean), follow_up_notes (string or null)."
        )
        self.set_post_prompt_llm_params(temperature=0.1)

        # --- Global data ---
        self.set_global_data({
            "account_id": "",
            "account_name": "",
        })

        # =====================================================================
        # STEPS — Code-driven workflow. Each step gates which tools are available.
        # Functions return change_step actions to drive transitions.
        # =====================================================================

        contexts = self.define_contexts()
        ctx = contexts.add_context("default")

        # Step 1: Identify the customer
        # Only lookup tools available. No order/case tools until identified.
        ctx.add_step("identify_customer") \
            .add_section("Task", "Greet the caller and identify their account. "
                         "Ask for their company name or phone number.") \
            .set_functions(["lookup_customer_by_name", "lookup_customer_by_phone"])

        # Step 2: Main menu — customer is verified, ask what they need
        # Can list orders, check cases, or create a case directly
        ctx.add_step("main_menu") \
            .add_section("Task", "The customer is verified. Ask how you can help. "
                         "You can list their orders, check open cases, or help with a specific order.") \
            .set_functions(["list_recent_orders", "check_open_cases", "get_order_details", "create_support_case"])

        # Step 3: Order action — working on a specific order
        # Can update address, cancel, get details, create case, or go back to menu
        ctx.add_step("order_action") \
            .add_section("Task", "Help the customer with their specific order request.") \
            .set_functions(["get_order_details", "update_shipping_address", "cancel_order",
                           "create_support_case", "list_recent_orders"])

        # Step 4: Wrap up
        ctx.add_step("wrap_up") \
            .add_section("Task", "Summarize what was done during the call and ask if there's anything else. "
                         "If not, thank them and end the call.") \
            .set_functions(["list_recent_orders", "check_open_cases", "get_order_details"])

    # =========================================================================
    # Post-call summary
    # =========================================================================

    def on_summary(self, summary, raw_data=None):
        """Write call summary back to Salesforce as a Case."""
        print(f"[on_summary] {summary}")
        try:
            self.sf.Case.create({
                "Subject": "AI Agent Call Summary",
                "Description": str(summary) if summary else "No summary",
                "Status": "New",
                "Priority": "Low",
                "Origin": "Phone",
            })
        except Exception as e:
            print(f"[on_summary] SF write failed: {e}")

    # =========================================================================
    # STEP 1 TOOLS: Customer identification
    # =========================================================================

    @AgentBase.tool(
        name="lookup_customer_by_phone",
        description="Look up a customer account by phone number",
        parameters={
            "phone": {"type": "string", "description": "Phone number, digits only (e.g. 5551001000)"}
        },
    )
    def lookup_customer_by_phone(self, args, raw_data):
        phone = args.get("phone", "")
        account = lookup_account_by_phone(self.sf, phone)

        if not account:
            return SwaigFunctionResult(
                "No account found with that phone number. Ask the customer to try their company name."
            )

        return self._account_found(account)

    @AgentBase.tool(
        name="lookup_customer_by_name",
        description="Look up a customer account by company name",
        parameters={
            "company_name": {"type": "string", "description": "Company name (partial match supported)"}
        },
    )
    def lookup_customer_by_name(self, args, raw_data):
        company_name = args.get("company_name", "")
        account = lookup_account_by_name(self.sf, company_name)

        if not account:
            return SwaigFunctionResult(
                f"No account found matching '{company_name}'. Ask the customer to verify or try a phone number."
            )

        return self._account_found(account)

    def _account_found(self, account):
        """Shared handler for successful account lookup. Transitions to main_menu."""
        orders = get_orders_for_account(self.sf, account["Id"])
        order_hints = [o["OrderNumber"] for o in orders] if orders else []

        return (
            SwaigFunctionResult(
                f"Found account: {account['Name']}. "
                f"Phone on file: {account.get('Phone', 'not listed')}. "
                f"Ask the customer how you can help."
            )
            .update_global_data({
                "account_id": account["Id"],
                "account_name": account["Name"],
            })
            .add_dynamic_hints(order_hints)
            .swml_change_step("main_menu")
        )

    # =========================================================================
    # STEP 2+ TOOLS: Order and case operations
    # =========================================================================

    @AgentBase.tool(
        name="list_recent_orders",
        description="List the customer's recent orders",
        parameters={},
    )
    def list_recent_orders(self, args, raw_data):
        global_data = raw_data.get("global_data", {}) if raw_data else {}
        account_id = global_data.get("account_id", "")

        if not account_id:
            return SwaigFunctionResult("No account identified yet.").swml_change_step("identify_customer")

        orders = get_orders_for_account(self.sf, account_id)
        if not orders:
            return SwaigFunctionResult("No orders found on this account.")

        lines = []
        for i, o in enumerate(orders, 1):
            total = f"${o['TotalAmount']:,.2f}" if o.get("TotalAmount") else "pending"
            desc = o.get("Description", "no description")
            num_spoken = format_order_number(o["OrderNumber"])
            lines.append(
                f"{i}. Order {num_spoken}, {desc}, {total}, status {o['Status']}"
            )

        return SwaigFunctionResult(
            f"{len(orders)} orders found. " + ". ".join(lines)
            + ". Ask which order they'd like details on."
        )

    @AgentBase.tool(
        name="get_order_details",
        description="Get full details of a specific order including line items",
        parameters={
            "order_number": {"type": "string", "description": "The order number"}
        },
    )
    def get_order_details(self, args, raw_data):
        order_number = args.get("order_number", "")
        order = get_order_by_number(self.sf, order_number)

        if not order:
            return SwaigFunctionResult(f"Order {order_number} not found. Ask the customer to verify.")

        items = get_order_items(self.sf, order["Id"])
        item_lines = []
        for item in items:
            name = item.get("Product2", {}).get("Name", "Unknown") if item.get("Product2") else "Unknown"
            qty = int(item.get("Quantity", 0))
            price = item.get("TotalPrice", 0)
            item_lines.append(f"{qty} of {name} at ${price:,.2f}")

        shipping = order.get("ShippingAddress")
        ship_str = "no shipping address on file"
        if shipping:
            parts = [shipping.get("street", ""), shipping.get("city", ""),
                     shipping.get("state", ""), shipping.get("postalCode", "")]
            ship_str = ", ".join(p for p in parts if p)

        total = f"${order['TotalAmount']:,.2f}" if order.get("TotalAmount") else "pending"
        num_spoken = format_order_number(order["OrderNumber"])

        details = (
            f"Order {num_spoken}: {order.get('Description', 'no description')}, "
            f"total {total}, placed {order['EffectiveDate']}, status {order['Status']}. "
            f"Shipping to {ship_str}. "
            f"Items: {', '.join(item_lines) if item_lines else 'none'}."
        )
        return SwaigFunctionResult(details).swml_change_step("order_action")

    @AgentBase.tool(
        name="update_shipping_address",
        description="Update the shipping address on an order",
        parameters={
            "order_number": {"type": "string", "description": "The order number to update"},
            "street": {"type": "string", "description": "New street address"},
            "city": {"type": "string", "description": "New city"},
            "state": {"type": "string", "description": "New state (2-letter code)"},
            "postal_code": {"type": "string", "description": "New postal/zip code"},
        },
    )
    def update_shipping_address(self, args, raw_data):
        order_number = args.get("order_number", "")
        order = get_order_by_number(self.sf, order_number)

        if not order:
            return SwaigFunctionResult(f"Order {order_number} not found.")

        # Business rule enforced in code, not prompt
        if order["Status"] != "Draft":
            return SwaigFunctionResult(
                f"This order is {order['Status']} and the address cannot be changed. "
                f"A support case can be created instead. Ask the customer if they'd like that."
            )

        success = update_order_shipping_address(
            self.sf, order["Id"],
            args.get("street", ""), args.get("city", ""),
            args.get("state", ""), args.get("postal_code", ""),
        )

        if success:
            return SwaigFunctionResult(
                f"Shipping address updated on order {format_order_number(order_number)} to "
                f"{args.get('street')}, {args.get('city')}, {args.get('state')} {args.get('postal_code')}."
            )
        return SwaigFunctionResult("Address update failed. A support case should be created.")

    @AgentBase.tool(
        name="cancel_order",
        description="Cancel an order",
        parameters={
            "order_number": {"type": "string", "description": "The order number to cancel"},
            "reason": {"type": "string", "description": "Reason for cancellation"},
        },
    )
    def cancel_order(self, args, raw_data):
        order_number = args.get("order_number", "")
        reason = args.get("reason", "")
        order = get_order_by_number(self.sf, order_number)

        if not order:
            return SwaigFunctionResult(f"Order {order_number} not found.")

        # Business rule: only Draft orders can be cancelled. Code enforces this.
        if order["Status"] != "Draft":
            return SwaigFunctionResult(
                f"This order is {order['Status']} and cannot be cancelled directly. "
                f"A return case will be created for the fulfillment team."
            )

        # Get account_id from the order
        account_id = ""
        if order.get("Account"):
            account_id = order["Account"].get("Id", "")
        if not account_id:
            result = self.sf.query(f"SELECT AccountId FROM Order WHERE Id = '{order['Id']}' LIMIT 1")
            account_id = result["records"][0]["AccountId"] if result["records"] else ""

        case_id = create_case(
            self.sf,
            account_id=account_id,
            subject=f"Order Cancellation - {order_number}",
            description=f"Cancellation requested. Reason: {reason}",
        )

        case_detail = self.sf.query(f"SELECT CaseNumber FROM Case WHERE Id = '{case_id}' LIMIT 1")
        case_num = case_detail["records"][0]["CaseNumber"] if case_detail["records"] else "pending"

        return SwaigFunctionResult(
            f"Cancellation case {case_num} created for order {format_order_number(order_number)}. "
            f"The fulfillment team will process this."
        )

    # =========================================================================
    # Case tools
    # =========================================================================

    @AgentBase.tool(
        name="check_open_cases",
        description="Check for open support cases on the customer's account",
        parameters={},
    )
    def check_open_cases(self, args, raw_data):
        global_data = raw_data.get("global_data", {}) if raw_data else {}
        account_id = global_data.get("account_id", "")

        if not account_id:
            return SwaigFunctionResult("No account identified.").swml_change_step("identify_customer")

        cases = get_cases_for_account(self.sf, account_id)
        if not cases:
            return SwaigFunctionResult("No open cases on this account.")

        lines = [f"Case {c['CaseNumber']}: {c['Subject']} ({c['Priority']} priority, {c['Status']})" for c in cases]
        return SwaigFunctionResult(f"{len(cases)} open case(s). " + ". ".join(lines))

    @AgentBase.tool(
        name="create_support_case",
        description="Create a support case for the customer",
        parameters={
            "subject": {"type": "string", "description": "Brief subject line"},
            "description": {"type": "string", "description": "Description of the issue"},
        },
    )
    def create_support_case(self, args, raw_data):
        global_data = raw_data.get("global_data", {}) if raw_data else {}
        account_id = global_data.get("account_id", "")

        if not account_id:
            return SwaigFunctionResult("No account identified.").swml_change_step("identify_customer")

        case_id = create_case(self.sf, account_id, args.get("subject", ""), args.get("description", ""))
        case_detail = self.sf.query(f"SELECT CaseNumber FROM Case WHERE Id = '{case_id}' LIMIT 1")
        case_num = case_detail["records"][0]["CaseNumber"] if case_detail["records"] else "pending"

        return SwaigFunctionResult(f"Support case {case_num} created. The team will follow up.")


def main():
    agent = OrderManagementAgent()
    agent.run(port=3000)


if __name__ == "__main__":
    main()
