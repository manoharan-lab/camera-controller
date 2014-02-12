#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright 2011-2013, Vinothan N. Manoharan, Thomas G. Dimiduk,
# Rebecca W. Perry, Jerome Fung, and Ryan McGorty, Anna Wang
#
# This file is part of HoloPy.
#
# HoloPy is free software: you can redistribute it and/or modify
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
from ctypes import c_ubyte, windll, sizeof
import numpy as np
import os.path

epix = windll.LoadLibrary("C:\Program Files\EPIX\XCLIB\XCLIBW64.dll")

def open_camera(formatfile=None):
    if formatfile is None:
        formatfile = os.path.join("formatFiles","PhotonFocus_8bit_1024x1024.fmt")
    #format file stored here: C:\Users\Public\Documents\EPIX
    i = epix.pxd_PIXCIopen("","",formatfile) #standard NTSC
    if i == 0:
        print("Frame grabber opened successfully.")
    elif i == -13:
        print("Frame grabber can't find format file.")
    elif i == -23:
        print("Frame grabber is already open.")
    else:
        print("Opening the frame grabber failed with error code "+str(i))
        #epix.pxd_mesgFault(1)

def close_camera():
    i = epix.pxd_PIXCIclose("","NTSC","") #standard NTSC #-25
    if i ==0:
        print("Frame grabber closed successfully.")
    elif i == -25:
        print("Failed to close the frame grabber because it wasn't open.")
    else:
        print("Closing the frame grabber failed with error code "+str(i))

def get_image():
    most_recent_buffer = epix.pxd_capturedBuffer(1)
    xdim = epix.pxd_imageXdim()
    ydim = epix.pxd_imageYdim()

    imagesize = xdim*ydim

    c_buf = (c_ubyte * imagesize)(0)
    c_buf_size = sizeof(c_buf)

    epix.pxd_readuchar(0x1,most_recent_buffer,0,0,-1,ydim, c_buf, c_buf_size, "Gray")
    return np.frombuffer(c_buf, c_ubyte).reshape([xdim, ydim])

def get_frame_number():
    return epix.pxd_capturedBuffer(1)-1

def finished_live_sequence():
    return epix.pxd_goneLive(1) == 0

def start_continuous_capture():
    # here we keep a buffer 1000 long and capture 1000000 image.
    # this is just a cludge to collect lots of images
    # TODO: can we make this infinite?
    epix.pxd_goLiveSeq(0x1,1,1000,1,1000000,1)


def start_sequence_capture(n_frames):
    epix.pxd_goLiveSeq(0x1,1,n_frames,1,n_frames,1)

def stop_live_capture():
    epix.pxd_goUnLive(0x1)

def frameToArray(bufnum):

    xdim = epix.pxd_imageXdim()
    ydim = epix.pxd_imageYdim()

    imagesize = xdim*ydim

    c_buf = (c_ubyte * imagesize)(0)
    c_buf_size = sizeof(c_buf)

    epix.pxd_readuchar(0x1,bufnum,0,0,-1,ydim, c_buf, c_buf_size, "Gray")

    im = np.frombuffer(c_buf, c_ubyte)
    im = im.reshape([xdim, ydim])

    return im

