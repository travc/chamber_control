#!/usr/bin/env python3
"""
Run a timed series of temperature and humidity setpoints
"""

import sys
import os
import fcntl
import serial
import minimalmodbus
import time
import configparser
from itertools import chain
import argparse
from datetime import datetime
from threading import Event
from collections import deque
import signal
import logging

import pandas as pd

import especmodbus


# setup logging
def getlvlnum(name):
    return name if isinstance(name, int) else logging.getLevelName(name)
def getlvlname(num):
    return num if isinstance(num, str) else logging.getLevelName(num)
logging.basicConfig()
logging.getLogger().setLevel(logging.WARNING)


## CONSTANTS ##
DEFAULT_CONFIG_FILE = "test_exp.cfg"


def main(argv):

    # parse cfg_file argument and set defaults
    conf_parser = argparse.ArgumentParser(description=__doc__,
                                          add_help=False)  # turn off help so later parse (with all opts) handles it
    conf_parser.add_argument('-c', '--cfg-file', type=argparse.FileType('r'), default=DEFAULT_CONFIG_FILE,
                             help="Config file specifiying options/parameters.\nAny long option can be set by remove the leading '--' and replace '-' with '_'")
    args, remaining_argv = conf_parser.parse_known_args(argv)
    # build the config (read config files)
    cfg_filename = None
    if args.cfg_file:
        cfg_filename = args.cfg_file.name
        cfg = configparser.ConfigParser(inline_comment_prefixes=('#',';'))
        cfg.optionxform = str # make configparser case-sensitive
        cfg.read_file(chain(("[DEFAULTS]",), args.cfg_file))
        defaults = dict(cfg.items("DEFAULTS"))
        # special handling of paratmeters that need it like lists
        #defaults['overwrite'] = defaults['overwrite'].lower() in ['true', 'yes', 'y', '1']
        #if( 'bam_files' in defaults ): # bam_files needs to be a list
        #    defaults['bam_files'] = [ x for x in defaults['bam_files'].split('\n') if x and x.strip() and not x.strip()[0] in ['#',';'] ]
    else:
        defaults = {}

    # parse rest of arguments with a new ArgumentParser
    parser = argparse.ArgumentParser(description=__doc__, parents=[conf_parser])
    parser.add_argument('-d', "--dev", default=None,
            help="Serial port or dev file; required")
    parser.add_argument('-l', "--logfile", default=None,
            help="Filename to log experiment status to; required")
    parser.add_argument('-f', "--input-file", default=None,
            help="Filename of main (time, temperature, humidity) file to track")
    parser.add_argument("--restart", action="store_true", default=False,
            help="Ignore any exisitng log and start fresh; "
                 "default is to continue previous run if any")
    parser.add_argument('-T', "--test", action="store_true", default=False,
            help="Run test function and exit")
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

    parser.set_defaults(**defaults) # add the defaults read from the config file
    args = parser.parse_args(remaining_argv)

    logging.getLogger().setLevel(logging.getLogger().getEffectiveLevel()+
                                 (10*(args.quiet-args.verbose-args.verbose_level)))

    # check for required arguments
    if args.logfile is None:
        print("ERROR: -l/--logfile must be set", file=sys.stderr)
        sys.exit(1)
    if args.logfile is None:
        print("ERROR: -f/--input-file must be set", file=sys.stderr)
        sys.exit(1)
    if args.dev is None:
        print("ERROR: -d/--dev must be set", file=sys.stderr)
        sys.exit(1)
    # if the dev is just an int, add the /dev/ttyS part
    try:
        args.dev = "/dev/ttyS{:d}".format(int(args.dev))
    except ValueError:
        pass

    # Startup output
    start_time = time.time()
    logging.info("Experiment started {}; dev={}; pid={}".format(
                        datetime.fromtimestamp(start_time).astimezone().strftime("%Y-%m-%d %H:%M:%S.%f %z"),
                        args.dev,
                        os.getpid()))
    logging.info(args)

    # Setup the modbus interface
    espec = especmodbus.EspecF4Modbus(args.dev, args.addr, args.timeout)

    logging.info("Logfile: '{}'".format(args.logfile))
    if args.restart:
        try:
            os.unlink(args.logfile)
            logging.warn("Removed old logfile due to --restart")
        except FileNotFoundError:
            pass

    # Read the input file
    pd.read_csv(args.input_file)
    #TCC TODO


    # log the start time (or do for each cycle?)
    #TCC TODO


#    # Event object to handle main loop cycling
#    mainloopcylceevent = Event()
#    while True:
#
#        ## sleep til next check
#        cycle_number += 1
#        mainloopcylceevent.wait(max(MIN_CYCLE_SLEEP, start_time+cycle_number*args.freq-time.time()))
#        mainloopcylceevent.clear() # in case it was set by an interrupt


## Main hook for running as script
if __name__ == "__main__":
    sys.exit(main(argv=None))
