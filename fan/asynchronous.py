"""
Shortlived async helpers. Primary target is creating short-lived fast context with get_context
"""

import asyncio
import logging
import os
import socket
import time

import aiohttp
from basictracer import BasicTracer
from basictracer.span import BasicSpan
from py_zipkin.thrift import create_span, thrift_objs_in_bytes

from fan.context import AsyncContext
from fan.contrib.aio.discovery import LazyAiozkDiscovery
from fan.sync import BaseFanRecorder
from fan.transport import AsyncHTTPTransport, HTTPPropagator
from fan.utils import async_cache

discovery = None
tracer = None
ZIPKIN = os.environ.get('ZIPKIN')
ZIPKIN_TIMEOUT = 10  # Timeout to send span to zipkin over http


async def async_http_transport(encoded_span):
    # Adapted from: https://github.com/Yelp/py_zipkin#transport
    # The collector expects a thrift-encoded list of spans. Instead of
    # decoding and re-encoding the already thrift-encoded message, we can just
    # add header bytes that specify that what follows is a list of length 1.
    timeout = aiohttp.ClientTimeout(total=ZIPKIN_TIMEOUT)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            url = 'http://{}/api/v1/spans'.format(ZIPKIN)
            headers = {'Content-Type': 'application/x-thrift'}
            async with session.post(url, data=encoded_span, headers=headers) as resp:
                await resp.read()
                # TODO: [TRACING] Check response status
    except asyncio.TimeoutError as e:
        log.warning('Failed to send span to zipkin. Timeout occurred.')


MY_IP = socket.gethostbyname(socket.gethostname())
EP = None
log = logging.getLogger('fan.async')


# TODO: [TRACING] Logging refactoring
async def logger_log_span(span_id, parent_span_id, trace_id, span_name, annotations,
                          binary_annotations, **kwargs):
    log.info('Log span: {}'.format(locals()))


async def async_zipkin_log_span(span_id, parent_span_id, trace_id, span_name, annotations,
                                binary_annotations, timestamp_s, duration_s, **kwargs):
    span = create_span(span_id, parent_span_id, trace_id, span_name, annotations,
                       binary_annotations, timestamp_s, duration_s)
    await async_http_transport(thrift_objs_in_bytes([span]))

    params = {'timestamp_s': timestamp_s, 'duration_s': duration_s, **kwargs}
    # TODO: [TRACING] Log in parsable format
    await logger_log_span(span_id, parent_span_id, trace_id, span_name, annotations,
                          binary_annotations, **params)


class AsyncFanRecorder(BaseFanRecorder):
    async def record_span(self, span):
        await self.log_span(**self.span_params(span, async_http_transport))
        return super().record_span(span)


class AsyncSpan(BasicSpan):
    async def finish(self, finish_time=None):
        # TODO: [TRACING] Do we need thread safe code
        finish = time.time() if finish_time is None else finish_time
        self.duration = finish - self.start_time
        await self._tracer.record(self)


class AsyncTracer(BasicTracer):
    def start_span(self,
                   operation_name=None,
                   child_of=None,
                   references=None,
                   tags=None,
                   start_time=None):
        # TODO: [TRACING] Think about copying logic from BasicTracer
        span = super().start_span(operation_name, child_of, references, tags, start_time)
        return AsyncSpan(
            self,
            span.operation_name,
            span._context,
            span.parent_id,
            span.tags,
            span.start_time,
        )

    async def record(self, span):
        await self.recorder.record_span(span)


def get_async_tracer(name=None):
    global tracer
    if tracer:
        return tracer
    if not name:
        name = 'no_name'

    if ZIPKIN:
        log_span = async_zipkin_log_span
    else:
        log_span = logger_log_span
    recorder = AsyncFanRecorder(name, log_span)
    tracer = AsyncTracer(recorder)
    return tracer


@async_cache
async def get_discovery(name=None, loop=None):
    discovery = LazyAiozkDiscovery(
        os.environ.get('ZK_HOST', 'zk'),
        os.environ.get('ZK_CHROOT', '/'),
        with_data_watcher=False,
        loop=loop)
    discovery.transport_classes = {
        'http': AsyncHTTPTransport,
    }

    discovery.tracer = get_async_tracer(name)
    discovery.tracer.register_propagator('http', HTTPPropagator())
    return discovery


async def get_context(name=None, service_name=None, loop=None):
    if not service_name and name:
        service_name = name
    discovery = await get_discovery(name=service_name, loop=loop)
    return AsyncContext(discovery, name=name)