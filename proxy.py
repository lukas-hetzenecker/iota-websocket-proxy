import os
import json
from collections import namedtuple
from typing import Dict, List

import aiohttp
from aiohttp import web
import asyncio
import zmq
from aiohttp.web_app import Application
from zmq.asyncio import Context
from iota import Transaction

IOTA_HOST = os.environ.get('IOTA_HOST', '127.0.0.1')
IOTA_IRI_PORT = int(os.environ.get('IRI_PORT', '14265'))
IOTA_ZMQ_PORT = int(os.environ.get('ZMQ_PORT', '5556'))

IOTA_URL = 'http://%s:%s' % (IOTA_HOST, IOTA_IRI_PORT)


class emptylistdict(dict):
    def __missing__(self, key):
        return []  # note, does *not* set self[key]

Subscription = namedtuple('Subscription', ['connection', 'address', 'id'])


class ActiveConnection:
    def __init__(self, ws):
        self.websocket = ws
        self.subscriptions = []

    def subscribe(self, subscription):
        print('subscribe', subscription)
        if subscription.address not in connection_addresses:
            connection_addresses[subscription.address] = list()
        connection_addresses[subscription.address].append(subscription)
        self.subscriptions.append(subscription)

    def unsubscribe(self, id_):
        subscriptions = filter(lambda s: s.id == id_, self.subscriptions)
        for subscription in subscriptions:
            connection_addresses.get(subscription.address, []).remove(subscription)
            self.subscriptions.remove(subscription)

    def disconnect(self):
        #map(lambda subscription: connection_addresses.get(subscription.address, []).remove(subscription), self.subscriptions)
        for subscription in self.subscriptions:
            connection_addresses.get(subscription.address, []).remove(subscription)


websocket_connections = list()
connection_addresses: Dict[str, List[Subscription]] = dict() #emptylistdict()

async def zmq_iota_recv():
    ctx = Context.instance()
    print("Connecting to ZMQ...")
    s = ctx.socket(zmq.SUB)
    s.connect('tcp://%s:%s' % (IOTA_HOST, IOTA_ZMQ_PORT))
    print("Subscribing to tx_trytes...")
    s.subscribe(b"tx_trytes")
    while True:
        msg = await s.recv()
        #print('received', msg)
        topic, data, hash_ = msg.split(b' ')
        str_data = data.decode('ascii')
        str_hash = hash_.decode('ascii')

        tx = Transaction.from_tryte_string(data, hash_)

        print(str(tx.address), connection_addresses.get(str(tx.address), []), repr(connection_addresses))
        tasks = [send_json(subscription.connection, {'id': subscription.id, 'type': 'transaction', 'data': str_data,
                                                     'hash': str_hash})
                 for subscription in connection_addresses.get(str(tx.address), [])]
        if tasks:
            await asyncio.wait(tasks)
    s.close()

async def send_json(connection: ActiveConnection, message):
    try:
        await connection.websocket.send_json(message)
    except ConnectionError:
        connection.disconnect()
        pass

async def handle(request):
    name = request.match_info.get('name', "Anonymous")
    text = "Hello, " + name
    return web.Response(text=text)

async def find_transactions(address: str, subscription: Subscription):
    headers = {'X-IOTA-API-Version': '1'}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.post(IOTA_URL, json={"command": "findTransactions", "addresses": [address]}) as hashes_response:
            hashes_data = await hashes_response.json()
            hashes = hashes_data['hashes']
            async with session.post(IOTA_URL, json={"command": "getTrytes", "hashes": hashes}) as trytes_response:
                trytes_data = await  trytes_response.json()
                print(trytes_data)
                trytes = trytes_data['trytes']
                print(trytes)
                for i, tryte in enumerate(trytes):
                    await send_json(subscription.connection, {'id': subscription.id, 'type': 'transaction',
                                                              'data': tryte, 'hash': hashes[i]})


async def websocket_handler(request):
    print('got websocket request!', request)
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    connection = ActiveConnection(ws)
    websocket_connections.append(connection)

    async for msg in ws:
        print(msg)
        if msg.type == aiohttp.WSMsgType.TEXT:
            data = json.loads(msg.data)
            if 'id' not in data:
                await send_json(connection, {'error': 'missing id argument'})
                break
            if 'type' not in data:
                await send_json(connection, {'error': 'missing type argument'})
                break
            id_ = data['id']
            if data['type'] == 'subscribe':
                for address in data.get('addresses', []):
                    subscription = Subscription(connection, address, id_)
                    connection.subscribe(subscription)
                    # get already published messages...
                    await find_transactions(address, subscription)
            elif data['type'] == 'unsubscribe':
                connection.unsubscribe(id_)
        elif msg.type == aiohttp.WSMsgType.ERROR:
            print('ws connection closed with exception %s' %
                  ws.exception())
            break
        elif msg.type == aiohttp.WSMsgType.CLOSE:
            print('websocket connection closed')
            break

    connection.disconnect()

    print('websocket connection closed')

    return ws

async def start_background_tasks(app):
    app.loop.create_task(zmq_iota_recv())

app = web.Application()
app.on_startup.append(start_background_tasks)

app.add_routes([web.get('/', handle)])
app.add_routes([web.get('/ws', websocket_handler)])
web.run_app(app)
