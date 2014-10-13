import socket
import json
import argparse
import os
import logging
import sys
import collections
import time
import traceback

from urlparse import urlparse
from string import Template
from os.path import expanduser

version = '0.3.5'

logger = logging.getLogger("ppagent")
config_home = expanduser("~/.ppagent/")

ch = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

def excepthook(ex_cls, ex, tb):
    logging.critical(''.join(traceback.format_tb(tb)))
    logging.critical('{0}: {1}'.format(ex_cls, ex))
    easy_exit(1)
sys.excepthook = excepthook

default_config = '''[
    {"miner":
        {
            "type": "CGMiner"
        }
    }
]'''


class WorkerNotFound(Exception):
    pass


def easy_exit(code=0):
    """ A helper to prevent the window from closing rapidly on Windows """
    if sys.platform == "win32":
        raw_input("Press any key to continue...")
    exit(code)


class Miner(object):
    """ Represents one mining client. Currently only implementation is CGMiner,
    but in the future other miners could be interfaced with. """

    def __init__(self):
        """ Receives a dictionary of arguments defined in the miner declaration
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
    defaults = {
        'port': 4028,
        'address': '127.0.0.1',
        'collectors': {
            'status': {
                'enabled': True,
                'temperature': True,
                'mhps': True,
                'details': True,
                'interval': 60
            },
            'temp': {
                'enabled': True,
                'interval': 60
            },
            'hashrate': {
                'enabled': True,
                'interval': 60
            }
        }
    }

    def __init__(self, collectors, remotes, thresholds=None, port=4028,
                 address='127.0.0.1'):
        self.thresholds = thresholds or {}
        self.port = port
        self.remotes = remotes
        self.address = address
        # filter our disabled collectors
        self.collectors = dict((k, v) for (k, v) in collectors.items()
                               if v.get('enabled', False))

        self._worker = None
        self.queue = []
        self.authenticated = False
        self.last_devs = []
        self.sent_thresholds = False

    def reset(self):
        """ Called when connection to the miner is lost for some reason """
        self.last_devs = []
        self._worker = None
        self.authenticated = False
        self.sent_thresholds = False

    def reset_timers(self):
        now = int(time.time())
        for coll in self.collectors.values():
            interval = coll['interval']
            coll['next_run'] = ((now // interval) * interval) + interval

    @property
    def worker(self):
        if self._worker is None:
            self._worker = self.fetch_username()
        return self._worker

    def collect(self):
        # trim queue to keep it from growing infinitely while disconnected
        self.queue = self.queue[:10]
        now = int(time.time())

        if self.sent_thresholds is False:
            self.queue.append([self.worker, 'thresholds', self.thresholds, now])
            self.sent_thresholds = True

        mhs = []
        # if it's time to run, and we have status defined
        if ('status' in self.collectors or
            'temp' in self.collectors or
            'hashrate' in self.collectors) and now >= self.collectors['status']['next_run']:
            mhs, temps, details = self.call_devs()

        if 'status' in self.collectors and now >= self.collectors['status']['next_run']:
            conf = self.collectors['status']
            gpus = [{} for _ in temps]
            output = {"type": "cgminer", "gpus": gpus, "pool": self.pool_stat()}
            # if it failed to connect we should just skip collection
            if details is None:
                return
            if conf['temperature']:
                for i, temp in enumerate(temps):
                    output['gpus'][i]['temp'] = temp
            if conf['mhps']:
                for i, mh in enumerate(mhs):
                    output['gpus'][i]['hash'] = mh
            if conf['details']:
                for i, det in enumerate(details):
                    output['gpus'][i].update(det)
            output['v'] = version
            self.queue.append([self.worker, 'status', output, now])

            # set the next time it should run
            conf['next_run'] += conf['interval']

        if 'temp' in self.collectors and now >= self.collectors['temp']['next_run']:
            conf = self.collectors['temp']
            self.queue.append([self.worker, 'temp', temps, now])

            # set the next time it should run
            conf['next_run'] += conf['interval']

        if mhs and 'hashrate' in self.collectors and now >= self.collectors['hashrate']['next_run']:
            conf = self.collectors['hashrate']
            self.queue.append([self.worker, 'hashrate', mhs, now])

            # set the next time it should run
            conf['next_run'] += conf['interval']

    def call(self, command, params=None):
        sok = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sok.connect((self.address, self.port))
        sok.settimeout(5)
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

    def pool_stat(self):
        data = self.call('pools')
        for pool in data['POOLS']:
            if pool['Stratum URL'] in self.remotes:
                return pool
        return {}

    def fetch_username(self):
        data = self.call('pools')
        for pool in data['POOLS']:
            if pool['Stratum URL'] in self.remotes:
                return pool['User']
        raise WorkerNotFound("Unable to find worker in pool connections")

    def fetch_pool(self):
        data = self.call('pools')
        try:
            return urlparse(data['POOLS'][0]['URL'])
        except KeyError:
            raise Exception("cgminer not connected to any pools")

    def call_devs(self):
        """ Retrieves and parses device information from cgminer """
        data = self.call('devs')
        if 'DEVS' not in data:
            raise Exception()

        temps = [d.get('Temperature') for d in data['DEVS']]
        details = []
        for d in data['DEVS']:
            details.append(dict((k, v) for k, v in d.iteritems()
                                if k != 'Temperature'))
        # we store the last total megahashes internally and report the
        # difference since last run, as opposed to reporting cgminers avg
        # megahash or 5s megahash
        if self.last_devs and len(self.last_devs) == len(data['DEVS']):
            diff = time.time() - self._last_dev
            mhs = [round((now['Total MH'] - last['Total MH']) / diff, 3)
                   for now, last in zip(data['DEVS'], self.last_devs)]
        else:
            mhs = []
        self._last_dev = time.time()
        self.last_devs = data['DEVS']
        return mhs, temps, details


class MockCGMiner(CGMiner):
    def collect(self):
        now = int(time.time())
        self.queue.append([self.worker, 'temp', [12, 15, 18], now])
        self.queue.append([self.worker, 'hashrate', [12, 15, 18], now])
        self.queue.append([self.worker, 'status', {"test": "other"}, now])

    def call(self, command, params=None):
        if command == "devs":
            return json.loads('{"gpus": [{"Difficulty Accepted": 410112.0, "Difficulty Rejected": 512.0, "GPU Voltage": 1.2, "GPU Clock": 1070, "Fan Speed": 2482, "GPU Activity": 99, "Status": "Alive", "Device Rejected%": 0.1247, "Fan Percent": 100, "Rejected": 2, "Memory Clock": 1500, "Hardware Errors": 0, "Accepted": 1492, "Last Share Pool": 0, "Diff1 Work": 410653, "hash": 0.381, "Total MH": 28107.5384, "Enabled": "Y", "Device Elapsed": 73201, "Device Hardware%": 0.0, "Last Valid Work": 1409019675, "Last Share Time": 1409019675, "GPU": 0, "MHS av": 0.38, "MHS 5s": 0.38, "temp": 66.0, "Last Share Difficulty": 256.0, "Intensity": "0", "Powertune": -20, "Utility": 1.22}, {"Difficulty Accepted": 425728.0, "Difficulty Rejected": 1536.0, "GPU Voltage": 1.2, "GPU Clock": 1070, "Fan Speed": 2847, "GPU Activity": 99, "Status": "Alive", "Device Rejected%": 0.3579, "Fan Percent": 100, "Rejected": 6, "Memory Clock": 1500, "Hardware Errors": 0, "Accepted": 1573, "Last Share Pool": 0, "Diff1 Work": 429141, "hash": 0.384, "Total MH": 28105.474, "Enabled": "Y", "Device Elapsed": 73201, "Device Hardware%": 0.0, "Last Valid Work": 1409019755, "Last Share Time": 1409019755, "GPU": 1, "MHS av": 0.38, "MHS 5s": 0.38, "temp": 48.0, "Last Share Difficulty": 256.0, "Intensity": "0", "Powertune": -20, "Utility": 1.29}, {"Difficulty Accepted": 440320.0, "Difficulty Rejected": 512.0, "GPU Voltage": 1.2, "GPU Clock": 1070, "Fan Speed": 2965, "GPU Activity": 99, "Status": "Alive", "Device Rejected%": 0.1163, "Fan Percent": 100, "Rejected": 2, "Memory Clock": 1500, "Hardware Errors": 0, "Accepted": 1609, "Last Share Pool": 0, "Diff1 Work": 440053, "hash": 0.381, "Total MH": 28103.2376, "Enabled": "Y", "Device Elapsed": 73201, "Device Hardware%": 0.0, "Last Valid Work": 1409019735, "Last Share Time": 1409019736, "GPU": 2, "MHS av": 0.38, "MHS 5s": 0.38, "temp": 55.0, "Last Share Difficulty": 256.0, "Intensity": "0", "Powertune": -20, "Utility": 1.32}, {"Difficulty Accepted": 423168.0, "Difficulty Rejected": 1280.0, "GPU Voltage": 1.2, "GPU Clock": 1070, "Fan Speed": 2980, "GPU Activity": 99, "Status": "Alive", "Device Rejected%": 0.3007, "Fan Percent": 100, "Rejected": 5, "Memory Clock": 1500, "Hardware Errors": 0, "Accepted": 1539, "Last Share Pool": 0, "Diff1 Work": 425739, "hash": 0.381, "Total MH": 28010.2666, "Enabled": "Y", "Device Elapsed": 73201, "Device Hardware%": 0.0, "Last Valid Work": 1409019750, "Last Share Time": 1409019750, "GPU": 3, "MHS av": 0.38, "MHS 5s": 0.38, "temp": 58.0, "Last Share Difficulty": 256.0, "Intensity": "0", "Powertune": -20, "Utility": 1.26}, {"Difficulty Accepted": 436096.0, "Difficulty Rejected": 0.0, "GPU Voltage": 1.2, "GPU Clock": 1070, "Fan Speed": 2990, "GPU Activity": 99, "Status": "Alive", "Device Rejected%": 0.0, "Fan Percent": 100, "Rejected": 0, "Memory Clock": 1500, "Hardware Errors": 0, "Accepted": 1580, "Last Share Pool": 0, "Diff1 Work": 434616, "hash": 0.381, "Total MH": 28105.5478, "Enabled": "Y", "Device Elapsed": 73201, "Device Hardware%": 0.0, "Last Valid Work": 1409019757, "Last Share Time": 1409019757, "GPU": 4, "MHS av": 0.38, "MHS 5s": 0.38, "temp": 56.0, "Last Share Difficulty": 256.0, "Intensity": "0", "Powertune": -20, "Utility": 1.3}, {"Difficulty Accepted": 438912.0, "Difficulty Rejected": 768.0, "GPU Voltage": 1.2, "GPU Clock": 1070, "Fan Speed": 2889, "GPU Activity": 99, "Status": "Alive", "Device Rejected%": 0.1745, "Fan Percent": 100, "Rejected": 3, "Memory Clock": 1500, "Hardware Errors": 0, "Accepted": 1617, "Last Share Pool": 0, "Diff1 Work": 440188, "hash": 0.381, "Total MH": 28105.8263, "Enabled": "Y", "Device Elapsed": 73201, "Device Hardware%": 0.0, "Last Valid Work": 1409019619, "Last Share Time": 1409019619, "GPU": 5, "MHS av": 0.38, "MHS 5s": 0.38, "temp": 64.0, "Last Share Difficulty": 256.0, "Intensity": "0", "Powertune": -20, "Utility": 1.33}], "type": "cgminer", "pool": {"Stratum Active": true, "Difficulty Accepted": 2574336.0, "Pool Rejected%": 0.1786, "Difficulty Rejected": 4608.0, "Diff1 Shares": 2580390, "Status": "Alive", "Proxy Type": "", "Last Share Difficulty": 256.0, "Pool Stale%": 0.0694, "Quota": 1, "Rejected": 18, "Stratum URL": "stratum.simplevert.com", "User": "VbRS1xjKP3nEvV7uC1NbECkzW8kTdVP63J.Kev1n2", "Long Poll": "N", "Accepted": 9410, "Proxy": "", "Get Failures": 0, "Difficulty Stale": 1792.0, "URL": "stratum+tcp://stratum.simplevert.com:3344", "Discarded": 6985, "Has Stratum": true, "Last Share Time": 1409019757, "Stale": 6, "Works": 171292, "POOL": 0, "Priority": 0, "Getworks": 3570, "Has GBT": false, "Best Share": 19970948, "Remote Failures": 0}, "v": "0.3.5"}')
        elif command == "pools":
            data = {"POOLS": [
                {"Stratum URL": "localhost",
                 "URL": "stratum+tcp://localhost:3333",
                 "User": "testing"}
            ]}
            return data


class AgentSender(object):
    """ Managed interfacing with PowerPool server for relaying information """
    def __init__(self, miners, address='127.0.0.1', port=4444):
        self.address = address
        self.port = port
        self.miners = miners
        self.conn = None

    def connect(self):
        logger.info("Opening connection to agent server; addr: {0}; port: {1}"
                     .format(self.address, self.port))
        conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        conn.connect((self.address, self.port))
        conn.settimeout(15)
        self.conn = conn.makefile()
        logger.debug("Announcing hello message")
        self.conn.write(json.dumps({'method': 'hello', 'params': [0.1]}) + "\n")
        self.conn.flush()

    def reset_connection(self):
        logger.info("Disconnected from remote.")
        self.conn = None
        # reauth required upon connection error
        for miner in self.miners:
            miner.authenticated = False

    def send(self, data):
        logger.debug("Sending {0} to server".format(data))
        try:
            if self.conn is None:
                self.connect()
            self.conn.write(json.dumps(data) + "\n")
            self.conn.flush()
        except socket.error:
            logger.debug("Send socket error", exc_info=True)
            self.reset_connection()
        except Exception:
            logger.error("Unhandled sending exception, resetting connection.",
                         exc_info=True)
            self.reset_connection()

        return True

    def receive(self):
        if self.conn is None:
            return {}

        try:
            recv = self.conn.readline(4096)
        except socket.error as e:
            logger.debug("Failed to receive response, connection error", exc_info=True)
            self.reset_connection()
            return {}

        if len(recv) > 4000:
            raise Exception("Server returned too large of a string")
        logger.debug("Received response from server {0}".format(recv.strip()))
        if not recv:
            self.reset_connection()
            return {}
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
            # we need to authenticate with the remote if not authed yet
            if miner.authenticated is False:
                try:
                    username = miner.worker
                except WorkerNotFound:
                    logger.info("Miner not connected to valid pool")
                    continue
                except socket.error:
                    logger.info("Unable to connect to miner.")
                    continue
                except Exception:
                    logger.error("Unhandled exception", exc_info=True)
                    continue

                logger.debug("Attempting to authenticate {0}".format(username))
                data = {'method': 'worker.authenticate',
                        'params': [username, ]}
                if not self.send(data):
                    logger.info("Failed to communicate with server")
                    time.sleep(5)
                    continue

                retval = self.receive()
                if retval.get('error', True) is None:
                    logger.debug("Successfully authenticated {0}".format(username))
                    miner.authenticated = True
                    miner.reset_timers()
                else:
                    logger.info(
                        "Failed to authenticate worker {0}, server returned {1}."
                        .format(username, retval))

            if miner.authenticated is True:
                try:
                    miner.collect()
                except socket.error:
                    logger.info("Problem collecting from cgminer, resetting connection")
                    miner.reset()
                except Exception:
                    logger.warn("Unhandled exception from collection, resetting connection", exc_info=True)
                    miner.reset()
            else:
                # don't distribute if we're not authenticated...
                continue

            # send all our values that were accumulated
            farthest = 0
            for i, value in enumerate(miner.queue):
                send = {'method': 'stats.submit', 'params': value}
                logger.info("Transmitting new stats: {0}".format(send))
                if not self.send(send):
                    logger.warn("Unable to send to remote, probably down temporarily.")
                    time.sleep(5)
                    break

                # try to get a response from the server. if we fail to
                # receive, just wait till next loop to send
                ret = self.receive()
                if ret is None or ret.get('error', True) is not None:
                    logger.warn("Received failure result '{0}' from the server!"
                                .format(ret))
                    break
                farthest = i + 1

            # trim all the sent messages off the queue
            miner.queue[:] = miner.queue[farthest:]


def install(configs):
    if os.geteuid() != 0:
        logger.error("Please run as root to install...")
        easy_exit()

    # where are we running from right now?
    script_path = os.path.realpath(__file__).replace('pyc', 'py')
    logger.info("Detected script in path " + script_path)
    # chroot folder
    script_dir = os.path.join(os.path.split(script_path)[:-1])[0]
    # now build an executable path
    exec_path = "{0} {1}".format(sys.executable, script_path)
    logger.info("Configuring executable path" + script_dir)
    setup_folders('/etc/ppagent/')

    import subprocess
    if configs['type'] == 'upstart':
        upstart = open(os.path.join(script_dir, 'install/upstart.conf')).read().format(exec_path=exec_path, chdir=script_dir)

        path = '/etc/init/ppagent.conf'
        flo = open(path, 'w')
        flo.write(upstart)
        flo.close()
        os.chmod(path, 0644)

        try:
            subprocess.call('useradd ppagent', shell=True)
        except Exception as e:
            if getattr(e, 'returncode', 0) == 9:
                pass
            raise
        logger.info("Added ppagent user to run daemon under")

        subprocess.call('service ppagent restart', shell=True)
    elif configs['type'] == 'sysv':
        sysv = open(os.path.join(script_dir, 'install/initd')).read()
        sysv = Template(sysv).safe_substitute(exec_path=exec_path)

        path = '/etc/init.d/ppagent'
        flo = open(path, 'w')
        flo.write(sysv)
        flo.close()
        os.chmod(path, 0751)
        subprocess.call('/etc/init.d/ppagent start', shell=True)
        subprocess.call('update-rc.d ppagent defaults', shell=True)


def setup_folders(config_home, filename="config.json"):
    try:
        os.makedirs(config_home, 0751)
        logger.info("Config folder created at {0}"
                    .format(config_home))
    except OSError as e:
        if e.errno != 17:
            logger.error("Failed to create configuration directory at {0}"
                         .format(config_home))
            easy_exit(1)
        logger.debug("Config directory already created")

    with open(os.path.join(config_home, filename), 'w') as f:
        f.write(default_config)
        logger.info("Wrote the default configuration file to {0}"
                    .format(os.path.join(config_home, filename)))


def entry():
    parser = argparse.ArgumentParser(
        prog='ppagent', description='A daemon for reporting mining statistics to your pool.')
    parser.add_argument('-l',
                        '--log-level',
                        choices=['DEBUG', 'INFO', 'WARN', 'ERROR'],
                        default='INFO')
    parser.add_argument('-a', '--address', default=None)
    parser.add_argument('-c', '--config', default=None)
    parser.add_argument('-p', '--port', type=int, default=None)
    parser.add_argument('--version', action='version', version='%(prog)s {0}'.format(version))
    subparsers = parser.add_subparsers(title='main subcommands', dest='action')

    subparsers.add_parser('run', help='start the daemon')
    inst = subparsers.add_parser('install', help='install the upstart script and add user')
    inst.add_argument('type', choices=['upstart', 'sysv'],
                      help='upstart for ubuntu, sysv for debian.')
    if len(sys.argv) == 1:
        args = parser.parse_args(['run'])
    else:
        args = parser.parse_args()
    configs = vars(args)

    if configs['action'] == 'install':
        try:
            install(configs)
        except Exception:
            logger.info("Installation failed because of an unhandled exception:")
            raise
        easy_exit(0)

    # rely on command line log level until we get all configs parsed
    ch.setLevel(getattr(logging, args.log_level))
    logger.setLevel(getattr(logging, args.log_level))

    # if they didn't specify a config file lets create a default in the os
    # specific default locations
    if configs['config'] is None:
        if sys.platform == "win32":
            configs['config'] = 'ppagent.json'
            path = '.'
            name = 'ppagent.json'
        else:
            configs['config'] = os.path.join(config_home, 'config.json')
            path = config_home
            name = 'config.json'

        if not os.path.isfile(configs['config']):
            setup_folders(path, name)

    # setup or load our configuration file
    try:
        file_configs = json.load(open(configs['config']))
        logger.debug("Loaded JSON config file from {0}".format(configs['config']))
    except (IOError, OSError):
        logger.error("JSON configuration file {0} couldn't be loaded, no miners configured, exiting..."
                     .format(configs['config']), exc_info=True)
        easy_exit(1)

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
            typ = globals()[content.pop('type', 'CGMiner')]
            kwargs = {}
            # apply defaults, followed by overriding with config options
            update(kwargs, typ.defaults)
            update(kwargs, content)
            kwargs['remotes'] = [configs['address']]
            # init the miner class with the configs
            miners.append(typ(**kwargs))
        elif title == "daemon":
            configs.update(content)

    if not configs['address']:
        # try and fetch the address from our first miner entry. A bit of a hack
        # until 0.4 can be released to handle this more robustly
        while True:
            try:
                url = miners[0].fetch_pool()
            except Exception:
                logger.info("Couldn't fetch pool info from cgminer!", exc_info=True)
                time.sleep(1)
                continue
            configs['address'] = url.hostname
            configs['port'] = url.port + 1111
            break

    # set a default of 4444 for the port
    if not configs['port']:
        configs['port'] = 4444

    for miner in miners:
        miner.remotes = [configs['address']]

    # set our logging level based on the configs
    ch.setLevel(getattr(logging, configs['log_level']))
    logger.setLevel(getattr(logging, configs['log_level']))
    logger.debug(configs)

    sender = AgentSender(miners, configs['address'], configs['port'])
    sender.loop()

if __name__ == "__main__":
    entry()
