import socket
import json
import argparse


class CGMinerCollector(object):
    keys = ['temps', 'hashrates']

    def __init__(self, port=4028, address='127.0.0.1'):
        self.port = port
        self.address = address

    def collect(self, key):
        if key not in self.keys:
            raise NotImplementedError

        return getattr(self, 'call_' + key)()

    def call(self, command, params=None):
        sok = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sok.connect(("", self.port))
        sok.send('{"command":"' + command + '"}')
        data = sok.makefile().readline()[:-1]
        retval = json.loads(data)
        sok.close()
        return retval

    def call_temp(self):
        data = self.call('devs')
        if 'DEVS' not in data:
            raise Exception()

        return [d.get('Temperature') for d in data['DEVS']]

    def call_hashrate(self):
        data = self.call('devs')
        if 'DEVS' not in data:
            raise Exception()

        return [d.get('MHS av') for d in data['DEVS']]

def entry():
    parser = argparse.ArgumentParser(prog='ppagent')
    parser.add_argument('-l',
                        '--log-level',
                        choices=['DEBUG', 'INFO', 'WARN', 'ERROR'],
                        default='ERROR')
    subparsers = parser.add_subparsers(title='main subcommands', dest='action')

    push = subparsers.add_parser('call', help='manually fetch a key')
    args = parser.parse_args()
    coll = CGMinerCollector()
    print coll.call_temp()
    print coll.call_hashrate()
