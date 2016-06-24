#!/usr/bin/env python
# -*- coding: utf-8 -*-

from c4r import ds18b20
from c4r import cpu
from c4r import lib
from c4r import error_messages
from c4r.helpers import verify_token


def api_wrapper(method, *args):
    try:
        return method(*args)
    except Exception as e:
        print 'API error: {0}'.format(get_error_message(e))
        return None


def get_error_message(e):
    return error_messages.get_error_message(e)


def set_api_key(token):
    api_wrapper(lib.set_api_key, token)


def register(variables):
    verify_token(lib.api_key)
    api_wrapper(lib.register, variables)


def find_ds_sensors():
    return api_wrapper(ds18b20.find_all)


def find_cpu():
    return api_wrapper(cpu.Cpu)


def read_persistent(variables):
    api_wrapper(lib.read_persistent, variables)


def read_system(variables):
    api_wrapper(lib.read_system, variables)

# only for http-data-exchange scenario
# def process_variables(variables, server_msg):
#     api_wrapper(lib.process_variables, variables, server_msg)


def send_receive(variables):
    verify_token(lib.api_key)
    return api_wrapper(lib.send_receive, variables)


def send_system_info():
    verify_token(lib.api_key)
    return api_wrapper(lib.send_system_info)


def start_message_broker_listen():
    verify_token(lib.api_key)
    return api_wrapper(lib.start_mqtt_listen)


def stop_message_broker_listen():
    verify_token(lib.api_key)
    return api_wrapper(lib.stop_mqtt_listen)
