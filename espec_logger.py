#!/usr/bin/env python3
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
from dateutil.tz import tzlocal
from threading import Event
from collections import deque
import signal
import logging
import especmodbus

# setup logging
logging.addLevelName(logging.INFO+1, "STAT")
logging.addLevelName(logging.CRITICAL-1, "NOTICE")
def getlvlnum(name):
    return name if isinstance(name, int) else logging.getLevelName(name)
def getlvlname(num):
    return num if isinstance(num, str) else logging.getLevelName(num)
logging.basicConfig()
logging.getLogger().setLevel(logging.WARNING)


## CONSTANTS ##
DEFAULT_CONFIG_FILE = "test_logger.cfg"
MIN_CYCLE_SLEEP = 0.1
MIN_LVL_TO_LOGFILE = logging.NOTSET # Log everything to file... @TCC, might want to change this (numeric level)
MIN_LVL_TO_EMAIL = logging.ERROR    # (numeric level)
TAIL_DEQUE_MAX_LEN = 20
# Globals, yeah, ick
gTAIL_DEQUE = deque(maxlen=TAIL_DEQUE_MAX_LEN)


## code to simplify sending email
# from: http://masnun.com/2010/01/01/sending-mail-via-postfix-a-perfect-python-example.html
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.utils import COMMASPACE, formatdate
from email import encoders

def sendMail(to, fro, subject, text, files=[], server="localhost"):
    assert type(to)==list
    assert type(files)==list
    msg = MIMEMultipart()
    msg['From'] = fro
    msg['To'] = COMMASPACE.join(to)
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = subject
    msg.attach( MIMEText(text) )
    for file in files:
        part = MIMEBase('application', "octet-stream")
        part.set_payload( open(file,"rb").read() )
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', 'attachment; filename="%s"'
                       % os.path.basename(file))
        msg.attach(part)
    smtp = smtplib.SMTP(server)
    smtp.sendmail(fro, to, msg.as_string() )
    smtp.close()


#######

def epoch2str(float_secs):
    return datetime.fromtimestamp(float_secs).replace(tzinfo=tzlocal()).strftime("%Y-%m-%d %H:%M:%S.%f %z")


class SWDeviationAlarm():
    def __init__(self, name, low_trigger_thresh, low_clear_thresh=None,
                            high_trigger_thresh=None, high_clear_thresh=None):
        """
        If clear_thresh values are omitted, will be set to same as trigger_thresh values
        If only low thresh values are give, high values will be set the same
        """
        self.name = name
        self.low_trigger_thresh = low_trigger_thresh
        self.low_clear_thresh = low_clear_thresh
        self.high_trigger_thresh = high_trigger_thresh
        self.high_clear_thresh = high_clear_thresh
        self.setpoint = None
        self.reactivate_time = None
        # defaults: high and low threshs are the same; clear_thresh = trigger_thresh
        # the logic here is a wee bit tricky
        if self.high_clear_thresh is None:
            self.high_clear_thresh = self.low_clear_thresh
        if self.low_clear_thresh is None:
            self.low_clear_thresh = self.low_trigger_thresh
        if self.high_trigger_thresh is None:
            self.high_trigger_thresh = self.low_trigger_thresh
        if self.high_clear_thresh is None:
            self.high_clear_thresh = self.high_trigger_thresh
        assert self.low_clear_thresh <= self.low_trigger_thresh
        assert self.high_clear_thresh <= self.high_trigger_thresh
        # trigger # set only if currently in an alarmed/triggered state
        self.trigger_type = None
        self.first_trigger_time = None
        self.last_trigger_time = None
        self.current_msg_level = 0

    def init_setpoint(self, setpoint):
        """just sets the setpoint value"""
        self.setpoint = setpoint

    def get_setpoint(self):
        return self.setpoint

    def reenable(self):
        self.reactivate_time = None

    def disable_until_time(self, reactivate_time, override=False):
        """if override is false, will not reduce existing disable time"""
        if override or self.reactivate_time is None or self.reactivate_time < reactivate_time:
            self.reactivate_time = reactivate_time

    def is_triggered(self): # return True if in an alarmed state
        return self.first_trigger_time is not None

    def _trigger(self, curtime, trigger_type, value, msgs):
        if self.first_trigger_time is None: # new trigger
            self.current_msg_level = 'CRITICAL'
            self.trigger_type = trigger_type
            self.first_trigger_time = curtime
            self.last_trigger_time = curtime
            print("First Trigger {}".format(curtime))
        else: # retrigger
            self.current_msg_level = 'WARNING'
            if self.trigger_type != trigger_type:
                msgs.append(['WARNING', "{} alarm changed from {} to {} ... THIS IS ODD".format(
                        self.name, self.trigger_type, "LOW")])
                self.trigger_type = trigger_type
            self.last_trigger_time = curtime
        return msgs


    def update(self, setpoint, value):
        curtime = time.time()
        msgs = [] # level, string; levels are 0=debug, 1=info, 2=warning, 3=critical

        # check for setpoint change
        if self.setpoint is None or setpoint != self.setpoint:
            msgs.append(['INFO', "{} setpoint change from {} to {}".format(
                    self.name, self.setpoint, setpoint)])
            self.setpoint = setpoint

        # just unset and trigger and return if disabled (will not trigger)
        if self.reactivate_time is not None and curtime < self.reactivate_time:
            self.trigger_type = None
            self.first_trigger_time = None
            self.last_trigger_time = None
            msgs.append(['INFO', "ALARM {} disabled until {:.2f} ({:.2f} more sec)".format(
                    self.name, self.reactivate_time, self.reactivate_time-curtime)])
            return msgs

        # Low
        if value < setpoint-self.low_trigger_thresh:
            msgs = self._trigger(curtime, "LOW", value, msgs)
        # High
        if value > setpoint+self.high_trigger_thresh:
            msgs = self._trigger(curtime, "HIGH", value, msgs)
        # Clear
        if( self.first_trigger_time is not None and
            value > setpoint-self.low_clear_thresh and
            value < setpoint+self.high_clear_thresh ):
            self.current_msg_level = 1
            msgs.append(['NOTICE', "ALARM {} {} CLEARED; first_trigger_time:{:.2f}, duration:{:.2f} sec".format(
                    self.name, self.trigger_type, self.first_trigger_time,
                    curtime-self.first_trigger_time)])
            self.trigger_type = None
            self.first_trigger_time = None
            self.last_trigger_time = None

        # Output
        if self.first_trigger_time is not None:
            msgs.append([self.current_msg_level,
                        "ALARM {} {} value={} SP={} time:{:.2f} for {:.2f}s; first trigger {:.2f}s ago".format(
                        self.name, self.trigger_type, value, setpoint,
                        self.first_trigger_time,
                        self.last_trigger_time-self.first_trigger_time,
                        curtime-self.first_trigger_time)])
        return msgs

#######


def write_msg(logfilename, lvl, msg):
    lvlnum = getlvlnum(lvl)
    lvlname = getlvlname(lvl)
    msg = "{:.2f}\t".format(time.time())+str(msg)
    logging.log(lvlnum, msg)
    # output to logfile
    if lvlnum >= MIN_LVL_TO_LOGFILE:
        msg = lvlname+"\t"+str(msg)
        with open(logfilename, 'a') as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            print(msg, file=fh)
            fcntl.flock(fh, fcntl.LOCK_UN)
            fh.close()
        # add to a rolling queue for possible other (email) outout
        gTAIL_DEQUE.append(msg)


def main(argv):

    # parse cfg_file argument and set defaults
    conf_parser = argparse.ArgumentParser(description=__doc__,
                                          add_help=False)  # turn off help so later parse (with all opts) handles it
    conf_parser.add_argument('-c', '--cfg-file', type=argparse.FileType('r'),# default=DEFAULT_CONFIG_FILE,
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
        defaults['overwrite'] = defaults['overwrite'].lower() in ['true', 'yes', 'y', '1']
        # defaults['make_temperature_plots'] = strtobool(defaults['make_temperature_plots'])
        #        if( 'bam_files' in defaults ): # bam_files needs to be a list
        #            defaults['bam_files'] = [ x for x in defaults['bam_files'].split('\n') if x and x.strip() and not x.strip()[0] in ['#',';'] ]
    else:
        defaults = {}

    # parse rest of arguments with a new ArgumentParser
    parser = argparse.ArgumentParser(description=__doc__, parents=[conf_parser])
    parser.add_argument('-d', "--dev", default=None,
            help="Serial port or dev file")
    parser.add_argument('-T', "--test", action="store_true", default=False,
            help="Run test function and exit")
    parser.add_argument("--addr", type=int, default=1,
            help="Modbus slave address")
    parser.add_argument("--timeout", type=int, default=1,
            help="Modbus timeout")
    parser.add_argument('-f', "--freq", type=int, default=30,
            help="Approximate time in seconds between log entries")
    parser.add_argument('-l', "--logfile", default="test.log",
            help="Filename to write log to")
    parser.add_argument("--overwrite", action='store_true', default=False,
            help="Overwrite existing logfile (default is to append)")
    parser.add_argument('-e', "--alarm_email", default="chamber",
            help="Email address to send alarm messages to ('none' to disable)")
    parser.add_argument('-q', "--quiet", action='count', default=0,
            help="Decrease verbosity")
    parser.add_argument('-v', "--verbose", action='count', default=0,
            help="Increase verbosity")
    parser.add_argument("--verbose_level", type=int, default=0,
            help="Set verbosity level as a number")

    parser.add_argument("--alarm_T_deviation_trigger", type=float, default=1,
            help="Threshold in 'C to trigger Temperature deviation from Setpoint alarm")
    parser.add_argument("--alarm_T_deviation_clear", type=float, default=1,
            help="Threshold in 'C to clear the Temperature deviation from Setpoint alarm")
    parser.add_argument("--alarm_T_disable_time_after_setpoint_change_multiplier", type=float, default=10,
            help="Temperature deviation alarm is disabled after a setpoint change for constant + multiplier * difference in 'C")
    parser.add_argument("--alarm_T_disable_time_after_setpoint_change_constant", type=float, default=10,
            help="Temperature deviation alarm is disabled after a setpoint change for constant + multiplier * difference in 'C")

    parser.add_argument("--alarm_H_deviation_trigger", type=float, default=10,
            help="Threshold in 'C to trigger Humidity deviation from Setpoint alarm")
    parser.add_argument("--alarm_H_deviation_clear", type=float, default=10,
            help="Threshold in 'C to clear the Humidity deviation from Setpoint alarm")
    parser.add_argument("--alarm_H_disable_time_after_setpoint_change_multiplier", type=float, default=10,
            help="Humidity deviation alarm is disabled after a setpoint change for constant + multiplier * difference in 'C")
    parser.add_argument("--alarm_H_disable_time_after_setpoint_change_constant", type=float, default=10,
            help="Humidity deviation alarm is disabled after a setpoint change for constant + multiplier * difference in 'C")

    parser.set_defaults(**defaults) # add the defaults read from the config file
    args = parser.parse_args(remaining_argv)

    logging.getLogger().setLevel(logging.getLogger().getEffectiveLevel()+
                                 (10*(args.quiet-args.verbose-args.verbose_level)))

    # dev has to be set
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
    write_msg(args.logfile, 'INFO', "Logger started {}; dev={}; pid={}".format(
                        epoch2str(start_time),
                        args.dev,
                        os.getpid()))
    write_msg(args.logfile, 'INFO', args)

    # Setup the modbus interface
    espec = especmodbus.EspecF4Modbus(args.dev, args.addr, args.timeout)
    # if test is set, just run the test and exit
    if args.test:
        espec.test()
        return(0)

    logging.info("Logfile: '{}'".format(args.logfile))
    if args.overwrite:
        logging.warn("Overwriting logfile '{}'".format(args.logfile))
        try:
            os.unlink(args.logfile)
        except FileNotFoundError:
            pass

    # alarms
    alarm_emailed_time = None # keep track of if/when we sent email to avoid spamming too much
    ## Software alarms
    swalarm_Tdev = SWDeviationAlarm('T', args.alarm_T_deviation_trigger, args.alarm_T_deviation_clear)
    swalarm_Hdev = SWDeviationAlarm('H', args.alarm_H_deviation_trigger, args.alarm_H_deviation_clear)

    # header line and first data line
    stat = espec.getStat()
    write_msg(args.logfile, 'INFO', "STAT_HEADER\ttime\t"+'\t'.join(str(v) for v in stat.keys()))
    write_msg(args.logfile, 'STAT', '\t'.join(str(v) for v in stat.values()))
    # set the initial setpoint values in the alarms
    swalarm_Tdev.init_setpoint(stat['TSetpoint'])
    swalarm_Hdev.init_setpoint(stat['HSetpoint'])

    # Event object to handle main loop cycling
    mainloopcylceevent = Event()
    # Catch ALRM (kill -ALRM {pid}) to wake the main loop and immediately poll the chamber
    signal.signal(signal.SIGALRM, lambda signum,frame: mainloopcylceevent.set())
    # @TCC could reset the start_time on the signal too

    # loop for subsequent data lines
    cycle_number = 0 # for timing the next loop
    while True:
        email_msg = [] # these will get emailed out as critical alarms

        ## update/read stat from the chamber
        try:
            stat = espec.updateStat()
        except OSError as err:
            write_msg(args.logfile, 'CRITICAL', str(err))
            email_msg.append("CRITICAL\t"+str(err))

        # output to log file
        write_msg(args.logfile, 'STAT', '\t'.join(str(v) for v in stat.values()))

        ## Events (like a setpoint change)
        # setpoint changes; logging will be handled by swalarm, but we want to temporally disable alarm triggering
        if stat['TSetpoint'] != swalarm_Tdev.get_setpoint():
            T_delay_time = (args.alarm_T_disable_time_after_setpoint_change_multiplier*
                            abs(stat['TSetpoint']-swalarm_Tdev.get_setpoint())+
                            args.alarm_T_disable_time_after_setpoint_change_constant)
            T_reenable_time = time.time()+T_delay_time
            swalarm_Tdev.disable_until_time(T_reenable_time)
            # also disable H swalarm for same time since heating/cooling tends to throw H off
            swalarm_Hdev.disable_until_time(T_reenable_time) # also disable H alarm
            write_msg(args.logfile, 'INFO', "Disabling T and H alarms for {:.2f}s until {:.2f}".format(
                      T_delay_time, T_reenable_time))
        # HSetpoint
        if stat['HSetpoint'] != swalarm_Hdev.get_setpoint() :
            H_delay_time = (args.alarm_H_disable_time_after_setpoint_change_multiplier*
                            abs(stat['HSetpoint']-swalarm_Hdev.get_setpoint())+
                            args.alarm_H_disable_time_after_setpoint_change_constant)
            H_reenable_time = time.time()+H_delay_time
            swalarm_Hdev.disable_until_time(H_reenable_time) # also disable H alarm
            write_msg(args.logfile, 'INFO', "disabling H alarm for {:.2f}s until {:.2f}".format(
                      H_delay_time, H_reenable_time))

        msgs = []
        ## Chamber fault alarm
        if stat['ChamberAlarmStatus']:
            msgs.append(['CRITICAL', "ALARM CHAMBER"])
        ## Software alarms
        msgs.extend(swalarm_Tdev.update(stat['TSetpoint'], stat['T']))
        msgs.extend(swalarm_Hdev.update(stat['HSetpoint'], stat['H']))

        # output messages
        for msg_level, msg in msgs:
            if getlvlnum(msg_level) >= MIN_LVL_TO_EMAIL:
                email_msg.append(getlvlname(msg_level)+'\t'+msg)
            if getlvlnum(msg_level) >= MIN_LVL_TO_LOGFILE:
                write_msg(args.logfile, msg_level, msg)

        # email (just email if any messages are above the threshod; could get frequent)
        if email_msg:
            alarm_emailed_time = time.time()
            subject = "Chamber Alarm '{}'\n".format(args.dev)
            msg = "Chamber Alarm '{}'\n".format(args.dev)
            msg += '\n'.join(email_msg)+'\n'
            msg += "\n\nSTAT_HEADER\ttime\t"+'\t'.join(str(v) for v in stat.keys())
            msg += "\ntail of logfile:\n"+'\n'.join(str(v) for v in gTAIL_DEQUE)
            sendMail([args.alarm_email], 'root', subject, msg)

        ## sleep til next check
        cycle_number += 1
        mainloopcylceevent.wait(max(MIN_CYCLE_SLEEP, start_time+cycle_number*args.freq-time.time()))
        mainloopcylceevent.clear() # in case it was set by an interrupt


## Main hook for running as script
if __name__ == "__main__":
    sys.exit(main(argv=None))
