# chamber_control
Enviromental chamber monitoring and control

## Chamber serial ports

* 0 = /dev/ttyS0   ; rightmost, nearest computer
* 1 = /dev/ttyUSB3
* 2 = /dev/ttyUSB2 ; middle
* 3 = /dev/ttyUSB1
* 4 = /dev/ttyUSB0 ; leftmost, nearest door


## Running

### Have a chamber follow the T & RH readings from an external sensor (a Pi with an SHT31 attached to it)

```
./maildone.sh './track_sensor.py -d /dev/ttyUSB0 -C "ssh root@10.200.59.13 /root/read_sht31.py out"' |& tee -a track_outdoor_repFOO.log
```


## Install

Runs using python3.  Requires miminalmodbus which can be installed via pip.


`track_sensor.py` will typically require putting your ssh key in `authorized_keys` on the remote pi to grab the readings.




## Misc

## ideas/todo
Detect "Chamber Run" switch beign off if possible

add silence alarm with timeout (reenable after time or return to normal range) to logger

## general todo
better monit monitoring (disk at least)
