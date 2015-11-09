import datetime
from subprocess import CalledProcessError
from multiprocessing import Pool, Pipe
import time
from requests import RequestException
import signal

from cloud4rpi.__main__ import log
import cloud4rpi.errors as errors
import cloud4rpi.helpers as helpers

from sensors import ds18b20 as temperature_sensor
# from sensors import test_sensor as temperature_sensor
from user_scripts.test import ExampleScript
# from user_scripts.example import ExampleScript


parent_conn, child_conn = Pipe()


class MutableDatetime(datetime.datetime):
    @classmethod
    def utcnow(cls):
        return super(MutableDatetime, cls).utcnow()


datetime.datetime = MutableDatetime


def find_sensors():
    return temperature_sensor.find_all()


def read_sensor(address):
    return temperature_sensor.read(address)


def init_worker():
    signal.signal(signal.SIGINT, signal.SIG_IGN)


class RpiDaemon(object):
    def __init__(self, settings):
        self.sensors = None
        self.variables = None
        self.actuators = None
        self.me = None
        self.pool = Pool(processes=4, initializer=init_worker)
        token = settings.DeviceToken
        if not helpers.verify_token(token):
            raise errors.InvalidTokenError
        self.settings = settings
        self.token = token

    def run(self):
        self.prepare()
        self.send_device_config()
        # TODO necessary?
        self.ensure_there_are_sensors()
        self.run_user_scripts()
        self.poll()

    def prepare(self):
        self.know_thyself()
        self.prepare_sensors()
        self.prepare_variables()
        self.prepare_actuators()

    def prepare_sensors(self):
        self.find_sensors()

    def prepare_variables(self):
        self.variables = helpers.find_variables(self.settings)

    def prepare_actuators(self):
        self.actuators = helpers.find_actuators(self.settings)

    def know_thyself(self):
        log.info('Getting device configuration...')
        self.me = helpers.get_device(self.token)

    def find_sensors(self):
        self.sensors = find_sensors()

    def send_device_config(self):
        self.register_new_extensions()
        self.me.set_type('Raspberry PI')
        self.me = helpers.put_device(self.token, self.me)
        print 'RESPONSE: ' + str(self.me.dump())

    def register_new_extensions(self):
        new_sensors = self.me.whats_new(self.sensors)
        new_actuators = self.me.whats_new(self.actuators)
        new_variables = self.me.whats_new(self.variables)
        if len(new_sensors) > 0:
            log.info('New sensors found: {0}'.format(list(new_sensors)))
            self.me.add_sensors(sorted(new_sensors))
        if len(new_actuators) > 0:
            log.info('New actuators found: {0}'.format(list(new_actuators)))
            self.me.add_actuators([x for x in self.settings.Actuators if x['address'] in sorted(new_actuators)])
        if len(new_variables) > 0:
            log.info('New variables found: {0}'.format(list(new_variables)))
            self.me.add_variables([x for x in self.settings.Variables if x['name'] in sorted(new_variables)])

    def ensure_there_are_sensors(self):
        if len(self.sensors) == 0:
            raise errors.NoSensorsError

    def read_sensors(self):
        data = []
        for x in self.sensors:
            try:
                data.append(read_sensor(x))
            except Exception as ex:
                log.error('Reading sensor error: ' + ex.message)

        return data

    def poll(self):
        while True:
            self.tick()
            time.sleep(self.settings.scanIntervalSeconds)

    def tick(self):
        try:
            if parent_conn.poll():
                    self.set_actuator_state(parent_conn.recv())
            res = self.send_stream()
            self.process_actuators_state(res)
            self.send_system_parameters()
        except RequestException:
            log.error('Failed. Skipping...')

    def send_stream(self):
        stream = self.create_stream()
        return helpers.post_stream(self.token, stream)


    def process_actuators_state(self, res):
        for act_id, act_params in res['configuration']['actuators'].iteritems():
            parent_conn.send({'id': act_id, 'params': act_params})

    def set_actuator_state(self, data):
        print str(helpers.set_actuator_state(self.token, data['id'], data['state']))

    def create_stream(self):
        ts = datetime.datetime.utcnow().isoformat()
        readings = self.read_sensors()
        payload = self.me.map_extensions(readings)
        return {
            'ts': ts,
            'payload': payload
        }

    def send_system_parameters(self):
        try:
            helpers.post_system_parameters(self.token)
        except (CalledProcessError, RequestException):
            log.error('Failed. Skipping...')

    def shutdown(self):
        print 'Terminate user scripts'
        self.pool.terminate()
        self.pool.join()
        print 'Done'

    def run_user_scripts(self):
        self.pool.apply_async(run_script, args=(ExampleScript, self.me.dump()))

    def send_user_script_data(self, data):
        print 'send_user_script_data' + str(data)

    def get_callback(self):
        def callback(data):
            self.send_user_script_data(data)

        return callback


def run_script(script_class, script_config):
    print 'Init user script'
    with script_class(script_config, child_conn) as user_script:
        print 'Run user script'
        user_script.run()
    print 'Done user script'
