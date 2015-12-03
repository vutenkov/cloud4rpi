#!/usr/bin/env python
# -*- coding: utf-8 -*-

from c4r import ds18b20
from c4r.log import Logger
from c4r import daemon

log = Logger().get_log()
dmn = daemon.Daemon()

def find_ds_sensors():
    return ds18b20.find_all()

def set_device_token(token):
    dmn.set_device_token(token)

def read_persistence(variables):
    dmn.read_persistence(variables)

def process_variables(variables):
    dmn.process_variables(variables)
