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
Higher Level interface to the epix framegrabber

.. moduleauthor:: Thomas G. Dimiduk <tom@dimiduk.net>
.. moduleauthor:: Rebecca W. Perry <perry.becca@gmail.com>
"""
from ctypes import c_ubyte, windll, sizeof, c_ushort
import numpy as np
import os.path

epix = windll.LoadLibrary("C:\Program Files\EPIX\XCLIB\XCLIBW64.dll")

class PhotonFocusCamera(object):
    def __init__(self):
        self.pixci_opened = False
        self.bit_depth = None
        self.roi_shape = None
        self.open()

    def open(self, bit_depth=12, roi_shape=(1024, 1024)):
        if self.pixci_opened:
            self.close()

        self.bit_depth = bit_depth
        self.roi_shape = roi_shape

        filename = "PhotonFocus_{0}bit_{1}x{2}.fmt".format(self.bit_depth,
                                                           *self.roi_shape)
        formatfile = os.path.join("formatFiles", filename)

        i = epix.pxd_PIXCIopen("","", formatfile) # standard NTSC
        if i == 0:
            print("Frame grabber opened successfully.")
            self.pixci_opened = True
        elif i == -13:
            print("Frame grabber can't find format file.")
        elif i == -23:
            print("Frame grabber is already open.")
        else:
            print("Opening the frame grabber failed with error code "+str(i))
            #epix.pxd_mesgFault(1)

    def close(self):
        if self.open:
            i = epix.pxd_PIXCIclose("","NTSC","") # standard NTSC #-25
            if i == 0:
                print("Frame grabber closed successfully.")
                self.open = True
            elif i == -25:
                print("Failed to close the frame grabber because it wasn't open.")
            else:
                print("Closing the frame grabber failed with error code "+str(i))
        else:
            return

    def get_image(self, buffer_number=None):
        if buffer_number is None:
            buffer_number = epix.pxd_capturedBuffer(1)
        # TODO: can we use the locally stored values for these? Or is
        # there some subtle way that will lead us astray?
        xdim = epix.pxd_imageXdim()
        ydim = epix.pxd_imageYdim()

        imagesize = xdim*ydim

        if self.bit_depth > 8:
            c_type = c_ushort
            cam_read = epix.pxd_readushort
        else:
            c_type = c_ubyte
            cam_read = epix.pxd_readuchar
        c_buf = (c_type * imagesize)(0)
        c_buf_size = sizeof(c_buf)

        cam_read(0x1, buffer_number, 0, 0, -1, ydim, c_buf,
                           c_buf_size, "Gray")
                           
        im = np.frombuffer(c_buf, c_type).reshape([xdim, ydim])
        if self.bit_depth > 8:
            # We have to return a 16 bit image, use the upper bits so that 
            # outputs look nicer (max pixel intensity will be interpreted as 
            # white by image viewers)
            im = im * 2**(16-self.bit_depth)

        return im

    def get_frame_number(self):
        return epix.pxd_capturedBuffer(1)-1

    def finished_live_sequence(self):
        return epix.pxd_goneLive(1) == 0

    def start_continuous_capture(self):
        # here we keep a buffer 1000 long and capture 1000000 image.
        # this is just a cludge to collect lots of images
        # TODO: can we make this infinite?
        epix.pxd_goLiveSeq(0x1,1,1000,1,1000000,1)


    def start_sequence_capture(self, n_frames):
        epix.pxd_goLiveSeq(0x1,1,n_frames,1,n_frames,1)

    def stop_live_capture(self, ):
        epix.pxd_goUnLive(0x1)
