import json
import aiohttp
import asyncio
from pprint import pformat

green = '\033[92m'
red = '\033[91m'
end = '\033[0m'

async def connect_websocket(session):
    async with session.ws_connect('ws://127.0.0.1:8080/ws') as ws:
        message = {'id': 1, 'type': 'subscribe', 'addresses': ['DU9DDSX9JOSPNFDTBCHYMLXTSB9YWIJTZZ9OMQSKUEMCGSCOVTXIQAH9WRCMGNVFCSUHPZWYLJZVCMGLA']}
        print(green, pformat(message), end)
        await ws.send_json(message)
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                response = json.loads(msg.data)
                print(red, pformat(response), end)
            elif msg.type == aiohttp.WSMsgType.ERROR:
                break

async def main():
    async with aiohttp.ClientSession(loop=loop) as session:
        await asyncio.wait([
            connect_websocket(session),
        ])

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
