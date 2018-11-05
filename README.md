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

### track_sensor.py fails when there is a network glitch
### It also fails (same place) when the pi fails to read the sensor... also indicates a problem on the pi
ssh: connect to host 10.200.59.13 port 22: Network is unreachable
2018-08-04 10:04:51.853 INFO track_sensor: Read from sensor: ''
Traceback (most recent call last):
  File "./track_sensor.py", line 192, in <module>
  File "./track_sensor.py", line 140, in main
    T = round(float(foo[0]), 1)
IndexError: list index out of range


