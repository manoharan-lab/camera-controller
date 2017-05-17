#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright 2014, Thomas G. Dimiduk, Rebecca W. Perry, Aaron Goldfain
#
# This file is part of Camera Controller
#
# Camera Controller is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# HoloPy is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with HoloPy.  If not, see <http://www.gnu.org/licenses/>.
"""
Higher Level interface to thorlabs piezo stage driver (KPZ101). 



.. moduleauthor:: Aaron M. Goldfain <agoldfain@seas.harvard.edu>
"""
import numpy as np
import os.path
import time

from ctypes import *



class KPZ101OpenError(Exception):
    def __init__(self, mesg):
        self.mesg = mesg
    def __str__(self):
        return self.mesg

class KPZ101(object):
    def __init__(self):
        piezo_dm_file = 'C:\\Program Files\\Thorlabs\\Kinesis\\Thorlabs.MotionControl.DeviceManager.dll'
        piezo_file = 'C:\\Program Files\\Thorlabs\\Kinesis\\Thorlabs.MotionControl.KCube.Piezo.dll'
        if os.path.isfile(piezo_dm_file) and os.path.isfile(piezo_file):        
            dm = windll.LoadLibrary(piezo_dm_file)
            self.piezo = windll.LoadLibrary(piezo_file)
        else:
            raise CameraOpenError("Thorlabs KPZ101 drivers not available.")

    def open_stage(self, serialNo, poll_time = 10, v_out = 0.0, v_step = 5.0 ):
        #poll_time for device is in ms      
        self.poll_time = poll_time 
        v_max = 750 # max voltage output (750 = 75.0 volts)
        prop_term = 100 #proportional feedback setting
        int_term = 15 #integral feedback setting
        loop_mode = 1 #closed loop = 2. open loop = 1.
        V_source = 2 #voltage source. 0 is software only. 1 is software and external. 2 is software and potentiometer, 3 is all three.
        input_source = 3 #feedback input source: 1 = all hub bays, 2 = adjacent hub bays, 3 = external SMA
        self.j_mode = 2 #joystick mode: 1 = voltage adjust, 2 = jogging, 3 = set voltage
        self.j_rate = 1 #voltage adjust speed (1-3) = (slow-fast)
        self.j_dir = 1 #joystick direction sense
        self.v_set1 = 0.0 #voltage setting 1 as a percentage of the total voltage 
        self.v_set2 = 0.0 #voltage setting 2 as a percentage of the total voltage 
        self.dspI = 50 # display intensity (from 0 to 100)

        
               
        self.serialNo = str(serialNo)
        i = self.piezo.PCC_Open(self.serialNo) # returns 0 if it works
        
        if i == 0:
            print("Piezo Driver Opened Successfully")
            #configure stage
            self.piezo.PCC_StartPolling(self.serialNo, self.poll_time) #returns 1 if it works
            self.piezo.PCC_SetMaxOutputVoltage(self.serialNo, v_max)
            self.piezo.PCC_SetFeedbackLoopPIconsts(self.serialNo, prop_term, int_term)
            self.piezo.PCC_SetPositionControlMode(self.serialNo, loop_mode) #1 for open_loop, 2 for closed loop
            self.piezo.PCC_SetHubAnalogInput(self.serialNo, input_source)
            self.piezo.PCC_SetMMIParams(self.serialNo, self.j_mode, self.j_rate, int(round(v_step/100.0*32767)), self.j_dir, int(round(self.v_set1/100.0*32767)), int(round(self.v_set2/100.0*32767)), self.dspI) 
            #enable voltage output
            self.piezo.PCC_Enable(self.serialNo)
            time.sleep(.1)
            self.piezo.PCC_SetVoltageSource(self.serialNo, V_source)
            time.sleep(.1)
            #set stage voltages
            self.set_step_voltage(v_step)
            self.set_output_voltage(v_out)
            time.sleep(.1)
            self.get_output_voltage()
        else:
            print("Opening piezo driver failed with error code "+str(i))          
            self.stage_output_voltage = 0
            self.stage_set_voltage = 0
    
    def close_stage(self):
        print ('Closing stage with serial number ' + self.serialNo)
        self.set_output_voltage(0)
        time.sleep(2) 
        self.piezo.PCC_Disable(self.serialNo)
        self.piezo.PCC_StopPolling(self.serialNo)
        self.piezo.PCC_Disconnect(self.serialNo)
        self.piezo.PCC_Close(self.serialNo)
        self.stage_output_voltage = 0
    
    def set_output_voltage(self, v_out_set):
        #sets stage output voltage
        #v_out_set is a percentage (0-100) of the total output voltage
        if v_out_set > 100:
            v_out_set = 100
        if v_out_set < 0:
            v_out_set = 0
        self.piezo.PCC_SetOutputVoltage(self.serialNo, int(round(v_out_set/100.0*32767)) )

            
    def get_output_voltage(self):
        actual_v_out = self.piezo.PCC_GetOutputVoltage(self.serialNo)
        self.stage_output_voltage = 100.0*float(actual_v_out)/32767        
    
    def set_step_voltage(self, v_step_set, wait_for_update = True):
        #sets stage step voltage for one notch of the wheel
        #v_step_set is a percentage (0-100) of the total output voltage
        if v_step_set > 100:
            v_step_set = 100
        if v_step_set < 0:
            v_step_set = 0    
        
        self.piezo.PCC_SetMMIParams(self.serialNo, self.j_mode, self.j_rate, int(round(v_step_set/100.0*32767)), self.j_dir, int(round(self.v_set1/100.0*32767)), int(round(self.v_set2/100.0*32767)), self.dspI) 
        if wait_for_update: 
            time.sleep(.1) #wait for the device to update
        
            j_mode = c_short(0)
            j_rate = c_short(0)
            v_step = c_int32(0)
            j_dir = c_short(0)
            v_set1 = c_int32(0)
            v_set2 = c_int32(0)
            dspI = c_int16(0)
            self.piezo.PCC_GetMMIParams(self.serialNo, byref(j_mode), byref(j_rate), byref(v_step), byref(j_dir), byref(v_set1), byref(v_set2), byref(dspI)) 
            v_step_actual = 100.0*float(v_step.value)/32767
            
        self.stage_step_voltage = v_step_actual
        
