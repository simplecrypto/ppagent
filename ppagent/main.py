import socket
import json
import argparse
import os
import logging
import sys
import collections
import yaml
import time

from pprint import pformat
from os.path import expanduser


logger = logging.getLogger("ppagent")
config_home = expanduser("~/.ppagent/")

ch = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)


class WorkerNotFound(Exception):
    pass


miner_defaults = {
    'CGMiner': {
        'port': 4028,
        'address': '127.0.0.1',
        'collectors': {
            'status': {
                'enabled': True,
                'temperature': True,
                'mhps': True,
                'interval': 60
            }
        }
    }
}


class Miner(object):
    """ Represents one mining client. Currently only implementation is CGMiner,
    but in the future other miners could be interfaced with. """

    def __init__(self):
        """ Recieves a dictionary of arguments defined in the miner declaration
        """
        raise NotImplementedError

    def collect(self):
        """ Called at regular intervals to collect information. Should return a
        list of dictionaries that get passed serialized to pass to the
        powerpool collector. Should manage it's only scheduling. """
        raise NotImplementedError


class CGMiner(Miner):
    keys = ['temps', 'hashrates']
    valid_collectors = ['status']

    def __init__(self, collectors, remotes, port=4028, address='127.0.0.1'):
        self.port = port
        self.remotes = remotes
        self.address = address
        # filter our disabled collectors
        self.collectors = {k: v for (k, v) in collectors.items()
                           if v.get('enabled', False)}

        self._worker = None
        self.queue = []
        self.authenticated = False

    def test(self):
        pass

    def reset_timers(self):
        now = int(time.time())
        for coll in self.collectors.values():
            interval = coll['interval']
            coll['next_run'] = ((now // interval) * interval)

    @property
    def worker(self):
        if self._worker is None:
            self._worker = self.fetch_username()
        return self._worker

    def collect(self):
        # trim queue to keep it from growing infinitely while disconnected
        self.queue = self.queue[:10]

        now = int(time.time())
        # if it's time to run, and we have status defined
        if ('status' in self.collectors or
                'temp' in self.collectors or
                'hashrate' in self.collectors):
            ret = self.call_devs()
            mhs, temps = ret

        if 'status' in self.collectors and now >= self.collectors['status']['next_run']:
            conf = self.collectors['status']
            string = ""
            # if it failed to connect we should just skip collection
            if ret is None:
                return
            if conf['temperature']:
                for i, temp in enumerate(temps):
                    string += "GPU {} Temp: {}C\n".format(i, temp)
            if conf['mhps']:
                for i, mh in enumerate(mhs):
                    string += "GPU {} 5s: {} MH/s\n".format(i, mh)
            self.queue.append([self.worker, 'status', string, int(time.time())])

            # set the next time it should run
            conf['next_run'] += conf['interval']

    def call(self, command, params=None):
        sok = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sok.connect((self.address, self.port))
        try:
            sok.send('{"command":"' + command + '"}')
            data = sok.makefile().readline()[:-1]
            retval = json.loads(data)
        except socket.error:
            self._worker = None
            self.authenticated = False
            return None
        finally:
            sok.close()
        return retval

    def fetch_username(self):
        data = self.call('pools')
        for pool in data['POOLS']:
            if pool['Stratum URL'] in self.remotes:
                return pool['User']
        raise WorkerNotFound("Unable to find worker in pool connections")

    def call_devs(self):
        data = self.call('devs')
        if 'DEVS' not in data:
            raise Exception()

        temps = [d.get('Temperature') for d in data['DEVS']]
        mhs = [d.get('MHS 5s') for d in data['DEVS']]
        return mhs, temps


class AgentSender(object):
    """ Managed interfacing with PowerPool server for relaying information """
    def __init__(self, miners, address='127.0.0.1', port=4444):
        self.address = address
        self.port = port
        self.miners = miners
        self.conn = None

    def connect(self):
        logger.debug("Opening connection to agent server...")
        conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        conn.connect((self.address, self.port))
        self.conn = conn.makefile()
        self.conn.write(json.dumps({'method': 'hello', 'params': [0.1]}) + "\n")
        self.conn.flush()

    def reset_connection(self):
        logger.info("Disconnected from remote.")
        self.conn = None
        # reauth required upon connection error
        for miner in self.miners:
            miner.authenticated = False

    def send(self, data):
        logger.debug("Sending {} to server".format(data))
        try:
            if self.conn is None:
                self.connect()
            self.conn.write(json.dumps(data) + "\n")
            self.conn.flush()
        except (socket.error, Exception):
            self.reset_connection()
            raise

    def recieve(self):
        recv = self.conn.readline(4096)
        if len(recv) > 4000:
            raise Exception("Server returned too large of a string")
        logger.debug("Recieved response from server {}".format(recv.strip()))
        if not recv:
            self.reset_connection()
            return None
        return json.loads(recv)

    def loop(self):
        try:
            while True:
                self.transmit()
                time.sleep(1)
        except KeyboardInterrupt:
            logging.info("Shutting down daemon from sigint...")

    def transmit(self):
        # accumulate values to send
        for miner in self.miners:
            if miner.authenticated is False:
                try:
                    username = miner.worker
                except WorkerNotFound:
                    logger.info("Miner not connected to valid pool")
                    continue
                except Exception:
                    logger.info("Unable to connect to miner")
                    continue

                logger.debug("Attempting to authenticate {}".format(username))
                data = {'method': 'worker.authenticate',
                        'params': [username, ]}
                try:
                    self.send(data)
                except Exception:
                    logger.debug("Failed to communicate with server")
                    time.sleep(5)
                    continue

                retval = self.recieve()
                if retval['error'] is None:
                    logger.info("Successfully authenticated {}".format(username))
                    miner.authenticated = True
                    miner.reset_timers()
                else:
                    logger.debug(
                        "Failed to authenticate worker {}, server returned {}."
                        .format(username, retval))

            if miner.authenticated is True:
                miner.collect()
            else:
                # don't distribute if we're not authenticated...
                continue

            # send all our values that were accumulated
            sent = []
            for i, value in enumerate(miner.queue):
                try:
                    send = {'method': 'stats.submit', 'params': value}
                    logger.info("Transmiting new stats: {}".format(send))
                    self.send(send)
                except Exception:
                    logger.warn(
                        "Unable to send to remote, probably down temporarily.")
                    time.sleep(5)
                else:
                    # try to get a response from the server. if we fail to
                    # recieve, just wait till next loop to send
                    ret = self.recieve()
                    if ret is None or ret.get('error', True) is not None:
                        logger.warn("Recieved failure result from the server!")
                    else:
                        sent.append(i)

            # remove the successfully sent values
            for i in sent:
                del miner.queue[i]


def entry():
    parser = argparse.ArgumentParser(prog='ppagent')
    parser.add_argument('-l',
                        '--log-level',
                        choices=['DEBUG', 'INFO', 'WARN', 'ERROR'],
                        default='WARN')
    parser.add_argument('-a',
                        '--address',
                        default='agent.simpledoge.com')
    parser.add_argument('-p',
                        '--port',
                        type=int,
                        default=4444)
    subparsers = parser.add_subparsers(title='main subcommands', dest='action')

    subparsers.add_parser('call', help='manually fetch a key')
    args = parser.parse_args()
    configs = vars(args)

    # rely on command line log level until we get all configs parsed
    ch.setLevel(getattr(logging, args.log_level))
    logger.setLevel(getattr(logging, args.log_level))

    # make a configuration directory, fail if we cannot make it
    try:
        os.makedirs(config_home)
        logger.debug("Config created")
    except OSError as e:
        if e.errno != 17:
            logger.error("Failed to create toroidal configuration directory")
            exit(1)
        logger.debug("Config directory already created")

    # setup or load our configuration file
    try:
        file_configs = yaml.load(open(config_home + "config.yml"))
        logger.debug("Loaded JSON config file")
    except (IOError, OSError):
        logger.debug("JSON configuration file doesn't exist.. Creating empty one")
        with open(config_home + "config.yml", 'w') as f:
            f.write("{}")
        file_configs = {}

    # setup our collected configs by recursively overriding
    def update(d, u):
        """ Simple recursive dictionary update """
        for k, v in u.iteritems():
            if isinstance(v, collections.Mapping):
                r = update(d.get(k, {}), v)
                d[k] = r
            else:
                d[k] = u[k]
        return d

    # do some processing on the config file
    miners = []
    for section in file_configs:
        title = section.keys()[0]
        content = section.values()[0]
        # process a miner directive
        if title == "miner":
            typ = content.pop('type', 'CGMiner')
            kwargs = {}
            # apply defaults, followed by overriding with config options
            update(kwargs, miner_defaults[typ])
            update(kwargs, content)
            kwargs['remotes'] = [configs['address']]
            # init the miner class with the configs
            miners.append(globals()[typ](**kwargs))
        elif title == "daemon":
            configs.update(content)

    # set our logging level based on the configs
    ch.setLevel(getattr(logging, configs['log_level']))
    logger.setLevel(getattr(logging, configs['log_level']))
    logger.debug(configs)

    sender = AgentSender(miners, configs['address'], configs['port'])
    sender.loop()
