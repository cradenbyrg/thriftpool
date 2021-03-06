from __future__ import absolute_import

import logging

from thriftpool.components.base import StartStopComponent
from thriftpool.utils.mixin import LogsMixin

logger = logging.getLogger(__name__)


class ServicesComponent(LogsMixin, StartStopComponent):

    name = 'worker.services'

    def create(self, parent):
        services = parent.app.thriftworker.services
        for slot in parent.app.slots:
            self._debug("Register service '%s'.", slot.name)
            services.register(slot.name, slot.service.processor)
