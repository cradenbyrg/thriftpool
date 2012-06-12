import yep
from base import factory
from setproctitle import setproctitle
from gevent.greenlet import Greenlet


def main():
    device = factory.Device()
    device.start()

    server = factory.Server(('localhost', 9090))
    Greenlet(server.stop).start_later(60)
    server.serve_forever()


if __name__ == '__main__':
    setproctitle('[server]')
    #yep.start('server.prof')
    main()
    #yep.stop()
    #import cProfile
    #cProfile.runctx("main()", globals(), locals(), "server.prof")
