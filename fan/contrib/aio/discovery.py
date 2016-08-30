import asyncio

from aiozk import ZKClient

from fan.discovery import CompositeDiscovery, RemoteDiscovery
from fan.contrib.aio.remote import AIOProxyEndpoint


async def tornado_result(future):
    q = asyncio.Queue()

    def _inner(result):
        q.put(result)
    future.add_done_callback(_inner)
    return await q.get()


class ZKDiscovery(RemoteDiscovery):
    def __init__(self, zk_path):
        super().__init__()
        self.zk = ZKClient(zk_path)

    async def on_start(self):
        await self.zk.start()

    def register(self, path, config):
        pass

    def find_endpoint(self, service_name):
        pass

    def watch(self, path, callback):
        pass

    def unwatch(self, path, callback):
        pass


class AIOCompositeDiscovery(CompositeDiscovery):
    def create_proxy(self, name, proxy_cfg):
        return AIOProxyEndpoint(self, name, proxy_cfg)