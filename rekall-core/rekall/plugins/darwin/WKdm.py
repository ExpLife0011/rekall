# Rekall Memory Forensics
#
# Copyright 2014 Google Inc. All Rights Reserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or (at
# your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA
"""A WKdm decompressor.

This code is very closely based on the C implementation by

Paul Wilson -- wilson@cs.utexas.edu

and

Scott F. Kaplan -- sfkaplan@cs.utexas.edu

from September 1997.
"""
from __future__ import division

from builtins import next
from builtins import range
from past.utils import old_div
__author__ = "Andreas Moser <amoser@google.com>"

import itertools
import math
import struct
import time

DICTIONARY_SIZE = 16

TAGS_AREA_OFFSET = 4
TAGS_AREA_SIZE = 64

NUM_LOW_BITS = 10
LOW_BITS_MASK = 0x3FF

ZERO_TAG = 0x0
PARTIAL_TAG = 0x1
MISS_TAG = 0x2
EXACT_TAG = 0x3

# Set up the dictionary before performing compression or
# decompression.  Each element is loaded with some value, the
# high-bits version of that value, and a next pointer.

# these are the constants for the hash function lookup table.
# Only zero maps to zero.  The rest of the tabale is the result
# of appending 17 randomizations of 1 to 14. Generated by a Scheme
# script in hash.scm.

HASH_LOOKUP_TABLE_CONTENTS = [
   0, 13,  2, 14,  4,  3,  7,  5,  1,  9, 12,  6, 11, 10,  8, 15,
   2,  3,  7,  5,  1, 15,  4,  9,  6, 12, 11,  8, 13, 14, 10,  3,
   2, 12,  4, 13, 15,  7, 14,  8,  5,  6,  9, 10, 11,  1,  2, 10,
  15,  8,  5, 11,  1,  9, 13,  6,  4, 14, 12,  3,  7,  4,  2, 10,
   9,  7,  8,  3,  1, 11, 13,  5,  6, 12, 15, 14, 10, 12,  2,  8,
   7,  9,  1, 11,  5, 14, 15,  6, 13,  4,  3,  3,  1, 12,  5,  2,
   13,  4, 15,  6,  9, 11,  7, 14, 10,  8,  9,  5,  6, 15, 10, 11,
   13,  4,  8,  1, 12,  2,  7, 14,  3,  7,  8, 10, 13,  9,  4,  5,
   12,  2,  1, 15,  6, 14, 11,  3,  2,  9,  6,  7,  4, 15,  5, 14,
    8, 10, 12,  3,  1, 11, 13, 11, 10,  3, 14,  2,  9,  6, 15,  7,
   12,  1,  8,  5,  4, 13, 15,  3,  6,  9,  2,  1,  4, 14, 12, 11,
   10, 13,  8,  5,  7,  8,  3,  9,  7,  6, 14, 10,  4, 13, 11,  1,
    5, 15,  2, 12, 12, 13,  3,  5,  8, 11,  9,  7,  1, 10,  6,  2,
   14, 15,  4,  9,  8,  2, 10,  1, 13,  6, 11,  5,  3,  7, 12, 14,
    4, 15,  1, 13, 15, 12,  5,  4, 14, 11,  6,  2, 10,  3,  8,  7,
    9,  6,  8,  3,  1,  5,  4, 15,  9,  7,  2, 13, 10, 12, 11, 14
]

# /***********************************************************************
#  *                   THE PACKING ROUTINES
#  */

def WK_pack_2bits(source_buf):
    res = []
    it = zip(*([iter(source_buf)] * 16))
    for (in1, in2, in3, in4, in5, in6, in7, in8,
         in9, in10, in11, in12, in13, in14, in15, in16) in it:
        res.extend([
            in1 + (in5 << 2) + (in9  << 4) + (in13 << 6),
            in2 + (in6 << 2) + (in10 << 4) + (in14 << 6),
            in3 + (in7 << 2) + (in11 << 4) + (in15 << 6),
            in4 + (in8 << 2) + (in12 << 4) + (in16 << 6)
        ])

    return res


# /* WK_pack_4bits()
#  * Pack an even number of words holding 4-bit patterns in the low bits
#  * of each byte into half as many words.
#  * note: pad out the input with zeroes to an even number of words!
#  */

def WK_pack_4bits(source_buf):
    res = []
    it = zip(*([iter(source_buf)] * 8))
    for in1, in2, in3, in4, in5, in6, in7, in8 in it:
        res.extend([
            in1 + (in5 << 4),
            in2 + (in6 << 4),
            in3 + (in7 << 4),
            in4 + (in8 << 4)
        ])

    return res

# /* pack_3_tenbits()
#  * Pack a sequence of three ten bit items into one word.
#  * note: pad out the input with zeroes to an even number of words!
#  */

def WK_pack_3_tenbits(source_buf):

    packed_input = []
    for in1, in2, in3 in zip(*([iter(source_buf)] * 3)):
        packed_input.append(in1 | (in2 << 10) | (in3 << 20))

    return packed_input


# /***************************************************************************
#  *          THE UNPACKING ROUTINES should GO HERE
#  */


# /*  WK_unpack_2bits takes any number of words containing 16 two-bit values
#  *  and unpacks them into four times as many words containg those
#  *  two bit values as bytes (with the low two bits of each byte holding
#  *  the actual value.
#  */

and3_sh0 = []
and3_sh2 = []
and3_sh4 = []
and3_sh6 = []
and_f = []
sh4_and_f = []

for i in range(256):
    and3_sh0.append((i >> 0) & 3)
    and3_sh2.append((i >> 2) & 3)
    and3_sh4.append((i >> 4) & 3)
    and3_sh6.append((i >> 6) & 3)
    and_f.append(i & 0xf)
    sh4_and_f.append((i >> 4) & 0xf)

def WK_unpack_2bits(input_buf):

    output = []
    for in1, in2, in3, in4 in zip(*([iter(input_buf)] * 4)):
        output.extend([
            and3_sh0[in1], and3_sh0[in2], and3_sh0[in3], and3_sh0[in4],
            and3_sh2[in1], and3_sh2[in2], and3_sh2[in3], and3_sh2[in4],
            and3_sh4[in1], and3_sh4[in2], and3_sh4[in3], and3_sh4[in4],
            and3_sh6[in1], and3_sh6[in2], and3_sh6[in3], and3_sh6[in4]
        ])
    return output

# /* unpack four bits consumes any number of words (between input_buf
#  * and input_end) holding 8 4-bit values per word, and unpacks them
#  * into twice as many words, with each value in a separate byte.
#  * (The four-bit values occupy the low halves of the bytes in the
#  * result).
#  */

def WK_unpack_4bits(input_buf):
    output = []
    for in1, in2, in3, in4 in zip(*([iter(input_buf)] * 4)):
        output.extend([
            and_f[in1],
            and_f[in2],
            and_f[in3],
            and_f[in4],
            sh4_and_f[in1],
            sh4_and_f[in2],
            sh4_and_f[in3],
            sh4_and_f[in4]])

    return output

# /* unpack_3_tenbits unpacks three 10-bit items from (the low 30 bits of)
#  * a 32-bit word
#  */

def WK_unpack_3_tenbits(input_buf):
    output = []
    for in1, in2, in3, in4 in zip(*([iter(input_buf)] * 4)):
        output.extend([
            in1 & 0x3FF, (in1 >> 10) & 0x3FF, (in1 >> 20) & 0x3FF,
            in2 & 0x3FF, (in2 >> 10) & 0x3FF, (in2 >> 20) & 0x3FF,
            in3 & 0x3FF, (in3 >> 10) & 0x3FF, (in3 >> 20) & 0x3FF,
            in4 & 0x3FF, (in4 >> 10) & 0x3FF, (in4 >> 20) & 0x3FF
        ])

    return output

def WKdm_compress(src_buf):
    dictionary = []
    for _ in range(DICTIONARY_SIZE):
        dictionary.append((1, 0))
    hashLookupTable = HASH_LOOKUP_TABLE_CONTENTS

    tempTagsArray = []
    tempQPosArray = []

    # Holds words.
    tempLowBitsArray = []

    # Holds words.
    full_patterns = []

    input_words = struct.unpack("I" * (len(src_buf), 4) // src_buf)

    for input_word in input_words:

        # Equivalent to >> 10.
        input_high_bits = input_word // 1024
        dict_location = hashLookupTable[input_high_bits % 256]
        dict_word, dict_high = dictionary[dict_location]

        if (input_word == dict_word):
            tempTagsArray.append(EXACT_TAG)
            tempQPosArray.append(dict_location)
        elif (input_word == 0):
            tempTagsArray.append(ZERO_TAG)
        else:
            if input_high_bits == dict_high:
                tempTagsArray.append(PARTIAL_TAG)
                tempQPosArray.append(dict_location)
                tempLowBitsArray.append((input_word % 1024))
            else:
                tempTagsArray.append(MISS_TAG)
                full_patterns.append(input_word)

        dictionary[dict_location] = (input_word, input_high_bits)

    qpos_start = len(full_patterns) + TAGS_AREA_OFFSET + (len(src_buf) // 64)

    packed_tags = WK_pack_2bits(tempTagsArray)

    num_bytes_to_pack = len(tempQPosArray)
    num_packed_words = math.ceil(old_div(num_bytes_to_pack, 8.0))
    num_source_bytes = int(num_packed_words * 8)

    tempQPosArray += [0] * (num_source_bytes - len(tempQPosArray))

    packed_qp = WK_pack_4bits(tempQPosArray)

    low_start = qpos_start + int(num_packed_words)

    num_packed_words = old_div(len(tempLowBitsArray), 3)
    # Align to 3 tenbits.
    while len(tempLowBitsArray) % 3:
        tempLowBitsArray.append(0)

    packed_low = WK_pack_3_tenbits(tempLowBitsArray)

    low_end = low_start + len(packed_low)

    header = [0, qpos_start, low_start, low_end]

    return struct.pack(
        "IIII" + # header
        "B" * len(packed_tags) +
        "I" * len(full_patterns) +
        "B" * len(packed_qp) +
        "I" * len(packed_low),
        * (header + packed_tags + full_patterns + packed_qp + packed_low))

def WKdm_decompress_apple(src_buf):
    qpos_start, low_start, low_end = struct.unpack("III", src_buf[:12])

    return _WKdm_decompress(src_buf, qpos_start, low_start, low_end, 12)

def WKdm_decompress(src_buf):
    qpos_start, low_start, low_end = struct.unpack("III", src_buf[4:16])

    return _WKdm_decompress(src_buf, qpos_start, low_start, low_end, 16)

def _WKdm_decompress(src_buf, qpos_start, low_start, low_end, header_size):

    if max(qpos_start, low_start, low_end) > len(src_buf):
        return None

    if qpos_start > low_start or low_start > low_end:
        return None

    dictionary = [1] * DICTIONARY_SIZE
    hashLookupTable = HASH_LOOKUP_TABLE_CONTENTS

    tags_str = src_buf[header_size : header_size + 256]
    tags_array = WK_unpack_2bits(struct.unpack("B" * len(tags_str), tags_str))

    qpos_str = src_buf[qpos_start * 4:low_start * 4]
    tempQPosArray = WK_unpack_4bits(
        struct.unpack("B" * len(qpos_str), qpos_str))

    lowbits_str = src_buf[low_start * 4:low_end * 4]
    num_lowbits_bytes = len(lowbits_str)
    num_lowbits_words = old_div(num_lowbits_bytes, 4)
    num_packed_lowbits = num_lowbits_words * 3

    rem = len(lowbits_str) % 16
    if rem:
        lowbits_str += "\x00" * (16 - rem)

    packed_lowbits = struct.unpack("I" * (old_div(len(lowbits_str), 4)), lowbits_str)

    tempLowBitsArray = WK_unpack_3_tenbits(packed_lowbits)[:num_packed_lowbits]

    patterns_str = src_buf[256 + header_size:qpos_start * 4]
    full_patterns = struct.unpack("I" * (old_div(len(patterns_str), 4)), patterns_str)

    p_tempQPosArray = iter(tempQPosArray)
    p_tempLowBitsArray = iter(tempLowBitsArray)
    p_full_patterns = iter(full_patterns)

    output = []

    for tag in tags_array:

        if tag == ZERO_TAG:
            output.append(0)
        elif tag == EXACT_TAG:
            output.append(dictionary[next(p_tempQPosArray)])
        elif tag == PARTIAL_TAG:

            dict_idx = next(p_tempQPosArray)
            temp = ((old_div(dictionary[dict_idx], 1024)) * 1024)
            temp += next(p_tempLowBitsArray)

            dictionary[dict_idx] = temp
            output.append(temp)
        elif tag == MISS_TAG:
            missed_word = next(p_full_patterns)
            dict_idx = hashLookupTable[(old_div(missed_word, 1024)) % 256]
            dictionary[dict_idx] = missed_word
            output.append(missed_word)

    for p in [p_tempQPosArray, p_tempLowBitsArray, p_full_patterns]:
        for leftover in p:
            if leftover != 0:
                # Something went wrong, we have leftover data to decompress.
                return None

    return struct.pack("I" * len(output), *output)
