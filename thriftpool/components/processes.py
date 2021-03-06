"""Manage process pool."""
from __future__ import absolute_import

import logging
import sys
import struct
import cPickle as pickle

from thriftworker.utils.loop import in_loop
from thriftworker.utils.mixin import LoopMixin
from thriftpool.utils.mixin import LogsMixin

from .base import StartStopComponent
from .proto import Producer

logger = logging.getLogger(__name__)


class ProcessManager(LogsMixin, LoopMixin):

    process_name = 'worker'
    gevent_monkey = 'from gevent.monkey import patch_all; patch_all();'
    script = 'from thriftpool.bin.thriftworker import main; main();'

    def __init__(self, app, manager, listeners):
        self.app = app
        self.manager = manager
        self.listeners = listeners
        self.producers = {}
        self.running = False
        super(ProcessManager, self).__init__()

    def _create_arguments(self):
        worker_type = self.app.config.WORKER_TYPE
        if worker_type == 'gevent':
            startup_line = '{0} {1}'.format(self.gevent_monkey, self.script)
        elif worker_type == 'sync':
            startup_line = self.script
        else:
            raise NotImplementedError()
        args = ['-c', '{0}'.format(startup_line)]
        return dict(cmd=sys.executable, args=args,
                    redirect_output=['out', 'err'],
                    custom_streams=['control'],
                    custom_channels=self.listeners.channels,
                    redirect_input=True)

    def _create_producer(self, process):
        stream = process.streams['control']
        producer = self.producers[process.id] = Producer(self.loop, stream, process)
        producer.start()
        return producer

    def _on_io(self, evtype, msg):
        stream = evtype == 'err' and sys.stderr or sys.stdout
        stream.write(msg['data'])

    def _initialize_process(self, process):
        process.monitor_io('.', self._on_io)
        message = pickle.dumps(self.app)
        message = struct.pack('I', len(message)) + message
        process.write(message)
        producer = self._create_producer(process)
        producer.apply('change_title', args=['[thriftworker-{0}]'.format(process.id)])
        producer.apply('register_acceptors', args=[self.listeners.descriptors])

    def _on_event(self, evtype, msg):
        if not self.running:
            return
        if evtype == 'spawn':
            self._info('Process %d spawned!', msg['pid'])
            process = self.manager.get_process(msg['pid'])
            self._initialize_process(process)
        elif evtype == 'exit':
            self._critical('Process %d exited!', msg['pid'])
            producer = self.producers.pop(msg['pid'])
            producer.stop()

    @in_loop
    def start(self):
        self.running = True
        manager = self.manager
        manager.subscribe('.', self._on_event)
        manager.add_process(self.process_name,
                            numprocesses=self.app.config.WORKERS,
                            **self._create_arguments())
        manager.start()

    @in_loop
    def _real_stop(self):
        self.running = False
        is_stopped = self.app.env.RealEvent()
        for producer in self.producers.values():
            producer.stop()
        self.producers = {}
        stop_callback = lambda *args: is_stopped.set()
        self.manager.stop(stop_callback)
        return is_stopped

    def stop(self):
        is_stopped = self._real_stop()
        is_stopped.wait(5.0)
        if not is_stopped.is_set():
            logger.error('Timeout when stopping processes.')

    def apply(self, method_name, callback=None, args=None, kwargs=None):
        """Run given method across all processes."""
        for producer in self.producers.values():
            producer.apply(method_name, callback, args, kwargs)


class ProcessManagerComponent(StartStopComponent):

    name = 'manager.process_manager'
    requires = ('loop', 'listeners')

    def create(self, parent):
        return ProcessManager(parent.app, parent.manager, parent.listeners)
