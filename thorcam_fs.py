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
Higher Level interface to Thorlabs usb cameras. This does not have the ablility to save images/videos or capture
sequences of frames. It is a basic interface to control the camera and get an image from it.

.. moduleauthor:: Aaron M. Goldfain <agoldfain@seas.harvard.edu>
"""
import numpy as np
import os.path

from ctypes import *



class CameraOpenError(Exception):
    def __init__(self, mesg):
        self.mesg = mesg
    def __str__(self):
        return self.mesg

class Camera(object):
    def __init__(self):
        self.bit_depth = None
        self.roi_shape = None
        self.camera = None
        self.handle = None
        self.meminfo = None
        self.uc480 = windll.LoadLibrary('C:\\Program Files\\Thorlabs\\Scientific Imaging\\ThorCam\\uc480_64.dll')
        self.exposure = None
        self.roi_pos = None

    def open(self, bit_depth=8, roi_shape=(1024, 1024), roi_pos=(0,0), camera=None, exposure = 0.01):
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
            pixelclock = c_uint(5) #set pixel clock to 5 MHz (slowest) to prevent frame dropping
            is_PixelClock = self.uc480.is_PixelClock
            is_PixelClock.argtypes = [c_int, c_uint, POINTER(c_uint), c_uint]
            is_PixelClock(self.handle, 6 , byref(pixelclock), sizeof(pixelclock)) #6 for setting pixel clock
            
            self.uc480.is_SetColorMode(self.handle, 6) # 6 is for monochrome 8 bit. See uc480.h for definitions
            self.set_roi_shape(self.roi_shape)
            print(self.roi_pos, '!!!!!!!!!!!!!!!!!!!!!!!!!!!!', roi_pos)
            self.set_roi_pos(self.roi_pos)
            self.set_exposure(exposure)
        else:
            raise CameraOpenError("Opening the ThorCam failed with error code "+str(i))


    def close(self):
        if self.handle != None:
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

        self.uc480.is_FreezeVideo(self.handle, 1) #1 means wait for capture to finish before continuing.
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

    def start_continuous_capture(self, buffersize):
                #not implemented for thorcam_fs 
        '''
        buffersize: number of frames to keep in rolling buffer
        '''
        # This appears to give an infinitely long live seqence, however it
        # looks like it may do it by continually overwriting the same image in
        # the buffer, so it probably will not work if we want a rolling buffer
        # tgd 2014-06-16
        # you can get the same effect by changing 1000000 to 0
        #self.epix.pxd_goLive(0x1,1)
        #self.epix.pxd_goLiveSeq(0x1,1,buffersize,1,1000000,1)

    def start_sequence_capture(self, n_frames):
        #not implemented for thorcam_fs 
        print 'sequence capture started'
        #self.epix.pxd_goLiveSeq(0x1,1,n_frames,1,n_frames,1)

    def stop_live_capture(self, ):
        #not implemented for thorcam_fs 
        print 'unlive now'
        #self.epix.pxd_goUnLive(0x1)
        
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
            print("ThorCam ROI set successfully.")
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
            print("ThorCam ROI set successfully.")
        else:
            print("Set ThorCam ROI size failed with error code "+str(i))
    
    def set_exposure(self, exposure):
        exposure_c = c_double(exposure)
        is_Exposure = self.uc480.is_Exposure
        is_Exposure.argtypes = [c_int, c_uint, POINTER(c_double), c_uint]
        is_Exposure(self.handle, 12 , exposure_c, 8) #12 is for setting exposure
        self.exposure = exposure_c.value
        
