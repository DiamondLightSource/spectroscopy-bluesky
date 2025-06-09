import time
from gdascripts.utils import caget, caput

ionchamber2fill="I0"
targetPressureAr=35 #mbar
targetPressureHe=1800 #mbar


def pump_on():
    caput("BL20I-EA-GIR-01:VACP1:CON",0) # pump on

def pump_off():
    caput("BL20I-EA-GIR-01:VACP1:CON",1) # pump off

def purge_line():
    pump_on()
    caput("BL20I-EA-GIR-01:V5:CON",2) # reset line valve
    time.sleep(1)
    caput("BL20I-EA-GIR-01:V5:CON",0) # open line valve
    time.sleep(1)
    line_pressure=float(caget("BL20I-EA-GIR-01:PCTRL1:P:RD"))
    #loop to wait for pressure in the lines to get to base vacuum
    print 'purging the gas-supply line...'
    while line_pressure>8.5: #mbar
        time.sleep(1)
        line_pressure=float(caget("BL20I-EA-GIR-01:PCTRL1:P:RD"))
    caput("BL20I-EA-GIR-01:V5:CON",1) # close line valve
    pump_off()


def purge_I0():
    time.sleep(1)
    pump_on()
    time.sleep(1)
    caput("BL20I-EA-GIR-01:V5:CON",2) # reset line valve
    time.sleep(1)
    caput("BL20I-EA-GIR-01:V5:CON",0) # open line valve
    caput("BL20I-EA-GIR-01:V6:CON",2) # reset valve I0
    time.sleep(1)    
    caput("BL20I-EA-GIR-01:V6:CON",0) # open valve I0
    time.sleep(30)
    # logic check for leaks in the ionchamber
    base_pressure=float(caget("BL20I-EA-GIR-01:P2")) # record base pressure
    caput("BL20I-EA-GIR-01:V6:CON",1) # close valve I0
    print 'Checking the ionchamber',ionchamber2fill,'for leaks'
    time.sleep(10)
    check_pressure=float(caget("BL20I-EA-GIR-01:P2")) # record pressure after dwell
    if check_pressure-base_pressure >3:
        print "WARNING, suspected leak in", ionchamber2fill, "Stopping here!!!"
    caput("BL20I-EA-GIR-01:V6:CON",1) # close valve I0    
    time.sleep(1)
    caput("BL20I-EA-GIR-01:V5:CON",1) # close line valve
    time.sleep(1)
    pump_off()


def inject_argonIntoI0(targetPressureAr):
    caput("BL20I-EA-GIR-01:PCTRL1:SETPOINT:WR", targetPressureAr) # communicate Ar setpoint
    caput("BL20I-EA-GIR-01:V3:CON",2) # reset Ar supply valve
    time.sleep(1)
    caput("BL20I-EA-GIR-01:V3:CON",0) # open Ar supply valve
    time.sleep(1)
    caput("BL20I-EA-GIR-01:PCTRL1:MODE:WR",0) #set MFC to control
    time.sleep(1)    
    caput("BL20I-EA-GIR-01:V6:CON",2) # reset valve I0
    time.sleep(1)
    caput("BL20I-EA-GIR-01:V6:CON",0) # open valve I0
    time.sleep(10) # dwell time for pressure to equilibrate
    # close all valves
    caput("BL20I-EA-GIR-01:V6:CON",1) # close I0 valve
    time.sleep(1)
    caput("BL20I-EA-GIR-01:PCTRL1:MODE:WR",1) # put MFC1 on hold
    caput("BL20I-EA-GIR-01:V3:CON",1) # close Ar supply


def inject_heliumIntoI0(targetPressureHe):
    caput("BL20I-EA-GIR-01:PCTRL2:SETPOINT:WR",targetPressureHe)
    time.sleep(1)    
    caput("BL20I-EA-GIR-01:PCTRL2:MODE:WR",0) # set MFC2 to control
    caput("BL20I-EA-GIR-01:V6:CON",2) # reset valve I0
    time.sleep(1)
    caput("BL20I-EA-GIR-01:V6:CON",0) # open valve I0
    time.sleep(5) # do not modify this timing
    caput("BL20I-EA-GIR-01:V6:CON",1) # close valve I0
    time.sleep(1)
    caput("BL20I-EA-GIR-01:PCTRL2:MODE:WR",1) # set MFC2 to control
    


purge_line()
##purge_I0()
#inject_argonIntoI0(targetPressureAr)
#purge_line()
#inject_heliumIntoI0(targetPressureHe)
##print 'Script finished,',ionchamber2fill,'filled successfully!'
##print 'Live long and prosper!'


