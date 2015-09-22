#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import re
import requests
import time
import datetime
import logging
import logging.handlers

from subprocess import CalledProcessError
from requests import RequestException
from settings import DeviceToken

from sensors import cpu as cpuSensor

import settings
import settings_vendor as config

W1_DEVICES = '/sys/bus/w1/devices/'
W1_SENSOR_PATTERN = re.compile('(10|22|28)-.+', re.IGNORECASE)

ANSI_ESCAPE = re.compile(r'\x1b[^m]*m')

LOG_FILE_PATH = os.path.join('/', 'var', 'log', 'cloud4rpid.log')

REQUEST_TIMEOUT_SECONDS = 3 * 60 + 0.05


def create_logger():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    config_logging_to_console(logger)
    return logger


def config_logging_to_console(logger):
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(console)


def config_logging_to_file(logger):
    log_file = logging.handlers.RotatingFileHandler(LOG_FILE_PATH, maxBytes=1024 * 1024)
    log_file.setFormatter(logging.Formatter('%(asctime)s: %(message)s'))
    logger.addHandler(log_file)


log = create_logger()


def get_system_parameters():
    cpu_temperature = cpuSensor.read()
    return {
        'cpuTemperature': cpu_temperature
    }

class MutableDatetime(datetime.datetime):
    @classmethod
    def utcnow(cls):
        return super(MutableDatetime, cls).utcnow()


datetime.datetime = MutableDatetime


def sensor_full_path(sensor):
    return os.path.join(W1_DEVICES, sensor, 'w1_slave')


def find_sensors():
    return [x for x in os.listdir(W1_DEVICES)
            if W1_SENSOR_PATTERN.match(x) and os.path.isfile(sensor_full_path(x))]


def read_sensor(address):
    readings = read_whole_file(sensor_full_path(address))
    temp_token = 't='
    temp_index = readings.find(temp_token)
    if temp_index < 0:
        return None
    temp = readings[temp_index + len(temp_token):]
    return address, float(temp) / 1000


def read_whole_file(path):
    with open(path, 'r') as f:
        return f.read()

def request_headers(token):
    return {'api_key': token}


def device_request_url(token):
    return '{0}/devices/{1}/'.format(config.baseApiUrl, token)


def stream_request_url(token):
    return '{0}/devices/{1}/streams/'.format(config.baseApiUrl, token)


def system_parameters_request_url(token):
    return '{0}/devices/{1}/params/'.format(config.baseApiUrl, token)


def get_device(token):
    res = requests.get(device_request_url(token),
                       headers=request_headers(token),
                       timeout=REQUEST_TIMEOUT_SECONDS)
    check_response(res)
    return ServerDevice(res.json())


def put_device(token, device):
    log.info('Sending device configuration...')
    deviceJSON = device.dump()
    log.info(deviceJSON)
    res = requests.put(device_request_url(token),
                       headers=request_headers(token),
                       json=deviceJSON,
                       timeout=REQUEST_TIMEOUT_SECONDS)
    check_response(res)
    if res.status_code != 200:
        log.error("Can't register sensor. Status: {0}".format(res.status_code))

    return ServerDevice(res.json())


def post_stream(token, stream):
    log.info('sending {0}'.format(stream))

    res = requests.post(stream_request_url(token),
                        headers=request_headers(token),
                        json=stream,
                        timeout=REQUEST_TIMEOUT_SECONDS)
    check_response(res)
    return res.json()


def post_system_parameters(token, params):
    log.info('sending {0}'.format(params))

    res = requests.post(system_parameters_request_url(token),
                        headers=request_headers(token),
                        json=params,
                        timeout=REQUEST_TIMEOUT_SECONDS)
    check_response(res)
    return res.json()


def check_response(res):
    log.info(res.status_code)
    if res.status_code == 401:
        raise AuthenticationError


def verify_token(token):
    r = re.compile('[0-9a-f]{24}')
    return len(token) == 24 and r.match(token)


class AuthenticationError(Exception):
    pass


class InvalidTokenError(Exception):
    pass


class NoSensorsError(Exception):
    pass


class ServerDevice(object):
    def __init__(self, device_json):
        self.json = device_json
        self.addresses = None
        self.sensor_index = None
        self.__build_sensor_index()
        self.__extract_addresses()

    def sensor_addrs(self):
        return self.addresses

    def add_sensors(self, sensors):
        self.json['sensors'] += [{'name': x, 'address': x} for x in sensors]
        self.__extract_addresses()

    def whats_new(self, sensors):
        existing = self.sensor_addrs()
        return set(sensors) - set(existing)

    def dump(self):
        return self.json

    def map_sensors(self, readings):
        index = self.sensor_index
        return {index[address]: reading for address, reading in readings if address in index}

    def set_type(self, new_type):
        self.json['type'] = new_type

    def __extract_addresses(self):
        self.addresses = self.sensor_index.keys()

    def __build_sensor_index(self):
        self.sensor_index = {sensor['address']: sensor['_id'] for sensor in self.json['sensors']}


class RpiDaemon(object):
    def __init__(self, token):
        self.sensors = None
        self.me = None
        if not verify_token(token):
            raise InvalidTokenError
        self.token = token

    def run(self):
        self.prepare_sensors()
        self.ensure_there_are_sensors()
        self.poll()

    def prepare_sensors(self):
        self.know_thyself()
        self.find_sensors()
        self.send_device_config()

    def know_thyself(self):
        log.info('Getting device configuration...')
        self.me = get_device(self.token)

    def find_sensors(self):
        self.sensors = find_sensors()

    def send_device_config(self):
        self.register_new_sensors()
        self.me.set_type('Raspberry PI')
        self.me = put_device(self.token, self.me)

    def register_new_sensors(self):
        new_sensors = self.me.whats_new(self.sensors)
        if len(new_sensors) > 0:
            log.info('New sensors found: {0}'.format(list(new_sensors)))
            self.me.add_sensors(sorted(new_sensors))

    def ensure_there_are_sensors(self):
        if len(self.sensors) == 0:
            raise NoSensorsError

    def read_sensors(self):
        payload = []
        for x in self.sensors:
            try:
                val = read_sensor(x)
                if val is not None:
                    payload.append(val)
            except Exception as ex:
                log.error('Reading sensor error:' + ex.message)

        return payload


    def poll(self):
        while True:
            self.tick()
            time.sleep(settings.scanIntervalSeconds)

    def tick(self):
        self.send_stream()
        self.send_system_parameters()

    def send_stream(self):
        stream = self.create_stream()
        try:
            post_stream(self.token, stream)
        except RequestException:
            log.error('Failed. Skipping...')

    def create_stream(self):
        ts = datetime.datetime.utcnow().isoformat()
        readings = self.read_sensors()
        payload = self.me.map_sensors(readings)
        return {
            'ts': ts,
            'payload': payload
        }

    def send_system_parameters(self):
        try:
            params = get_system_parameters()
            post_system_parameters(self.token, params)
        except (CalledProcessError, RequestException):
            log.error('Failed. Skipping...')


def modprobe(module):
    cmd = 'modprobe {0}'.format(module)
    ret = os.system(cmd)
    if ret != 0:
        raise CalledProcessError(ret, cmd)

def safeRunDaemon():
    maxTryCount = 5
    waitSecs = 10
    n = 0
    while n < maxTryCount:
        try:
            daemon.run()
            break
        except requests.ConnectionError as ex:
            log.exception('Daemon running ERROR: {0}'.format(ex.message))
            log.exception('Waiting for {0} sec...'.format(waitSecs))
            time.sleep(waitSecs)
            n += 1
            waitSecs *= 2


if __name__ == "__main__":
    try:
        modprobe('w1-gpio')
        modprobe('w1-therm')

        config_logging_to_file(log)

        log.info('Starting...')

        daemon = RpiDaemon(DeviceToken)
        safeRunDaemon()


    except RequestException as e:
        log.exception('Connection failed. Please try again later. Error: {0}'.format(e.message))
        exit(1)
    except CalledProcessError:
        log.exception('Try "sudo python cloud4rpi.py"')
        exit(1)
    except InvalidTokenError:
        log.exception('Device Access Token {0} is incorrect. Please verify it.'.format(DeviceToken))
        exit(1)
    except AuthenticationError:
        log.exception('Authentication failed. Check your device token.')
        exit(1)
    except NoSensorsError:
        log.exception('No sensors found... Exiting')
        exit(1)
    except Exception as e:
        log.exception('Unexpected error: {0}'.format(e.message))
        exit(1)
    except KeyboardInterrupt:
        log.info('Interrupted')
        exit(1)
