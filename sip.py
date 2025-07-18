import asyncio
import logging
from dotenv import load_dotenv
from livekit.api import (
    LiveKitAPI,
    SIPInboundTrunkInfo,
    CreateSIPInboundTrunkRequest,
    CreateSIPDispatchRuleRequest,
    SIPDispatchRule,
    SIPDispatchRuleIndividual,
)
from livekit.protocol.sip import CreateSIPOutboundTrunkRequest, SIPOutboundTrunkInfo

logger = logging.getLogger("sip")
file_handler = logging.FileHandler("sip.log")
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

load_dotenv()


def create_sip_inbound_trunk(
    number: str,
    nickname: str,
    krisp_enabled: bool = True,
):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        results = loop.run_until_complete(
            _create_sip_inbound_trunk_and_dispatch_rule(nickname, number, krisp_enabled)
        )
    finally:
        loop.close()
    return results


async def _create_sip_inbound_trunk_and_dispatch_rule(
    nickname: str,
    number: str,
    krisp_enabled: bool = True,
):

    try:
        livekit_api = LiveKitAPI()
        trunk = SIPInboundTrunkInfo(
            name=nickname,
            numbers=[number],
            krisp_enabled=krisp_enabled,
        )
        request = CreateSIPInboundTrunkRequest(trunk=trunk)
        trunk = await livekit_api.sip.create_sip_inbound_trunk(request)
        logger.info(f"SIP inbound trunk created: {trunk}")

    except Exception as e:
        logging.exception("Error creating SIP inbound trunk: %s", e)
        return {"success": False, "error": str(e)}
    finally:
        await livekit_api.aclose()

    try:
        livekit_api = LiveKitAPI()
        request = CreateSIPDispatchRuleRequest(
            rule=SIPDispatchRule(
                dispatch_rule_individual=SIPDispatchRuleIndividual(
                    room_prefix=f"phone-call-inbound-{number}",
                ),
            ),
            trunk_ids=[trunk.sip_trunk_id],
            name=nickname,
        )
        dispatch = await livekit_api.sip.create_sip_dispatch_rule(request)
        return {
            "success": True,
            "sip_trunk_id": trunk.sip_trunk_id,
            "sip_dispatch_rule_id": dispatch.sip_dispatch_rule_id,
        }
    except Exception as e:
        logging.exception("Error creating SIP dispatch rule: %s", e)
        return {"success": False, "error": str(e)}
    finally:
        await livekit_api.aclose()


def create_sip_outbound_trunk(
    nickname: str,
    termination_uri: str,
    auth_username: str,
    auth_password: str,
    numbers: list,
):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    results = loop.run_until_complete(
        _async_create_sip_outbound_trunk(
            nickname,
            termination_uri,
            auth_username,
            auth_password,
            numbers,
        )
    )
    loop.close()
    return results


async def _async_create_sip_outbound_trunk(
    nickname: str,
    termination_uri: str,
    auth_username: str,
    auth_password: str,
    number: str,
):
    try:
        livekit_api = LiveKitAPI()
        try:
            trunk = SIPOutboundTrunkInfo(
                name=nickname,
                address=termination_uri,
                numbers=[number],
                auth_username=auth_username,
                auth_password=auth_password,
            )
            request = CreateSIPOutboundTrunkRequest(trunk=trunk)
            trunk = await livekit_api.sip.create_sip_outbound_trunk(request)
            return {
                "success": True,
                "sip_trunk_id": trunk.sip_trunk_id,
            }

        except Exception as e:
            logging.exception("Error creating SIP outbound trunk: %s", e)
            return {"success": False, "error": str(e)}

        finally:
            await livekit_api.aclose()

    except Exception as e:
        logging.exception("Error creating SIP outbound trunk: %s", e)
        return {"success": False, "error": str(e)}
