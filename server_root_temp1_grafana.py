#!/usr/bin/env python
# coding: utf-8
# wittich
# run with python2

### this is a script that is run on the raspberry pie
### and reads out the room temperature
### then sends it to the grafana


from __future__ import print_function
import time
import re
import pickle
import struct
import socket
import RPi.GPIO as GPIO
import os,sys
import daemon
import pidfile

# settable parameters 
GRAPHITE_IP = '192.168.10.20'
GRAPHITE_PORT = 2003 # this is the pickle port
carbon_directory = "server-room.temp1" # this is the root directory for the graphite data
temp_sensor_ID = "28-3c01b5563c0c"
sleeptime=5
sleeptime_on_failure=30
starttime=time.time()

# set up connection to Graphite database 
def get_socket():
    try:
        sock = socket.socket()
        sock.connect((GRAPHITE_IP, GRAPHITE_PORT))
        return sock
    except Exception:
        return None

def setup_gpio_pins():
    # temp sensor using one-wire protocal
    # signal wire should be connected to gpio pin 4
    # and should configure internal pull up to avoid using a physical pull up resistor
    GPIO_PIN_NUMBER=4
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(GPIO_PIN_NUMBER, GPIO.IN, pull_up_down=GPIO.PUD_UP)


def timestamp_str():
    #return time.strftime("%Y%m%d_%H%M")
    return str(int(time.time()))

def print_with_time(message, fout=sys.stdout):
    fout.write("{} : {}\n".format(time.strftime("%Y%m%d_%H%M"), message))
    fout.flush()

def ds18b20_read_sensors():
    rtn = {}
    w1_devices = []
    w1_devices = os.listdir("/sys/bus/w1/devices/")
    for deviceid in w1_devices:
        rtn[deviceid] = {}
        rtn[deviceid]['temp_c'] = None
        device_data_file = "/sys/bus/w1/devices/" + deviceid + "/w1_slave"
        if os.path.isfile(device_data_file):
            try:
                f = open(device_data_file, "r")
                data = f.read()
                f.close()
                if "YES" in data:
                    (discard, sep, reading) = data.partition(' t=')
                    rtn[deviceid]['temp_c'] = float(reading) / float(1000.0)
                else:
                    rtn[deviceid]['error'] = 'No YES flag: bad data.'
            except Exception as e:
                rtn[deviceid]['error'] = 'Exception during file parsing: ' + str(e)
        else:
            rtn[deviceid]['error'] = 'w1_slave file not found.'
    return rtn;

def main():
    with open("server_root_temp1_grafana.log", "w") as fout:
        print_with_time("starting temperature logging...", fout)
        setup_gpio_pins()
        sock = None
        success_status = False
        while True:
            while not sock:
                print_with_time("connecting to socket...", fout)
                sock = get_socket()
                if not sock: time.sleep(10)
            temp_readings = ds18b20_read_sensors()
            if not temp_sensor_ID in temp_readings:
                print_with_time("Cannot find temperature sensor with ID={},".format(temp_sensor_ID), fout)
                print_with_time("\tPossible alternatives are:", fout)
                print_with_time("\t{}".format(temp_readings.keys()), fout)
                success_status = False
            elif 'error' in temp_readings[temp_sensor_ID]:
                print_with_time(temp_readings[temp_sensor_ID]['error'], fout)
                success_status = False
            else: 
                try:
                    value = temp_readings[temp_sensor_ID]['temp_c']
                    message = "{} {} {}\n".format(carbon_directory, value, timestamp_str())
                    sock.sendall(message)
                    if not success_status:
                        print_with_time("successfully sending message to Graphite...", fout)
                        success_status = True
                except Exception as e:
                    print_with_time("Unable to read and send temperature value:" + str(e), fout)
                    success_status = False
            if success_status:
                time.sleep(sleeptime- ((time.time()-starttime)%sleeptime))
            else:
                print_with_time("Will reconnect in {} seconds...".format(sleeptime_on_failure), fout)
                sock = None
                time.sleep(sleeptime_on_failure) #wait for more time in case of error

if __name__ == "__main__":
    with daemon.DaemonContext(working_directory="/home/pi/Temperature", pidfile=pidfile.PIDFile("/var/run/Temperature.pid")) as context:
        main()
