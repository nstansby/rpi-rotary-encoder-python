# Sample code to demonstrate Encoder class.  Prints the value every 5 seconds, and also whenever it changes.

import time
import RPi.GPIO as GPIO
from encoder import Encoder

def valueChanged(value, direction):
    print("* New value: {}, Direction: {}".format(value, direction))

GPIO.setmode(GPIO.BCM)

e1 = Encoder(26, 19, valueChanged)

try:
    while True:
        time.sleep(5)
        print("Value is {}".format(e1.getValue()))
except Exception:
    pass

GPIO.cleanup()