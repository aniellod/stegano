# MIT License
#
## Copyright (c) 2020 Daniel Lerch Hostalot. All rights reserved.
#
## Implementation for Automatic 1111
## Copyright (c) 2024 Aniello Di Meglio. All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a 
# copy of this software and associated documentation files (the "Software"), 
# to deal in the Software without restriction, including without limitation 
# the rights to use, copy, modify, merge, publish, distribute, sublicense, 
# and/or sell copies of the Software, and to permit persons to whom the 
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in 
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS 
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, 
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE 
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER 
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING 
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER 
# DEALINGS IN THE SOFTWARE.


# This implementation is based on the paper:
# Universal Distortion Function for Steganography in an Arbitrary Domain
# by Vojtěch Holub, Jessica Fridrich and Tomáš Denemark.

import os
import subprocess
import io
import gradio as gr
import random
import numpy as np
from PIL import Image, PngImagePlugin
import jpeg_toolbox as jt
from math import gcd

from modules import images, sd_samplers, scripts_postprocessing, shared, script_callbacks
from modules.ui_components import FormRow, ToolButton
from modules import paths_internal

postprocessing_callback = None
callback_registered = False

def text_to_bits(text):
    """Convert text to a binary list."""
    bit_list = []
    for char in text:
        bits = bin(ord(char))[2:].zfill(8)
        bit_list.extend([int(bit) for bit in bits])
    return bit_list

def bits_to_text(bits):
    """Convert a binary list to text."""
    chars = []
    for b in range(len(bits) // 8):
        byte = bits[b*8:(b+1)*8]
        byte_str = ''.join([str(bit) for bit in byte])
        chars.append(chr(int(byte_str, 2)))
    return ''.join(chars)

def jpeg_lsbr_hide(image_path, seed, message):
    """Embeds a hidden message in a JPEG image using J-UNIWARD."""
    # Convert the message to a binary list
    message += '\0'  # Add delimiter
    msg_bit_list = text_to_bits(message)

    # Load the JPEG image using jpeg_toolbox
    img = jt.load(image_path)

    dct = img["coef_arrays"][0]
    d1, d2 = dct.shape

    dct_copy = dct.copy()
    # Do not use 0 and 1 coefficients
    dct_copy[np.abs(dct_copy) == 1] = 0
    # Do not use the DC DCT coefficients
    dct_copy[::8, ::8] = 0
    # Flatten the array
    dct = dct.flatten()
    dct_copy = dct_copy.flatten()
    # Index of the DCT coefficients we can change
    idx = np.where(dct_copy != 0)[0]

    # Select a pseudorandom set of DCT coefficients to hide the message
    random.seed(int(seed))
    random.shuffle(idx)
    l = min(len(idx), len(msg_bit_list))
    idx = idx[:l]
    msg = np.array(msg_bit_list[:l])

    # LSB replacement:
    # Put LSBs to 0
    dct[idx] = np.sign(dct[idx]) * (np.abs(dct[idx]) - np.abs(dct[idx] % 2))
    # Add the value of the message
    dct[idx] = np.sign(dct[idx]) * (np.abs(dct[idx]) + msg)

    # Reshape and save DCTs
    dct = dct.reshape((d1, d2))
    img["coef_arrays"][0] = dct
    return img

def jpeg_lsbr_unhide(image,seed):
    """Extracts a hidden message from a JPEG image using LSB."""
    # Load the JPEG image using jpeg_toolbox
    img = jt.load(image)

    dct = img["coef_arrays"][0]
    d1, d2 = dct.shape

    dct_copy = dct.copy()
    # Do not use 0 and 1 coefficients
    dct_copy[np.abs(dct_copy) == 1] = 0
    # Do not use the DC DCT coefficients
    dct_copy[::8, ::8] = 0
    # Flatten the array
    dct = dct.flatten()
    dct_copy = dct_copy.flatten()
    # Index of the DCT coefficients we can change
    idx = np.where(dct_copy != 0)[0]

    # Select a pseudorandom set of DCT coefficients
    random.seed(int(seed))
    random.shuffle(idx)
    l = len(idx)

    # Read the message
    msg_bits = dct[idx] % 2
    message = bits_to_text(msg_bits.astype('uint8').tolist())
    return message.split('\0')[0]

# This portion of the code deal with the PNG format.
def get_pixel_order(width, height, seed):
    pixels = [(x, y) for x in range(width) for y in range(height)]
    random.seed(seed)
    random.shuffle(pixels)
    return pixels

def embed_message(image_path, message, seed):
    # Keep the metadata
    extra_meta = PngImagePlugin.PngInfo()
    extra_meta.add_text("parameters", message)

    img = Image.open(image_path)
    width, height = img.size
    
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    message += '\0'
    binary_message = ''.join(format(ord(char), '08b') for char in message)
    
    pixels = get_pixel_order(width, height, seed)
    
    data_index = 0
    for x, y in pixels:
        pixel = list(img.getpixel((x, y)))
        for color_channel in range(3):
            if data_index < len(binary_message):
                pixel[color_channel] = (pixel[color_channel] & 0xFE) | int(binary_message[data_index])
                data_index += 1
        img.putpixel((x, y), tuple(pixel))
        if data_index >= len(binary_message):
            break
    
    img.save(image_path, pnginfo=extra_meta)
    print("[stegano] Message embedded successfully.")

def extract_message(image_path, seed):
    img = Image.open(image_path)
    width, height = img.size
    
    pixels = get_pixel_order(width, height, seed)
    
    binary_message = ""
    extracted_message = ""
    for x, y in pixels:
        pixel = img.getpixel((x, y))
        for color_channel in range(3):
            binary_message += str(pixel[color_channel] & 1)
            if len(binary_message) == 8:
                char = chr(int(binary_message, 2))
                if char == '\0':
                    return extracted_message
                extracted_message += char
                binary_message = ""
    return extracted_message

def create_postprocessing_callback(message, enabled, seed, include_image_info):
    def my_postprocessing_callback(params):
        # print(f"[stegano] passed: message={message}, enabled={enabled}, seed={seed}, include={include_image_info}")
        if not enabled:
            return
        if not message and not include_image_info:
            print("[stegano] Message cannot be blank.")
            return
        # This function will be called after the image is saved
        pnginfo = getattr(params, 'pnginfo', None)
        geninfo = pnginfo.get('parameters', '')
        work_path = os.path.dirname(paths_internal.data_path)
        full_path = os.getcwd() + "/" + params.filename
        if params.filename.lower().endswith(('.jpg', '.jpeg')): 
            print(f"[stegano] Applied steganography to {params.filename}.")
            source = jt.load(full_path)
            message_orig = message + " " + geninfo
            stegano_image = jpeg_lsbr_hide(full_path, seed, message_orig)
            jt.save(stegano_image, full_path)
            jt.add_user_comment(full_path,geninfo)
            extracted_message = jpeg_lsbr_unhide(full_path, seed)
            if extracted_message == message_orig:
                print("[stegano] Verification successful. Embedded and extracted messages match.")
            else:
                print("[stegano] Verification failed. Embedded and extracted messages do not match.")
                print(f"[stegano] Original message: {message_orig}")
                print(f"[stegano] Extracted message: {extracted_message}")
        elif params.filename.lower().endswith('.png'):
            if message:
                message_orig = message + " " + geninfo
            else:
                message_orig = geninfo
            embed_message(full_path, message_orig, seed)
            extracted_message = extract_message(full_path, seed)
            if extracted_message == message_orig:
                print("[stegano] Verification successful. Embedded and extracted messages match.")
            else:
                print("[stegano] Verification failed. Embedded and extracted messages do not match.")
                print(f"[stegano] Original message: {message_orig}")
                print(f"[stegano] Extracted message: {extracted_message}")
            print(f"[stegano] Applied steganography to {params.filename}.")
        elif params.filename.lower().endswith('.webp'):
            print(f"[stegano] Processing WEBP is not yet supported")
        else:
            print(f"[stegano] Unsupported file type: {params.filename}")
    return my_postprocessing_callback

def register_callback_once(message, enabled, seed, include_image_info):
    global postprocessing_callback, callback_registered
    if enabled:
        if not callback_registered:
            postprocessing_callback = create_postprocessing_callback(message, enabled, seed, include_image_info)
            script_callbacks.on_image_saved(postprocessing_callback)
            callback_registered = True
    else:
        if callback_registered:
            script_callbacks.remove_callbacks_for_function(postprocessing_callback)
            callback_registered = False

class ScriptPostprocessingStegano(scripts_postprocessing.ScriptPostprocessing):
    name = "Steganographic content"
    order = 9999

    def ui(self):
        
        with gr.Group():
            with gr.Accordion(self.name, open=False, elem_id=id('accordion')):
                enabled = gr.Checkbox(label='Enabled', value=False)
                seed = gr.Number(label="Seed", value=0)
                include_image_info = gr.Checkbox(label='Include prompt and geninfo', value=True)
                message = gr.Textbox(label='Secret Message', value='', placeholder='Enter secret message here...')
                
        return {
            "enabled": enabled,
            "seed": seed,
            "include_image_info": include_image_info,
            "message": message
        }

    def process(self, pp: scripts_postprocessing.PostprocessedImage, message, enabled, seed, include_image_info):
        # print(f"Process called with enabled={enabled}")    
        register_callback_once(message, enabled, seed, include_image_info)
