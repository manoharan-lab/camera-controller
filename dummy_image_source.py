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
Simulate capturing images from a camera for development

.. moduleauthor:: Thomas G. Dimiduk <tom@dimiduk.net>
"""
import numpy as np

live = True
lastimage = (np.random.random((1024,1024))*256).astype('int')
frame_number = 1
stop_frame = np.Inf

class DummyCamera(object):
    def __init__(self):
        self.bit_depth = None
        self.roi_shape = [1024,1024]
        self.live = True
        self.lastimage = None
        self.frame_number = 1
        self.stop_frame = np.Inf
        self.pixci_opened = True
        self.camera = None
        pass

    def open(self, bit_depth=12, roi_shape=([1024,1024]), roi_pos = (0,0), camera=None, exposure = 0, frametime = 0):
        self.bit_depth = bit_depth
        self.roi_shape = roi_shape
        self.camera = camera
        self.roi_pos = roi_pos
        self.exposure = exposure
        self.frametime = frametime
        
        pass

    def close(self):
        pass

    def get_image(self, buffer_number=None):
        # Note, ignores buffer number for now
        if self.bit_depth == 8:
            dtype = 'uint8'
        else:
            dtype = 'uint16'
        if self.live and self.frame_number < self.stop_frame:
            random = np.random.random(self.roi_shape)
            self.lastimage = (random * (2**16)).astype(dtype)

            self.frame_number += 1
        return self.lastimage

    def get_frame_number(self):
        return self.frame_number

    def start_continuous_capture(self, buffersize):
        self.frame_number = 1
        self.live = True
        self.stop_frame = np.inf

    def start_sequence_capture(self, n_frames):
        self.frame_number = 1
        self.live = True
        self.stop_frame = n_frames+1

    def stop_live_capture(self):
        self.live = False

    def finished_live_sequence(self):
        return self.frame_number >= self.stop_frame
        
    def set_roi_pos(self, set_roi_pos):
        #not yet implemented
        self.roi_pos = [0, 0]
    
    def set_exposure(self, exposure):
        #not yet implemented
        self.exposure = 0
    
    def set_frametime(self, frametime):
        #not yet implemented
        self.frametime = 0
