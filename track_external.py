#!/usr/bin/env python3
"""
Run a timed series of light, temperature, and humidity setpoints
Allow setting only some values (such as just light)
Allow repeating/looping of the profile
"""

import sys
import os
import fcntl
import serial
from io import StringIO
import minimalmodbus
import time
import math
from datetime import datetime
from datetime import timezone
import dateutil
from threading import Event
from collections import deque
import signal
import logging

import especmodbus


# setup logging
def getlvlnum(name):
    return name if isinstance(name, int) else logging.getLevelName(name)
def getlvlname(num):
    return num if isinstance(num, str) else logging.getLevelName(num)
#logging.basicConfig(format='%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s', datefmt="%Y-%m-%d %H:%M:%S")
logging.basicConfig(format='%(asctime)s.%(msecs)03d %(levelname)s %(module)s: %(message)s', datefmt="%Y-%m-%d %H:%M:%S")
logging.getLogger().setLevel(logging.INFO)


## CONSTANTS ##
CHAMBER_DEV = "/dev/ttyUSB0"
GET_TH_CMD = "ssh root@10.200.59.13 /root/DHT11read.py"
CHAMBER_ADDR = 1
FREQUENCY = 15*60 # how often to update; in seconds
LIGHT_ON_HOUR = 6
LIGHT_OFF_HOUR = 18

MIN_CYCLE_SLEEP = 0.1
CHAMBER_TIMEOUT = 1
READ_TIMEOUT = 60


def epoch2str(float_secs):
    return datetime.fromtimestamp(float_secs).astimezone().strftime("%Y-%m-%d %H:%M:%S.%f %z")


def set_single_chamber_vals(chamber, vals, test_only_mode_flag):
    """actually send commands to the chamber to set values
    vals dict-like object with 'T', 'RH', and 'light'"""
    # round to 1 decimal place (not strictly needed, but good idea)



def main(argv):

    start_time = time.time()
    logging.info("Started {}; dev={}; pid={}".format(
                        datetime.fromtimestamp(start_time).astimezone().strftime("%Y-%m-%d %H:%M:%S.%f %z"),
                        CHAMBER_DEV,
                        os.getpid()))

    # Setup the modbus interface
    chamber = especmodbus.EspecF4Modbus(CHAMBER_DEV, CHAMBER_ADDR, CHAMBER_TIMEOUT)

    # Event object to handle main loop cycling
    mainloopcylceevent = Event()
    steptime = start_time

    test_only_mode_flag = False

    while True:

        # query the T & RH sensor host
        foo = os.popen(GET_TH_CMD).read()
        logging.info("Read from sensor: '{}'".format(foo))
        foo = foo.split()

        T = round(float(foo[0]), 1)
        RH = round(float(foo[1]), 1)

        # 6am to 6pm light cycle
        nowtime = datetime.now()
        light_on_hour = nowtime.replace(hour=LIGHT_ON_HOUR, minute=0, second=0, microsecond=0)
        light_off_hour = nowtime.replace(hour=LIGHT_OFF_HOUR, minute=0, second=0, microsecond=0)
        light_val = int(nowtime > light_on_hour and nowtime < light_off_hour)

        ## do the step
        logging.info("Set '{}' T={}, RH={}, light={}".format(chamber.dev, T, RH, light_val))
        if test_only_mode_flag:
            logging.info("Test only mode")
        else:
            if T is not None and not math.isnan(T):
                chamber.setTSetpoint(T)
            if RH is not None and not math.isnan(RH):
                chamber.setHSetpoint(RH)
            if light_val is not None and not math.isnan(light_val):
                chamber.setTimeSignal(light_val)

        ## sleep til this step is supposed to happen
        steptime += FREQUENCY
        sleepsecs = max(MIN_CYCLE_SLEEP, steptime-time.time())
        logging.info("Sleeping for {} secs until {} ({})".format(sleepsecs, steptime,
                        epoch2str(steptime)))
                        #datetime.fromtimestamp(steptime).astimezone().strftime("%Y-%m-%d %H:%M:%S.%f %z")
                        #))

        mainloopcylceevent.wait(sleepsecs)
        mainloopcylceevent.clear() # in case it was set by an interrupt


## Main hook for running as script
if __name__ == "__main__":
    sys.exit(main(argv=None))
