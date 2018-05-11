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
import configparser
from itertools import chain
import argparse
import numpy as np
from datetime import datetime
from datetime import timezone
import dateutil
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
#logging.basicConfig(format='%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s', datefmt="%Y-%m-%d %H:%M:%S")
logging.basicConfig(format='%(asctime)s.%(msecs)03d %(levelname)s %(module)s: %(message)s', datefmt="%Y-%m-%d %H:%M:%S")
logging.getLogger().setLevel(logging.WARNING)


## CONSTANTS ##
DEFAULT_CONFIG_FILE = "test_profile.cfg"
MIN_CYCLE_SLEEP = 0.1


def epoch2str(float_secs):
    return datetime.fromtimestamp(float_secs).astimezone().strftime("%Y-%m-%d %H:%M:%S.%f %z")


def set_chamber_vals(chamber_list, vals, test_only_mode_flag):
    for dev in chamber_list:
        set_single_chamber_vals(dev, vals, test_only_mode_flag)


def set_single_chamber_vals(chamber, vals, test_only_mode_flag):
    """actually send commands to the chamber to set values
    vals dict-like object with 'T', 'RH', and 'light'"""
    # round to 1 decimal place (not strictly needed, but good idea)
    T = round(float(vals['T']), 1)
    RH = round(float(vals['RH']), 1)
    light_val = round(float(vals['light']), 1)
    logging.info("Set '{}' T={}, RH={}, light={}".format(chamber.dev, T, RH, light_val))
    if test_only_mode_flag:
        logging.info("Test only mode")
    else:
        if T is not None and not np.isnan(T):
            chamber.setTSetpoint(T)
        if RH is not None and not np.isnan(RH):
            chamber.setHSetpoint(RH)
        if light_val is not None and not np.isnan(light_val):
            chamber.setTimeSignal(light_val)



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
            help="Serial port or dev file; "
                    "comma separated list without spaces is OK; "
                    "integer values are converted to /dev/ttyUSB{val}; "
                    "required")
    parser.add_argument('-l', "--logfile", default=None,
            help="Filename to log experiment status to; required")
    parser.add_argument('-p', "--profile", default=None,
            help="csv including a header line of 'time, T, RH, light' to track; "
                "either a filename or a string starting with '\\n'")
    parser.add_argument("--repeat", type=int, default=0,
            help="Period in seconds to repeat the profile; 0 for no repeat; 86400 for daily")
    parser.add_argument("--clocktime", action="store_true", default=False,
            help="Times in input refer to actual time instead of offset from start time")
    parser.add_argument("--restart", action="store_true", default=False,
            help="Ignore any exisitng log and start fresh; "
                 "default is to continue previous run if any")
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

    parser.set_defaults(**defaults) # add the defaults read from the config file
    args = parser.parse_args(remaining_argv)

    logging.getLogger().setLevel(logging.getLogger().getEffectiveLevel()+
                                 (10*(args.quiet-args.verbose-args.verbose_level)))

    # check for required arguments
    if args.logfile is None:
        print("ERROR: -l/--logfile must be set", file=sys.stderr)
        sys.exit(1)
    if args.logfile is None:
        print("ERROR: -p/--profile must be set", file=sys.stderr)
        sys.exit(1)
    if args.dev is None:
        print("ERROR: -d/--dev must be set", file=sys.stderr)
        sys.exit(1)

    # convert args.dev to a list
    args.dev = args.dev.split(',')
    # if the dev is just an int, add the /dev/ttyUSB part
    for i,dev in enumerate(args.dev):
        try:
            args.dev[i] = "/dev/ttyUSB{:d}".format(int(dev))
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
    espec = [especmodbus.EspecF4Modbus(dev, args.addr, args.timeout) for dev in args.dev]

    logging.info("Logfile: '{}'".format(args.logfile))
    if args.restart:
        try:
            os.unlink(args.logfile)
            logging.warn("Removed old logfile due to --restart")
        except FileNotFoundError:
            pass

    # Read the input file
    if args.profile.startswith('\n'):
        df = pd.read_csv(StringIO(args.profile.strip()), skipinitialspace=True)
    else:
        logging.info("Reading profile from file '{}'".format(args.profile))
        df = pd.read_csv(args.profile, skipinitialspace=True)
    # convert index from dates to just seconds into the timeseries (don't need to worry about TZ)
    df.index = pd.to_datetime(df['time'])
    if args.clocktime:
        df.index = pd.to_datetime(df['time'])
        df.index = df.index.tz_localize(-time.timezone)
        df.index = (df.index-pd.to_datetime(start_time, unit='s', utc=True).tz_convert(-time.timezone)).total_seconds()
    else:
        df.index = (df.index-df.index[0]).total_seconds()
    df.index.name = "seconds"

    #print(df.head()) # @TCC TEMP


    # if continuing, there will be a logfile
    run_start_time = None
    try:
        with open(args.logfile, 'r') as logfh:
            # first line is the start timestamp
            line = next(logfh)
            run_start_time = float(line.strip())
        logging.warning("Continuing run started at {} ({})".format(run_start_time,
                        epoch2str(run_start_time)))
                        #datetime.fromtimestamp(run_start_time).astimezone().strftime("%Y-%m-%d %H:%M:%S.%f %z")))
    except FileNotFoundError:
        pass

    # log the start time if this is a new run
    if run_start_time is None:
        run_start_time = time.time()
        with open(args.logfile, 'w') as logfh:
            print(run_start_time, file=logfh)

    ## skip steps which should have already happened
    # except the last one, which we should set the chamber's initial values to
    actual_start_time = time.time() # should always be >= than run_start_time
    oldstepdf = df[df.index <= actual_start_time-run_start_time]
    if oldstepdf.empty:
        logging.error("First step starts in the future... Don't do that.")
        sys.exit(2)
    print("Previous steps\n", oldstepdf)

    # add the passed steps to the next repeat (if we are repeating)
    if args.repeat > 0:
        for r in oldstepdf.iterrows():
            df.drop(r[0], inplace=True)
            df.loc[r[0]+args.repeat] = r[1]
    else: # just drop the old events if no repeat
        df = df[df.index > actual_start_time-run_start_time]

    logging.info("Events dataframe:\n"+str(df))


    # set initial values
    set_chamber_vals(espec, oldstepdf.iloc[-1], args.test_only)

    # Event object to handle main loop cycling
    mainloopcylceevent = Event()

    #for stepnum, (sec, dfrow) in enumerate(df.iterrows()):
    while not df.empty:
        sec = df.index[0]
        dfrow = df.iloc[0]

        logging.info("next event: "+str(round(sec,3))+" "+str(dict(dfrow)))#'\t'.join(list(dfrow.astype(str))))

        ## sleep til this step is supposed to happen
        steptime = run_start_time+sec
        sleepsecs = max(MIN_CYCLE_SLEEP, steptime-time.time())
        logging.info("Sleeping for {} secs until {} ({})".format(sleepsecs, steptime,
                        epoch2str(steptime)))
                        #datetime.fromtimestamp(steptime).astimezone().strftime("%Y-%m-%d %H:%M:%S.%f %z")
                        #))

        mainloopcylceevent.wait(sleepsecs)
        mainloopcylceevent.clear() # in case it was set by an interrupt

        ## do the step
        set_chamber_vals(espec, dfrow, args.test_only)

        ## drop the event
        df.drop(sec, inplace=True)

        ## if repeat, add for the next time around
        if args.repeat > 0:
            df.loc[sec+args.repeat] = dfrow


## Main hook for running as script
if __name__ == "__main__":
    sys.exit(main(argv=None))
