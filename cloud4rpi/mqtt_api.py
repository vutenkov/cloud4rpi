# -*- coding: utf-8 -*-

import time
import logging
import json

from cloud4rpi import config
from cloud4rpi import utils
from cloud4rpi.errors import MqttConnectionError

import paho.mqtt.client as mqtt

KEEP_ALIVE_INTERVAL = 30  # sec
RETRY_INTERVAL = 5  # sec
CONNECT_RESULT_UNDEFINED = 255

log = logging.getLogger(config.loggerName)


def is_success(rc):
    return rc == mqtt.MQTT_ERR_SUCCESS


class MqttApi(object):
    def __init__(self,
                 device_token,
                 host=config.mqqtBrokerHost,
                 port=config.mqttBrokerPort):
        utils.guard_against_invalid_token(device_token)

        def noop_on_command(cmd):
            pass

        self.__device_token = device_token
        self.__client = mqtt.Client(device_token, clean_session=False)
        self.__host = host
        self.__port = port
        self.__qos = 1
        self.__connect_result = None

        self.on_command = noop_on_command

    @property
    def commands_topic(self):
        return self.__format_topic('commands')

    @property
    def config_topic(self):
        return self.__format_topic('config')

    @property
    def data_topic(self):
        return self.__format_topic('data')

    @property
    def diag_topic(self):
        return self.__format_topic('diagnostics')

    def __format_topic(self, tail):
        return 'devices/{0}/{1}'.format(self.__device_token, tail)

    def connect(self):
        def on_connect(client, userdata, flags, rc):
            if not is_success(rc):
                log.error('Connection failed: %s', rc)
                raise MqttConnectionError(rc)

            log.info('Connected')
            self.__connect_result = rc

            log.info('Subscribing %s with QoS %s',
                     self.commands_topic, str(self.__qos))
            self.__client.subscribe(self.commands_topic, qos=self.__qos)

        def on_message(client, userdata, msg):
            log.info('Command received %s: %s', msg.topic, msg.payload)
            if callable(self.on_command):
                payload = msg.payload.decode() \
                    if isinstance(msg.payload, bytes) else msg.payload
                self.on_command(json.loads(payload))

        def on_disconnect(client, userdata, rc):
            log.info('Disconnected with code: %s', rc)
            self.__on_disconnect(rc)

        def on_publish(client, packet, mid):
            log.info('Published %s: %s', packet['topic'], packet['msg'])

        self.__client.on_connect = on_connect
        self.__client.on_message = on_message
        self.__client.on_disconnect = on_disconnect
        self.__client.on_publish = on_publish

        log.info('Connecting %s:%s', self.__host, self.__port)
        self.__client.connect(self.__host, self.__port,
                              keepalive=KEEP_ALIVE_INTERVAL)

        self.__connect_result = CONNECT_RESULT_UNDEFINED
        self.__client.loop_start()

        while self.__connect_result == CONNECT_RESULT_UNDEFINED:
            time.sleep(.01)

    def __on_disconnect(self, rc):
        if is_success(rc):
            return

        while True:
            log.info('Reconnecting')

            try:
                self.__client.reconnect()
                return
            except Exception as e:
                log.info('Reconnection failed: %s', str(e))

            time.sleep(RETRY_INTERVAL)

    def disconnect(self):
        self.__client.loop_stop()
        self.__client.disconnect()

    def publish_config(self, msg):
        self.__publish(self.config_topic, msg)

    def publish_data(self, msg):
        self.__publish(self.data_topic, msg)

    def publish_diag(self, msg):
        self.__publish(self.diag_topic, msg)

    def __publish(self, topic, payload=None):
        if payload is None:
            return

        msg = {
            'ts': utils.utcnow(),
            'payload': payload,
        }

        self.__client.user_data_set({
            'topic': topic,
            'msg': msg,
        })

        self.__client.publish(topic, qos=self.__qos, payload=json.dumps(msg))
