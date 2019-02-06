#!/usr/bin/env python3
"""
Periodically set a chamber to values read from an external sensor
"""

# Error which needs catching and handling.  Seems to recurr twice in a row; will happen again first time script is rerun
#Traceback (most recent call last):
#  File "./track_external.py", line 120, in <module>
#    sys.exit(main(argv=None))
#  File "./track_external.py", line 102, in main
#    chamber.setHSetpoint(RH)
#  File "/home/travc/chamber_control/especmodbus.py", line 116, in setHSetpoint
#    return self.inst.write_register(self.REG_H_SETPOINT, value, numberOfDecimals=1)
#  File "/home/travc/miniconda3/lib/python3.6/site-packages/minimalmodbus.py", line 296, in write_register
#    self._genericCommand(functioncode, registeraddress, value, numberOfDecimals, signed=signed)
#  File "/home/travc/miniconda3/lib/python3.6/site-packages/minimalmodbus.py", line 697, in _genericCommand
#    payloadFromSlave = self._performCommand(functioncode, payloadToSlave)
#  File "/home/travc/miniconda3/lib/python3.6/site-packages/minimalmodbus.py", line 798, in _performCommand
#    payloadFromSlave = _extractPayload(response, self.address, self.mode, functioncode)
#  File "/home/travc/miniconda3/lib/python3.6/site-packages/minimalmodbus.py", line 1088, in _extractPayload
#    raise ValueError('The slave is indicating an error. The response is: {!r}'.format(response))
#ValueError: The slave is indicating an error. The response is: '\x01\x90\x03\x0c\x01'


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
from dateutil.tz import tzlocal
from threading import Event
from collections import deque
import signal
import logging
import argparse

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
#CHAMBER_DEV = "/dev/ttyS0"
#GET_TH_CMD = "ssh root@10.200.59.13 /root/read_indoor_TH.py"
#FREQUENCY = 15*60 # how often to update; in seconds
#LIGHT_ON_HOUR = 6
#LIGHT_OFF_HOUR = 18

#CHAMBER_ADDR = 1
#CHAMBER_TIMEOUT = 1
READ_TIMEOUT = 60
MIN_CYCLE_SLEEP = 0.1

RH_RANGE_MIN = 10
RH_RANGE_MAX = 95
T_RANGE_MIN = -20
T_RANGE_MAX = 99

def epoch2str(float_secs):
    return datetime.fromtimestamp(float_secs).replace(tzinfo=tzlocal()).strftime("%Y-%m-%d %H:%M:%S.%f %z"),


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-d', "--dev", required=True,
            help="Serial port or device. eg: /dev/ttyUSB0 "
                    "(required)")
    #parser.add_argument('-l', "--logfile", default=None,
    #        help="Filename to log experiment status to; required")
    #parser.add_argument('-p', "--profile", default=None,
    #        help="csv including a header line of 'time, T, RH, light' to track; "
    #            "either a filename or a string starting with '\\n'")
    #parser.add_argument("--repeat", type=int, default=0,
    #        help="Period in seconds to repeat the profile; 0 for no repeat; 86400 for daily")
    #parser.add_argument("--clocktime", action="store_true", default=False,
    #        help="Times in input refer to actual time instead of offset from start time")
    #parser.add_argument("--restart", action="store_true", default=False,
    #        help="Ignore any exisitng log and start fresh; "
    #             "default is to continue previous run if any")
    parser.add_argument('-C', "--cmd", type=str, required=True,
            help="Command executed to get temperature, humiditiy, and (optionally) light values")
    parser.add_argument('-F', "--frequency", type=int, default=900,
            help="Update frequency in seconds")
    parser.add_argument("--light-on-hour", type=int, default=6,
            help="Hour (24) to turn on lights if cmd does not return a value for light")
    parser.add_argument("--light-off-hour", type=int, default=18,
            help="Hour (24) to turn off lights if cmd does not return a value for light")
    parser.add_argument("--override-light", action="store_true", default=False,
            help="Use fixed light cylce (light-on-hour and light-off-hour) even if cmd returns a value for light")
    parser.add_argument('-T', "--test-only", action="store_true", default=False,
            help="Do not actually send change commands to chamber")
    parser.add_argument("--addr", type=int, default=1,
            help="Modbus slave address")
    parser.add_argument("--timeout", type=int, default=1,
            help="Modbus timeout")
    parser.add_argument('-q', "--quiet", action='count', default=0,
            help="Decrease verbosity")
    parser.add_argument('-v', "--verbose", action='count', default=0,
            help="Increase verbosity")
    parser.add_argument("--verbose_level", type=int, default=0,
            help="Set verbosity level as a number")
    args = parser.parse_args(argv)

    logging.getLogger().setLevel(logging.getLogger().getEffectiveLevel()+
                                 (10*(args.quiet-args.verbose-args.verbose_level)))

    start_time = time.time()
    logging.info("Started {}; dev={}; pid={}".format(
                        epoch2str(start_time),
                        args.dev,
                        os.getpid()))

    # Setup the modbus interface
    chamber = especmodbus.EspecF4Modbus(args.dev, args.addr, args.timeout)

    # Event object to handle main loop cycling
    mainloopcylceevent = Event()
    steptime = start_time

    while True:

        # query the T & RH sensor host
        foo = os.popen(args.cmd).read().strip()
        logging.info("Read from sensor: '{}'".format(foo))
        foo = foo.split()

        T = round(float(foo[0]), 1)
        RH = round(float(foo[1]), 1)

        if T < T_RANGE_MIN:
            logging.warn("Requested T value {} too low. Setting to {}".format(T, T_RANGE_MIN))
            T = T_RANGE_MIN
        if T > T_RANGE_MAX:
            logging.warn("Requested T value {} too high. Setting to {}".format(T, T_RANGE_MAX))
            T = T_RANGE_MAX
        if RH < RH_RANGE_MIN:
            logging.warn("Requested RH value {} too low. Setting to {}".format(RH, RH_RANGE_MIN))
            RH = RH_RANGE_MIN
        if RH > RH_RANGE_MAX:
            logging.warn("Requested RH value {} too high. Setting to {}".format(RH, RH_RANGE_MAX))
            RH = RH_RANGE_MAX

        if len(foo) > 2 and not args.override_light:
            light_val = round(float(foo[2]), 1)
        else:
            # default light cycle
            nowtime = datetime.now()
            light_on_hour = nowtime.replace(hour=args.light_on_hour, minute=0, second=0, microsecond=0)
            light_off_hour = nowtime.replace(hour=args.light_off_hour, minute=0, second=0, microsecond=0)
            light_val = int(nowtime > light_on_hour and nowtime < light_off_hour)

        ## do the step
        logging.info("Set '{}' T={}, RH={}, light={}".format(chamber.dev, T, RH, light_val))
        if args.test_only:
            logging.info("Test only mode")
        else:
            if T is not None and not math.isnan(T):
                chamber.setTSetpoint(T)
            if RH is not None and not math.isnan(RH):
                chamber.setHSetpoint(RH)
            if light_val is not None and not math.isnan(light_val):
                chamber.setTimeSignal(light_val)

        ## sleep til this step is supposed to happen
        steptime += args.frequency
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
