# chamber_control
Enviromental chamber monitoring and control

## Chamber serial ports

* 0 = /dev/ttyS0   ; rightmost, nearest computer
* 1 = /dev/ttyUSB3
* 2 = /dev/ttyUSB2 ; middle
* 3 = /dev/ttyUSB1
* 4 = /dev/ttyUSB0 ; leftmost, nearest door

## notable changes
Tue Jul 17 15:19:51 HST 2018 : allow negative temperatures; ensure set values are in range for run_profile.py

## ideas/todo
Detect "Chamber Run" switch beign off if possible

add silence alarm with timeout (reenable after time or return to normal range) to logger

## general todo
better monit monitoring (disk at least)

## to FIX
track sensor misreads possible...
Should probably read multiple times and take median
