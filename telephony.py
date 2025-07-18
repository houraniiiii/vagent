# set up inbound trunking for the phone number

import argparse
import logging
from sip import create_sip_inbound_trunk, create_sip_outbound_trunk

logger = logging.getLogger("sip")
file_handler = logging.FileHandler("sip.log")
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.propagate = False  # Prevents duplicate logs if root logger is also configured


def set_up_inbound_trunking(phone_number, nickname):
    """
    Set up inbound trunking for a phone number.
    """
    logger.info(
        "Setting up inbound trunking for %s with nickname %s", phone_number, nickname
    )
    # Add your inbound trunking setup logic here
    result = create_sip_inbound_trunk(number=phone_number, nickname=nickname)
    if result["success"]:
        logger.info(
            "Inbound trunking setup for %s with nickname %s", phone_number, nickname
        )
    else:
        logger.error(
            "Error setting up inbound trunking for %s with nickname %s: %s",
            phone_number,
            nickname,
            result["error"],
        )


def set_up_outbound_trunking(phone_number, sip_trunk_uri, username, password, nickname):
    """
    Set up outbound trunking for a phone number.
    """
    logger.info(
        "Setting up outbound trunking for %s to %s as '%s' with nickname '%s'",
        phone_number,
        sip_trunk_uri,
        username,
        nickname,
    )
    # Add your outbound trunking setup logic here
    result = create_sip_outbound_trunk(
        phone_number, sip_trunk_uri, username, password, nickname
    )
    if result["success"]:
        logger.info(
            "Outbound trunking setup for %s to %s as '%s' with nickname '%s'",
            phone_number,
            sip_trunk_uri,
            username,
            nickname,
        )
    else:
        logger.error(
            "Error setting up outbound trunking for %s to %s as '%s' with nickname '%s': %s",
            phone_number,
            sip_trunk_uri,
            username,
            nickname,
            result["error"],
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Set up telephony trunking.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Inbound command
    inbound_parser = subparsers.add_parser("inbound", help="Set up inbound trunking")
    inbound_parser.add_argument(
        "--phone-number", required=True, help="Phone number for inbound trunking"
    )

    # Outbound command
    outbound_parser = subparsers.add_parser("outbound", help="Set up outbound trunking")
    outbound_parser.add_argument(
        "--phone-number", required=True, help="Phone number for outbound trunking"
    )
    outbound_parser.add_argument("--sip-trunk-uri", required=True, help="SIP trunk URI")
    outbound_parser.add_argument("--username", required=True, help="SIP username")
    outbound_parser.add_argument("--password", required=True, help="SIP password")

    args = parser.parse_args()

    if args.command == "inbound":
        set_up_inbound_trunking(
            args.phone_number, nickname=f"phone-call-inbound-{args.phone_number}"
        )
    elif args.command == "outbound":
        set_up_outbound_trunking(
            args.phone_number,
            args.sip_trunk_uri,
            args.username,
            args.password,
            nickname=f"phone-call-outbound-{args.phone_number}",
        )
