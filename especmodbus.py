#!/usr/bin/env python3
import sys
import os
import fcntl
import serial
import minimalmodbus
from collections import OrderedDict, namedtuple
import logging

####### Adjustments to minimalmodbus

class BlockingInstrument(minimalmodbus.Instrument):
    def _communicate(self, request, number_of_bytes_to_read):
        """Wraps Instrument._communicate with fcntl lock and unlock of the serial port"""
        fcntl.flock(self.serial.fileno(), fcntl.LOCK_EX)
        rv = super()._communicate(request, number_of_bytes_to_read)
        fcntl.flock(self.serial.fileno(), fcntl.LOCK_UN)
        return rv

# make debug messages from minimalmodbus go through logging
minimalmodbus._print_out = lambda msg: logging.debug(msg)


#######

class EspecF4Modbus():

    # Note: there must be a 'getWhatever' method for every 'Whatever' in STAT_FIELDS
    STAT_FIELDS = [
                'ChamberAlarmStatus',
                'T',
                'TSetpoint',
                'TAlarmStatus',
                'H',
                'HSetpoint',
                'HAlarmStatus',
                'HeatingPower',
                'CoolingPower',
                'HumidPower',
                'DehumidPower',
                'TimeSignal',
                ]

    # device constants
    # normal 16 bit registers
    REG_T = 100
    REG_T_SETPOINT = 300 # rw
    REG_H = 104
    REG_H_SETPOINT = 319 # rw

    # Alarms
    REG_ALARM1_STATUS = 102
    REG_ALARM1_SOURCE = 716 # input for alarm; 0=1, 1=2, 2=3
    REG_ALARM1_TYPE = 702 # 0=off, 1=process, 2=deviation
    REG_ALARM1_LOW_THRESHOLD = 302 # Deviation or Setpoint depending on ALARM1_TYPE; deviation should be negative
    REG_ALARM1_HIGH_THRESHOLD = 303 # Deviation or Setpoint depending on ALARM1_TYPE
    REG_ALARM1_SILENCING = 705 # alarm disabled until condition returns to normal
    REG_ALARM1_LATCHING = 704 # 0=self clearing, 1=latching
    REG_ALARM1_LOGIC = 707 # alarm output open (0) or closed (1) on alarm; probably don't need
    REG_ALARM1_MESSAGES = 108 # alarm puts a message on main chamber screen (0=yes, 1=no)
    REG_ALARM1_SIDES = 706 # 0=both, 1=low, 2=high

    REG_ALARM2_STATUS = 106
    REG_ALARM2_HIGH_DEVIATION = 322

    #
    REG_HEATING_POWER = 103
    REG_COOLING_POWER = 107
    REG_HUMID_POWER = 111
    REG_DEHUMID_POWER = 115
    # Fault?
    REG_CHAMBER_ALARM_STATUS = 201 # Digital input 1
        # Function can be set on 1060; default is "control outputs off" (I think)
    # Time Signal (power output switch to be used for lights?)
    REG_TIME_SIGNAL = 2000 # Digital output 1 #@TCC possibly rename to lights


    def __init__(self, dev, slave_addr, timeout):
        self.dev = dev
        self.slave_addr = slave_addr
        self.timeout = timeout
        # setup minimalmodbus
        minimalmodbus.TIMEOUT = self.timeout
        self.inst = BlockingInstrument(self.dev, self.slave_addr)
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            self.inst.debug = True
        logging.debug(self.inst)
        # read initial stat
        self.updateStat()


    ## low level
    def getChamberAlarmStatus(self):
        return self.inst.read_register(self.REG_CHAMBER_ALARM_STATUS)
    def getTAlarmStatus(self):
        return self.inst.read_register(self.REG_ALARM1_STATUS)
    def getHAlarmStatus(self):
        return self.inst.read_register(self.REG_ALARM2_STATUS)

    def getT(self):
        return self.inst.read_register(self.REG_T, numberOfDecimals=1)
    def getH(self):
        return self.inst.read_register(self.REG_H, numberOfDecimals=1)

    def getTSetpoint(self):
        return self.inst.read_register(self.REG_T_SETPOINT, numberOfDecimals=1)
    def setTSetpoint(self, value):
        return self.inst.write_register(self.REG_T_SETPOINT, value, numberOfDecimals=1)

    def getHSetpoint(self):
        return self.inst.read_register(self.REG_H_SETPOINT, numberOfDecimals=1)
    def setHSetpoint(self, value):
        return self.inst.write_register(self.REG_H_SETPOINT, value, numberOfDecimals=1)

    def getHeatingPower(self):
        return self.inst.read_register(self.REG_HEATING_POWER)
    def getCoolingPower(self):
        return self.inst.read_register(self.REG_COOLING_POWER)
    def getHumidPower(self):
        return self.inst.read_register(self.REG_HUMID_POWER)
    def getDehumidPower(self):
        return self.inst.read_register(self.REG_DEHUMID_POWER)

    def getTimeSignal(self):
        return self.inst.read_register(self.REG_TIME_SIGNAL)
    def setTimeSignal(self, value):
        return self.inst.write_register(self.REG_TIME_SIGNAL, value)

    ## higher level
    def getStat(self):
        return self.stat

    def updateStat(self):
        self.stat = OrderedDict()
        for k in self.STAT_FIELDS:
            self.stat[k] = getattr(self, "get"+k)()
        return self.stat


    ## Testing code, invoked when module is run as script

    def test(self):
        #self.setTSetpoint(23)
        #self.setHSetpoint(60)
        self.setTimeSignal(1)
        #print(self.stat.keys())
        #print(self.stat.values())
        for k,v in self.stat.items():
            print(k, v)

        #print("{0} 0x{0:x} 0b{0:016b}".format(self.inst.read_register(302)))
        #print("{0} 0x{0:x} 0b{0:016b}".format(self.inst.read_register(303)))
        #print("{0} 0x{0:x} 0b{0:016b}".format(self.inst.read_register(706)))

        #print("TS {0:b} 0x{0:x} 0b{0:016b}".format(self.inst.read_register(self.REG_TIME_SIGNAL)))
        #print("{0:b} 0x{0:x} 0b{0:016b}".format(self.inst.read_register(2001)))
        #self.inst.write_register(self.REG_TIME_SIGNAL, 0)
        #print("TS {0:b} 0x{0:x} 0b{0:016b}".format(self.inst.read_register(self.REG_TIME_SIGNAL)))
        #print("{0:b} 0x{0:x} 0b{0:016b}".format(self.inst.read_register(2001)))
        #val = self.inst.read_string(0)
        #print(val)
        #print(' '.join(format(ord(x), 'b') for x in val))
        #print("{0:b} 0x{0:x}".format(val))



### Simple testing code when run as script
def main():
#    ## Probe serial ports
#    for i in range(1,32):
#        DEFAULT_PORT = "/dev/ttyS{:d}".format(i)
#        DEFAULT_ADDR = 1
#        DEFAULT_TIMEOUT = 1
#        logging.getLogger().setLevel(logging.INFO)
#        try:
#            espec = EspecF4Modbus(DEFAULT_PORT, DEFAULT_ADDR, DEFAULT_TIMEOUT)
#            espec.test()
#        except (OSError,serial.serialutil.SerialException) as e:
#            print(i, e)
#            pass

    # single port
    DEFAULT_PORT = "/dev/ttyS0"
    DEFAULT_ADDR = 1
    DEFAULT_TIMEOUT = 1
    logging.getLogger().setLevel(logging.INFO)
    espec = EspecF4Modbus(DEFAULT_PORT, DEFAULT_ADDR, DEFAULT_TIMEOUT)
    espec.test()
    return(0)

## Main hook for running as script
if __name__ == "__main__":
    sys.exit(main())

