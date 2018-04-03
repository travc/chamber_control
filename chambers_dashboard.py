#!/usr/bin/env python3
import sys
import os
import random
import time
import numpy as np
import pandas as pd
import datetime

from bokeh.settings import settings as bokeh_settings
from bokeh.server.server import Server
from bokeh.application import Application
from bokeh.application.handlers.function import FunctionHandler
from bokeh.plotting import figure, ColumnDataSource
from bokeh.models import LinearAxis, Range1d, DataRange1d, DatetimeTickFormatter

import especmodbus

import logging
logging.basicConfig()
log = logging.getLogger()
log.setLevel(logging.INFO)

UPDATE_FREQ = 5 # seconds


def followFile(name):
    current = open(name, "r")
    curino = os.fstat(current.fileno()).st_ino
    while True:
        while True:
            line = current.readline()
            if not line:
                break
            yield line

        try:
            if os.stat(name).st_ino != curino:
                new = open(name, "r")
                current.close()
                current = new
                curino = os.fstat(current.fileno()).st_ino
                continue
        except IOError:
            pass
        time.sleep(1)

def check_for_new_data():
    pass

modbus_port = '/dev/ttyS0'
modbus_addr = 1
modbus_timeout = 0.5

def make_document(doc):
    espec = especmodbus.EspecF4Modbus(modbus_port, modbus_addr, modbus_timeout)
    #source = ColumnDataSource({ 'time':[],
                                #'T':[],
                                #'H':[],
                                #})
    stat = espec.getStat()
    print(stat, file=sys.stderr)
    for k,v in stat.items():
        stat[k] = [v]
    stat['time'] = [time.time()*1000]
    source_live = ColumnDataSource(stat)

    def update():
        stat = espec.updateStat()
        #new = {'time': [stat['time']],
               #'T': [stat['T']],
               #'H': [stat['H']],
              #}
        for k,v in stat.items():
            stat[k] = [v]
        stat['time'] = [time.time()*1000]
        #print(stat)
        source_live.stream(stat)

    doc.add_periodic_callback(update, UPDATE_FREQ*1000)
    #doc.add_next_tick_callback(check_for_new_data)

    fig = figure(title='Live plot test',
                x_axis_type="datetime",
                #x_range=[0, 1], y_range=[0, 1],
                plot_width=600,
                #sizing_mode='stretch_both',
                )

    tmp1 = fig.line(source=source_live, x='time', y='T', line_color='red')
    fig.y_range = DataRange1d(renderers=[tmp1])

    tmp2 = fig.line(source=source_live, x='time', y='H', line_color='blue', y_range_name="y_percent_axis")
    fig.extra_y_ranges = {"y_percent_axis": DataRange1d(renderers=[tmp2])}#start=0, end=100)}
    fig.add_layout(LinearAxis(y_range_name="y_percent_axis", axis_label="[%]"), 'right')

    #fig.circle(source=source, x='x', y='y', color='color', size=10)

    fig.xaxis.formatter = DatetimeTickFormatter(seconds=["%F\n%T"],
                                                minutes=["%F\n%T"],
                                                minsec=["%F\n%T"],
                                                hours=["%F\n%T"],
                                                hourmin=["%F\n%T"],
                                                days=["%F\n%T"],
                                                months=["%F\n%T"],
                                                years=["%F\n%T"])
    fig.xaxis.major_label_orientation = np.pi/2

    doc.title = "Chambers Dashboard"
    doc.add_root(fig)


apps = {'/cdb': Application(FunctionHandler(make_document))}
server = Server(apps, port=5006)
server.run_until_shutdown()

