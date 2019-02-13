# chamber_control
Enviromental chamber monitoring and control

## Chamber serial ports

* 0 = /dev/ttyS0   ; rightmost, nearest computer
* 1 = /dev/ttyUSB3
* 2 = /dev/ttyUSB2 ; middle
* 3 = /dev/ttyUSB1
* 4 = /dev/ttyUSB0 ; leftmost, nearest door


## Running

### Logging in...
Fire up your favorite terminal program and log into the PC (IP ends with 120).  

Run `byobu` to create a persistant session or reconnect to an existing one.  Hit the F6 key to pull up a help screen if you need to.  Most useful keys are:
- F2 : create a new window
- F3 : switch to previous window
- F4 : switch to next window
- F6 : disconnect from session  
To close a window, just type `exit`.

All the programs are under `/home/ncm/chamber_control` so:  
`cd chamber_control`

### Monitor/log a chamber
```
./maildone.sh ./espec_logger.py -c loggerUSB0.cfg 
```
This will create a `chamber_USB0.log` file.  
There is already .cfg file for each chamber.  
This program keeps running and ouputting to the terminal, so run one per window (just create a new window with F2).

### Have a chamber follow the T & RH readings from an external sensor (a Pi with an SHT31 attached to it)
```
./maildone.sh './track_sensor.py -d /dev/ttyUSB0 -C "ssh root@10.200.59.13 /root/read_sht31.py out"' |& tee -a track_outdoor_repFOO.log
```
Replace the `/root/read_sht31.py out` with `/root/read_sht31.py in` to read the sensor in the medfly rearing room.  
Replace the last `track_outdoor_repFOO.log` with whatever logging filename you want to use.  
*note: The `read_sht31.py` script which runs on a Raspberry Pi is in the `pihvac` repository.*

### Run a profile (follow a list, possibly repeating, of T,RH,light settings)
Make the profile configuration file.  See `profile_tmp.cfg` for an example.

Running a profile is started with something like:  
`./run_profile.py -c profile_tmp.cfg`  
Of note, `run_profile.py` will pick up where it left off by default.  If you want to start over, say:  
`./run_profile.py --restart -c profile_tmp.cfg`  
that doesn't matter if you are using 'clocktime' (real time), but does if you are doing something like following a .csv file with historic weather data.


## Install

Runs using python3.  Requires miminalmodbus which can be installed via pip.


`track_sensor.py` will typically require putting your ssh key in `authorized_keys` on the remote pi to grab the readings.




## Misc

## ideas/todo
Detect "Chamber Run" switch beign off if possible

add silence alarm with timeout (reenable after time or return to normal range) to logger

## general todo
better monit monitoring (disk at least)
