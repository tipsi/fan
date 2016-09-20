import logging


class Caller:
    log = logging.getLogger('Caller')

    def __init__(self, context, name):
        self.context = context
        self.call_path = [name]

    def __getattr__(self, name):
        self.call_path.append(name)
        return self

    def __call__(self, *args, **kwargs):
        self.log.debug('Generate call: {} {} {}'.format(self.call_path, args, kwargs))
        endpoint = self.context.discovery.find_endpoint(tuple(self.call_path[:-1]))
        self.log.debug('RPCEndpoint: {}'.format(endpoint))
        if endpoint:
            try:
                self.context.pre_call()
                method_name = self.call_path[-1]
                return endpoint.perform_call(self.context, method_name, *args, **kwargs)
            finally:
                self.context.post_call()


class RPC:
    def __init__(self, context):
        self.context = context

    def __getattr__(self, name):
        return Caller(self.context, name)
