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
'''Compress hdf5 files from the camera controllers raw dump format
into a single dataset

For speed, the camera writes out timeseries without compression and
with each image as an individual dataset in the file. This module is
then called in a seperate process to compress the data.

.. moduleauthor:: Thomas G. Dimiduk <tom@dimiduk.net>

'''

from __future__ import division
import h5py
import sys
import numpy as np
import os

def compress_h5(name, delete=False, progress=False):
    parts = name.split('.')
    if parts[-2] != 'uncompressed':
        print("file name should be of the form something.uncompressed.h5")
        return
    outname = '.'.join(parts[:-2] + parts[-1:])
    inf = h5py.File(name)
    shape2d = inf['1'].shape
    dtype = inf['1'].dtype
    n_frames = len(inf.keys())
    shape = shape2d + (n_frames,)
    chunk = min(n_frames, 100)

    outf = h5py.File(outname, 'w')
    outf.create_dataset('images', shape, chunks=(64, 64, chunk),
                        compression='gzip', dtype=dtype)

    buffer = np.zeros(shape2d+(chunk,), dtype=dtype)
    block = 0
    while (block+1)*chunk <= n_frames:
        for i in range(chunk):
            buffer[...,i] = inf[str(block*chunk+i)]
        outf['images'][...,block*chunk:(block+1)*chunk] = buffer
        block += 1
        if progress:
            print("{}%".format(block*chunk/n_frames * 100))

    # finish a partial chunk if the chunk size does not evenly divide n_frames
    if block*chunk < n_frames:
        partial = n_frames - block*chunk
        buffer = np.zeros(shape2d+(partial,), dtype=dtype)
        for i in range(partial):
            buffer[...,i] = inf[str(block*chunk+i)]
        outf['images'][...,block*chunk:] = buffer

    inf.close()
    if delete:
        os.remove(name)
    outf.close()

if __name__ == '__main__':
    name = sys.argv[1]
    compress_h5(name, progress=True)
