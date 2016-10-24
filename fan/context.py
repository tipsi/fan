from fan.rpc import RPC
from fan.service import Service


class Context:
    def __init__(self, discovery, service=None, parent=None, name=None):
        self.discovery = discovery
        if service:
            assert isinstance(service, Service), service
        self.service = service
        self.parent = parent

        if isinstance(parent, Context):
            parent_context = parent.span.context
        else:
            parent_context = parent
        self.span = discovery.tracer.start_span(child_of=parent_context,
                                                operation_name=name)
        self._entered = False

    def create_child_context(self, name=None):
        return Context(self.discovery, self.service, self, name)

    @property
    def rpc(self):
        '''
        if you generate totally new context, you must enter it before use:
        >>> with new_ctx:
               # now you may call new_ctx.rpc
               new_ctx.rpc.some_endpoint.ping()
        for most services it would be started when accepting incoming request in RemoteEndpoint,
        so you should not do that in services
        '''
        assert self._entered, 'You must enter context before call .rpc'
        return RPC(self)

    def pre_call(self):
        pass

    def post_call(self):
        self.span.finish()

    def __enter__(self, *args):
        self._entered = True
        self.pre_call()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.span.set_tag('error', '{} {}'.format(exc_type, exc_val))
        self.post_call()
