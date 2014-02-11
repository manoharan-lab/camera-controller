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
Simulate capturing images from a camera for development

.. moduleauthor:: Thomas G. Dimiduk <tom@dimiduk.net>
"""
import numpy as np

live = True
lastimage = (np.random.random((1024,1024))*256).astype('int')
frame_number = 1
stop_frame = np.Inf

def open_camera(format=None):
    pass

def close_camera():
    pass

def get_image():
    global lastimage, live, frame_number, stop_frame
    if live and frame_number < stop_frame:
        lastimage = (np.random.random((1024,1024))*256).astype('uint8')
        frame_number += 1
    return lastimage

def get_frame_number():
    global frame_number
    return frame_number

def start_continuous_capture():
    global live, frame_number, stop_frame
    frame_number = 1
    live = True
    stop_frame = np.inf

def start_sequence_capture(n_frames):
    global live, frame_number, stop_frame
    frame_number = 1
    live = True
    stop_frame = n_frames+1

def stop_live_capture():
    global live
    live = False
