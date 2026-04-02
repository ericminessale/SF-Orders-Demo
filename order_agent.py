"""
Order Management AI Agent — PGI Pattern
Uses steps to gate function availability. The LLM handles understanding
and data extraction. Code enforces workflow, business rules, and transitions.
"""

import os
import requests

from dotenv import load_dotenv
load_dotenv()

from signalwire import AgentBase
from signalwire.core.function_result import FunctionResult
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


class OrderManagementAgent(AgentBase):
    def __init__(self):
        super().__init__(
            name="sf-order-agent",
            route="/order-agent",
            record_call=True,
            record_format="wav",
            record_stereo=True,
            token_expiry_secs=86400,
        )

        self.sf = get_salesforce_client()

        # --- Voice ---
        self.add_language(
            "English", "en-US", "elevenlabs.rachel:eleven_turbo_v2_5",
            function_fillers=[
                "Let me look that up for you.",
                "One moment while I check.",
                "Checking that now.",
            ],
        )

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
            "enable_thinking": False,
            "turn_detection_min_length": 4,
        })

        # --- Model ---
        self.set_prompt_llm_params(model="gpt-4o-mini")

        # --- Prompt: persona and tone only ---
        self.prompt_add_section("Role", body=(
            "You are a customer service agent for a technology company. "
            "You are professional, concise, and empathetic."
        ))
        self.prompt_add_section("Response Style", bullets=[
            "Keep responses to 1-2 sentences.",
            "Ask one question at a time.",
            "If a customer sounds frustrated, acknowledge it briefly before proceeding.",
            "Never repeat information the customer already heard.",
        ])
        self.prompt_add_section("Capabilities", body=(
            "You can: look up customer accounts, list orders, show order details, "
            "validate and update shipping addresses on Draft orders, cancel Draft orders, "
            "check open support cases, and create new support cases. "
            "You cannot: process refunds, place new orders, update billing information, "
            "approve orders, modify account details, or access any system outside Salesforce. "
            "If asked to do something outside your capabilities, say so and offer to create a support case."
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
        # STEPS
        # =====================================================================

        contexts = self.define_contexts()
        ctx = contexts.add_context("default")

        ctx.add_step("identify_customer") \
            .add_section("Task", "Greet the caller and ask for their company name to look up their account.") \
            .set_functions(["lookup_customer_by_name"])

        ctx.add_step("main_menu") \
            .add_section("Task", "The customer is verified. Ask how you can help. "
                         "You can only access data for the verified account.") \
            .set_functions(["list_recent_orders", "check_open_cases", "get_order_details",
                           "validate_shipping_address", "confirm_shipping_address", "cancel_order", "create_support_case"])

        ctx.add_step("order_action") \
            .add_section("Task", "Help the customer with their specific order request.") \
            .set_functions(["get_order_details", "validate_shipping_address", "confirm_shipping_address", "cancel_order",
                           "create_support_case", "list_recent_orders"])

        ctx.add_step("wrap_up") \
            .add_section("Task", "Briefly summarize what was done and ask if there's anything else.") \
            .set_functions(["list_recent_orders", "check_open_cases", "get_order_details"])

    # =========================================================================
    # Post-call summary
    # =========================================================================

    def on_summary(self, summary, raw_data=None):
        """Write call summary back to Salesforce as a Case."""
        print(f"[on_summary] {summary}")

        import json
        try:
            with open("post_prompt_log.json", "w") as f:
                json.dump({"summary": summary, "raw_data": raw_data}, f, indent=2, default=str)
        except Exception:
            pass

        try:
            global_data = raw_data.get("global_data", {}) if raw_data else {}
            account_id = global_data.get("account_id", "")
            account_name = global_data.get("account_name", "Unknown")

            case_data = {
                "Subject": f"Call Summary - {account_name}",
                "Description": str(summary) if summary else "No summary",
                "Status": "New",
                "Priority": "Low",
                "Origin": "Phone",
            }
            if account_id:
                case_data["AccountId"] = account_id
                try:
                    contact = self.sf.query(
                        f"SELECT Id FROM Contact WHERE AccountId = '{account_id}' LIMIT 1"
                    )
                    if contact["records"]:
                        case_data["ContactId"] = contact["records"][0]["Id"]
                except Exception:
                    pass

            self.sf.Case.create(case_data)
        except Exception as e:
            print(f"[on_summary] SF write failed: {e}")

    # =========================================================================
    # Helpers
    # =========================================================================

    def _resolve_order_number(self, order_number, global_data):
        """Resolve position, description, or exact order number via order_map in global_data."""
        order_map = global_data.get("order_map", {})
        if order_number in order_map:
            return order_map[order_number]
        if order_number.lower() in order_map:
            return order_map[order_number.lower()]
        for key, val in order_map.items():
            if not key.isdigit() and order_number.lower() in key:
                return val
        return order_number

    def _verify_order_account(self, order, global_data):
        """Returns error FunctionResult if order doesn't belong to the verified account, else None."""
        account_id = global_data.get("account_id", "")
        order_account = order.get("Account", {}).get("Id", "") if order.get("Account") else ""
        if account_id and order_account and order_account != account_id:
            return FunctionResult("That order does not belong to your account.")
        return None

    def _account_found(self, account):
        """Shared handler for successful account lookup. Transitions to main_menu."""
        orders = get_orders_for_account(self.sf, account["Id"])
        order_hints = [o["OrderNumber"] for o in orders] if orders else []

        return (
            FunctionResult(
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
    # STEP 1: Customer identification
    # =========================================================================

    @AgentBase.tool(
        name="lookup_customer_by_phone",
        description="Look up a customer account by phone number. "
                    "Returns account name and transitions to order management.",
        parameters={
            "phone": {
                "type": "string",
                "description": "The caller's phone number in E.164 format: "
                               "+1 followed by 10 digits, no dashes or spaces (e.g. '+15551001000')"
            }
        },
    )
    def lookup_customer_by_phone(self, args, raw_data):
        account = lookup_account_by_phone(self.sf, args.get("phone", ""))
        if not account:
            return FunctionResult("No account found with that phone number. Ask for their company name instead.")
        return self._account_found(account)

    @AgentBase.tool(
        name="lookup_customer_by_name",
        description="Look up a customer account by company name. "
                    "Partial names are supported. Returns account name and transitions to order management.",
        parameters={
            "company_name": {
                "type": "string",
                "description": "The company name as spoken by the caller (e.g. 'Acme' will match 'Acme Corporation')"
            }
        },
    )
    def lookup_customer_by_name(self, args, raw_data):
        company_name = args.get("company_name", "")
        account = lookup_account_by_name(self.sf, company_name)
        if not account:
            return FunctionResult(f"No account matching '{company_name}'. Ask to verify or try a phone number.")
        return self._account_found(account)

    # =========================================================================
    # STEP 2+: Order and case operations
    # =========================================================================

    @AgentBase.tool(
        name="list_recent_orders",
        description="List the customer's recent orders with descriptions, totals, statuses, and order numbers. "
                    "After calling this, the customer can refer to orders by position (1, 2, 3) or order number.",
        parameters={},
    )
    def list_recent_orders(self, args, raw_data):
        global_data = raw_data.get("global_data", {}) if raw_data else {}
        account_id = global_data.get("account_id", "")

        if not account_id:
            return FunctionResult("No account identified yet.").swml_change_step("identify_customer")

        orders = get_orders_for_account(self.sf, account_id)
        if not orders:
            return FunctionResult("No orders found on this account.")

        order_map = {}
        lines = []
        for i, o in enumerate(orders, 1):
            total = f"${o['TotalAmount']:,.2f}" if o.get("TotalAmount") else "pending"
            desc = o.get("Description", "no description")
            order_map[str(i)] = o["OrderNumber"]
            order_map[desc.lower()] = o["OrderNumber"]
            lines.append(f"{i}. {desc}, {total}, status {o['Status']} (order number {o['OrderNumber']})")

        return (
            FunctionResult(f"{len(orders)} orders: " + ". ".join(lines))
            .update_global_data({"order_map": order_map})
        )

    @AgentBase.tool(
        name="get_order_details",
        description="Get full details for a specific order including line items, shipping address, and status. "
                    "Use when the customer asks about a specific order.",
        parameters={
            "order_number": {
                "type": "string",
                "description": "The 8-digit Salesforce order number (e.g. '00000100'). "
                               "If the caller refers by position from the list, pass the digit ('1', '2', '3')."
            }
        },
    )
    def get_order_details(self, args, raw_data):
        global_data = raw_data.get("global_data", {}) if raw_data else {}
        order_number = self._resolve_order_number(args.get("order_number", ""), global_data)
        order = get_order_by_number(self.sf, order_number)

        if not order:
            return FunctionResult(f"Order {order_number} not found. Ask the customer to verify.")

        err = self._verify_order_account(order, global_data)
        if err:
            return err

        items = get_order_items(self.sf, order["Id"])
        item_lines = [
            f"{int(item.get('Quantity', 0))} of "
            f"{item.get('Product2', {}).get('Name', 'Unknown') if item.get('Product2') else 'Unknown'} "
            f"at ${item.get('TotalPrice', 0):,.2f}"
            for item in items
        ]

        shipping = order.get("ShippingAddress")
        ship_str = "no shipping address on file"
        if shipping:
            parts = [shipping.get("street", ""), shipping.get("city", ""),
                     shipping.get("state", ""), shipping.get("postalCode", "")]
            ship_str = ", ".join(p for p in parts if p)

        total = f"${order['TotalAmount']:,.2f}" if order.get("TotalAmount") else "pending"
        items_str = ", ".join(item_lines) if item_lines else "no line items"

        return FunctionResult(
            f"{order.get('Description', 'Order')}: {items_str}. "
            f"Total {total}, status {order['Status']}, shipping to {ship_str}."
        ).swml_change_step("order_action")

    def _geocode_address(self, address: str) -> dict | None:
        """Validate and normalize an address via Google Maps Geocoding API.
        Returns {street, city, state, postal_code, formatted} or None."""
        api_key = os.getenv("GOOGLE_MAPS_API_KEY")
        if not api_key:
            return None
        try:
            resp = requests.get("https://maps.googleapis.com/maps/api/geocode/json", params={
                "address": address,
                "key": api_key,
                "components": "country:US",
            }, timeout=5)
            data = resp.json()
            if data.get("status") != "OK" or not data.get("results"):
                return None

            result = data["results"][0]
            components = {c["types"][0]: c for c in result["address_components"] if c.get("types")}

            street_num = components.get("street_number", {}).get("long_name", "")
            route = components.get("route", {}).get("long_name", "")
            city = components.get("locality", {}).get("long_name", "")
            state = components.get("administrative_area_level_1", {}).get("long_name", "")
            postal = components.get("postal_code", {}).get("long_name", "")

            return {
                "street": f"{street_num} {route}".strip(),
                "city": city,
                "state": state,
                "postal_code": postal,
                "formatted": result.get("formatted_address", ""),
            }
        except Exception as e:
            print(f"[geocode] Error: {e}")
            return None

    @AgentBase.tool(
        name="validate_shipping_address",
        description="Validate a new shipping address for an order using Google Maps. "
                    "Returns the normalized address for customer confirmation. "
                    "After the customer confirms, call confirm_shipping_address to apply the change. "
                    "Do not use create_support_case for address changes.",
        parameters={
            "order_number": {
                "type": "string",
                "description": "The 8-digit Salesforce order number (e.g. '00000100'), "
                               "or position from list ('1', '2', '3')."
            },
            "address": {
                "type": "string",
                "description": "The full new address as spoken by the caller "
                               "(e.g. '123 New Street, Metropolis, NY 10001')"
            },
        },
    )
    def validate_shipping_address(self, args, raw_data):
        global_data = raw_data.get("global_data", {}) if raw_data else {}
        order_number = self._resolve_order_number(args.get("order_number", ""), global_data)
        order = get_order_by_number(self.sf, order_number)

        if not order:
            return FunctionResult(f"Order {order_number} not found.")

        err = self._verify_order_account(order, global_data)
        if err:
            return err

        if order["Status"] != "Draft":
            return FunctionResult(
                f"This order is {order['Status']} and the address cannot be changed directly."
            )

        address = args.get("address", "")
        validated = self._geocode_address(address)

        if not validated:
            return FunctionResult(
                "Could not validate that address. Ask the customer to repeat or clarify it."
            )

        # Store validated address and order in global_data — LLM never touches this
        return (
            FunctionResult(
                f"The validated address is: {validated['formatted']}. "
                f"Ask the customer to confirm this is correct before applying the change."
            )
            .update_global_data({
                "pending_address": validated,
                "pending_address_order_id": order["Id"],
                "pending_address_order_number": order_number,
            })
        )

    @AgentBase.tool(
        name="confirm_shipping_address",
        description="Apply the validated shipping address to the order after the customer confirms. "
                    "Only call this after validate_shipping_address and customer confirmation.",
        parameters={},
    )
    def confirm_shipping_address(self, args, raw_data):
        global_data = raw_data.get("global_data", {}) if raw_data else {}
        pending = global_data.get("pending_address")
        order_id = global_data.get("pending_address_order_id")
        order_number = global_data.get("pending_address_order_number", "")

        if not pending or not order_id:
            return FunctionResult("No validated address pending. Use validate_shipping_address first.")

        success = update_order_shipping_address(
            self.sf, order_id,
            pending["street"], pending["city"], pending["state"], pending["postal_code"]
        )

        if success:
            return (
                FunctionResult(f"Shipping address on order {order_number} updated to {pending['formatted']}.")
                .update_global_data({
                    "pending_address": None,
                    "pending_address_order_id": None,
                    "pending_address_order_number": None,
                })
            )
        return FunctionResult("Address update failed.")

    @AgentBase.tool(
        name="cancel_order",
        description="Cancel a Draft order by creating a cancellation case in Salesforce. "
                    "Requires the customer's reason for cancellation — do not call without it.",
        parameters={
            "order_number": {
                "type": "string",
                "description": "The 8-digit Salesforce order number (e.g. '00000100'), "
                               "or position from list ('1', '2', '3')."
            },
            "reason": {
                "type": "string",
                "description": "The customer's reason for cancellation in their own words. "
                               "This must come from the customer — ask them if they haven't stated it."
            },
        },
    )
    def cancel_order(self, args, raw_data):
        reason = args.get("reason", "")

        if not reason or not reason.strip():
            return FunctionResult("Cannot cancel without a reason. Ask the customer why they want to cancel.")

        global_data = raw_data.get("global_data", {}) if raw_data else {}
        order_number = self._resolve_order_number(args.get("order_number", ""), global_data)
        order = get_order_by_number(self.sf, order_number)

        if not order:
            return FunctionResult(f"Order {order_number} not found.")

        err = self._verify_order_account(order, global_data)
        if err:
            return err

        if order["Status"] != "Draft":
            return FunctionResult(
                f"This order is {order['Status']} and cannot be cancelled directly."
            )

        account_id = global_data.get("account_id", "")

        case_id = create_case(
            self.sf,
            account_id=account_id,
            subject=f"Order Cancellation - {order_number}",
            description=f"Cancellation requested. Reason: {reason}",
        )

        case_detail = self.sf.query(f"SELECT CaseNumber FROM Case WHERE Id = '{case_id}' LIMIT 1")
        case_num = case_detail["records"][0]["CaseNumber"] if case_detail["records"] else "pending"

        return FunctionResult(f"Cancellation case {case_num} created for order {order_number}.")

    # =========================================================================
    # Case tools
    # =========================================================================

    @AgentBase.tool(
        name="check_open_cases",
        description="Check for open support cases on the customer's account. "
                    "Returns case numbers, subjects, and priorities.",
        parameters={},
    )
    def check_open_cases(self, args, raw_data):
        global_data = raw_data.get("global_data", {}) if raw_data else {}
        account_id = global_data.get("account_id", "")

        if not account_id:
            return FunctionResult("No account identified.").swml_change_step("identify_customer")

        cases = get_cases_for_account(self.sf, account_id)
        if not cases:
            return FunctionResult("No open cases on this account.")

        lines = [f"Case {c['CaseNumber']}: {c['Subject']} ({c['Priority']} priority)" for c in cases]
        return FunctionResult(f"{len(cases)} open case(s). " + ". ".join(lines))

    @AgentBase.tool(
        name="create_support_case",
        description="Create a general support case for issues that don't have a dedicated function. "
                    "Do not use for address changes (use validate_shipping_address) "
                    "or cancellations (use cancel_order).",
        parameters={
            "subject": {
                "type": "string",
                "description": "One-line subject (e.g. 'Billing dispute', 'Product defect report')"
            },
            "description": {
                "type": "string",
                "description": "Detailed description including relevant order numbers and specifics from the customer"
            },
        },
    )
    def create_support_case(self, args, raw_data):
        global_data = raw_data.get("global_data", {}) if raw_data else {}
        account_id = global_data.get("account_id", "")

        if not account_id:
            return FunctionResult("No account identified.").swml_change_step("identify_customer")

        case_id = create_case(self.sf, account_id, args.get("subject", ""), args.get("description", ""))
        case_detail = self.sf.query(f"SELECT CaseNumber FROM Case WHERE Id = '{case_id}' LIMIT 1")
        case_num = case_detail["records"][0]["CaseNumber"] if case_detail["records"] else "pending"

        return FunctionResult(f"Support case {case_num} created.")


def main():
    agent = OrderManagementAgent()
    agent.run(port=3000)


if __name__ == "__main__":
    main()
