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
Higher Level interface to Thorlabs usb cameras and thorlabs piezo stage driver (KPZ101). 
This does not have the ablility to save images/videos or capture sequences of frames. 
It is a basic interface to control the camera and get an image from it.


.. moduleauthor:: Aaron M. Goldfain <agoldfain@seas.harvard.edu>
"""
import numpy as np
import os.path
import time

from ctypes import *



class CameraOpenError(Exception):
    def __init__(self, mesg):
        self.mesg = mesg
    def __str__(self):
        return self.mesg

class Camera(object):
    def __init__(self):
        uc480_file = 'C:\\Program Files\\Thorlabs\\Scientific Imaging\\ThorCam\\uc480_64.dll'
        piezo_dm_file = 'C:\\Program Files\\Thorlabs\\Kinesis\\Thorlabs.MotionControl.DeviceManager.dll'
        piezo_file = 'C:\\Program Files\\Thorlabs\\Kinesis\\Thorlabs.MotionControl.KCube.Piezo.dll'
        if os.path.isfile(uc480_file) and os.path.isfile(piezo_dm_file) and os.path.isfile(piezo_file):        
            self.bit_depth = None
            self.roi_shape = None
            self.camera = None
            self.handle = None
            self.meminfo = None
            self.exposure = None
            self.roi_pos = None
            self.frametime = None
            self.uc480 = windll.LoadLibrary(uc480_file)
            dm = windll.LoadLibrary(piezo_dm_file)
            self.piezo = windll.LoadLibrary(piezo_file)
        else:
            raise CameraOpenError("ThorCam and Focus Stabilization drivers not available.")

    def open(self, bit_depth=8, roi_shape=(1024, 1024), roi_pos=(0,0), camera="ThorCam FS", exposure = 0.01, frametime = 10.0):
        self.bit_depth = bit_depth
        self.roi_shape = roi_shape
        self.camera = camera
        self.roi_pos = roi_pos
        
        is_InitCamera = self.uc480.is_InitCamera
        is_InitCamera.argtypes = [POINTER(c_int)]
        self.handle = c_int(0)
        i = is_InitCamera(byref(self.handle))       

        if i == 0:
            print("ThorCam opened successfully.")
            pixelclock = c_uint(43) #set pixel clock to 43 MHz (fastest)
            is_PixelClock = self.uc480.is_PixelClock
            is_PixelClock.argtypes = [c_int, c_uint, POINTER(c_uint), c_uint]
            is_PixelClock(self.handle, 6 , byref(pixelclock), sizeof(pixelclock)) #6 for setting pixel clock
            
            self.uc480.is_SetColorMode(self.handle, 6) # 6 is for monochrome 8 bit. See uc480.h for definitions
            self.set_roi_shape(self.roi_shape)
            self.set_roi_pos(self.roi_pos)
            self.set_frametime(frametime)
            self.set_exposure(exposure)
        else:
            raise CameraOpenError("Opening the ThorCam failed with error code "+str(i))


    def close(self):
        if self.handle != None:
            self.stop_live_capture()
            i = self.uc480.is_ExitCamera(self.handle) 
            if i == 0:
                print("ThorCam closed successfully.")
            else:
                print("Closing ThorCam failed with error code "+str(i))
        else:
            return

    def get_image(self, buffer_number=None):
        #buffer number not yet used
        #if buffer_number is None:
        #    buffer_number = self.epix.pxd_capturedBuffer(1)

        im = np.frombuffer(self.meminfo[0], c_ubyte).reshape(self.roi_shape[1], self.roi_shape[0])

        
        return im

    def get_frame_number(self):
        #not implemented for thorcam_fs 
        #return self.epix.pxd_capturedBuffer(0x1,1)-1

       return 1

    def finished_live_sequence(self):
        #not implemented for thorcam_fs 
        #return self.epix.pxd_goneLive(0x1) == 0
        return 0

    def start_continuous_capture(self, buffersize = None):

        '''
        buffersize: number of frames to keep in rolling buffer
        '''

        self.uc480.is_CaptureVideo(self.handle, 1)

    def start_sequence_capture(self, n_frames):
        #not implemented for thorcam_fs 
        print 'sequence capture started'
        #self.epix.pxd_goLiveSeq(0x1,1,n_frames,1,n_frames,1)

    def stop_live_capture(self, ):
        print 'unlive now'
        #self.epix.pxd_goUnLive(0x1)
        self.uc480.is_StopLiveVideo(self.handle, 1)
        
    def initialize_memory(self):
        if self.meminfo != None:
            self.uc480.is_FreeImageMem(self.handle, self.meminfo[0], self.meminfo[1])
        
        xdim = self.roi_shape[0]
        ydim = self.roi_shape[1]
        imagesize = xdim*ydim
            
        memid = c_int(0)
        c_buf = (c_ubyte * imagesize)(0)
        self.uc480.is_SetAllocatedImageMem(self.handle, xdim, ydim, 8, c_buf, byref(memid))
        self.uc480.is_SetImageMem(self.handle, c_buf, memid)
        self.meminfo = [c_buf, memid]

        
    def set_bit_depth(self, set_bit_depth = 8):
         if set_bit_depth != 8:
            print("only 8-bit images supported")
    
    def set_roi_shape(self, set_roi_shape):
        class IS_SIZE_2D(Structure):
            _fields_ = [('s32Width', c_int), ('s32Height', c_int)]
        AOI_size = IS_SIZE_2D(set_roi_shape[0], set_roi_shape[1]) #Width and Height
            
        is_AOI = self.uc480.is_AOI
        is_AOI.argtypes = [c_int, c_uint, POINTER(IS_SIZE_2D), c_uint]
        i = is_AOI(self.handle, 5, byref(AOI_size), 8 )#5 for setting size, 3 for setting position
        is_AOI(self.handle, 6, byref(AOI_size), 8 )#6 for getting size, 4 for getting position
        self.roi_shape = [AOI_size.s32Width, AOI_size.s32Height]
        
        if i == 0:
            print("ThorCam ROI size set successfully.")
            self.initialize_memory()
        else:
            print("Set ThorCam ROI size failed with error code "+str(i))

    def set_roi_pos(self, set_roi_pos):
        class IS_POINT_2D(Structure):
            _fields_ = [('s32X', c_int), ('s32Y', c_int)]
        AOI_pos = IS_POINT_2D(set_roi_pos[0], set_roi_pos[1]) #Width and Height
            
        is_AOI = self.uc480.is_AOI
        is_AOI.argtypes = [c_int, c_uint, POINTER(IS_POINT_2D), c_uint]
        i = is_AOI(self.handle, 3, byref(AOI_pos), 8 )#5 for setting size, 3 for setting position
        is_AOI(self.handle, 4, byref(AOI_pos), 8 )#6 for getting size, 4 for getting position
        self.roi_pos = [AOI_pos.s32X, AOI_pos.s32Y]
        
        if i == 0:
            print("ThorCam ROI position set successfully.")
        else:
            print("Set ThorCam ROI size failed with error code "+str(i))
    
    def set_exposure(self, exposure):
        #exposure should be given in ms
        exposure_c = c_double(exposure)
        is_Exposure = self.uc480.is_Exposure
        is_Exposure.argtypes = [c_int, c_uint, POINTER(c_double), c_uint]
        is_Exposure(self.handle, 12 , exposure_c, 8) #12 is for setting exposure
        self.exposure = exposure_c.value
    
    def set_frametime(self, frametime):
        #must reset exposure after setting framerate
        #frametime should be givin in ms. Framerate = 1/frametime
        is_SetFrameRate = self.uc480.is_SetFrameRate 
        
        if frametime == 0: frametime = 0.001
        
        set_framerate = c_double(0)
        is_SetFrameRate.argtypes = [c_int, c_double, POINTER(c_double)]
        is_SetFrameRate(self.handle, 1.0/(frametime/1000.0), byref(set_framerate))
        self.frametime = (1.0/set_framerate.value*1000.0)
        
    def open_stage(self, serialNo, poll_time = 10, v_out = 0.0, v_step = 5.0 ):
        #poll_time for device is in ms    
        
        self.poll_time = poll_time 
        v_max = 750 # max voltage output (750 = 75.0 volts)
        prop_term = 100 #proportional feedback setting
        int_term = 15 #integral feedback setting
        loop_mode = 1 #closed loop = 2. open loop = 1.
        V_source = 2 #voltage source. 0 is software only. 1 is software and external. 2 is software and potentiometer, 3 is all three.
        input_source = 3 #feedback input source: 3 = external SMA
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
            self.piezo.PCC_SetVoltageSource(self.serialNo, V_source)
            self.piezo.PCC_SetHubAnalogInput(self.serialNo, input_source)
            self.piezo.PCC_SetMMIParams(self.serialNo, self.j_mode, self.j_rate, int(round(v_step/100.0*32767)), self.j_dir, int(round(self.v_set1/100.0*32767)), int(round(self.v_set2/100.0*32767)), self.dspI) 

            #enable voltage output
            self.piezo.PCC_Enable(self.serialNo)
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
        print 'Closing Stage'
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
        
