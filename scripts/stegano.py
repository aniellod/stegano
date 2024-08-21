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

import gradio as gr
import sys
import random
import numpy as np
import jpeg_toolbox as jt
from PIL import Image, PngImagePlugin
import numpy as np
import tempfile

import modules.generation_parameters_copypaste as parameters_copypaste
from modules import devices, script_callbacks, shared

__version__ = "0.0.2"

ci = None
low_vram = False

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

def jpeg_lsbr_hide(image, seed, message):
    print(f"Image = {image.name}")
    """Embeds a hidden message in a JPEG image using LSB."""
    # Convert the message to a binary list
    message += '\0'  # Add delimiter
    msg_bit_list = text_to_bits(message)

    # Load the JPEG image using jpeg_toolbox
    img = jt.load(image.name)

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

    # Save the image to a temporary file
    temp_file = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    jt.save(img,temp_file.name)

    # Return the path to the temporary file for download
    return temp_file.name

def jpeg_lsbr_unhide(image,seed):
    """Extracts a hidden message from a JPEG image using LSB."""
    # Load the JPEG image using jpeg_toolbox
    img = jt.load(image.name)

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
    print("Message embedded successfully.")

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

def png_embed_message(image_path, message, seed):
    embed_message(image_path, message, seed)
    extracted_message = extract_message(image_path, seed)
    if extracted_message == message:
        print("Verification successful. Embedded and extracted messages match.")
    else:
        print("Verification failed. Embedded and extracted messages do not match.")
        print(f"Original message: {message}")
        print(f"Extracted message: {extracted_message}")
    print(f"Applied steganography to {image_path}.")

def png_extract_message(image_path, seed):
    extracted_message = extract_message(image_path, seed)
    return extracted_message

def image_analysis(image,seed):
    if image.name.lower().endswith(('.jpg', '.jpeg')): 
        return jpeg_lsbr_unhide(image,seed)
    elif image.name.lower().endswith(('.png')): 
        return png_extract_message(image,seed)
    else:
        print(f"Unsupported file type: {image.name}")

def encode_image(image,message,seed):
    if image.name.lower().endswith(('.jpg', '.jpeg')): 
        return jpeg_lsbr_hide(image,message,seed)
    elif image.name.lower().endswith(('.png')): 
        return png_embed_message(image,message,seed)
    else:
        print(f"Unsupported file type: {image.name}")
   
def stegano_decoded():
    return "Decoded message will appear here."

def format_license_for_gradio():
    license_text = """
JPEG Implementation
MIT License

Copyright (c) 2020 Daniel Lerch Hostalot. All rights reserved.

Implementation for Automatic 1111
Copyright (c) 2024 Aniello Di Meglio. All rights reserved.

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.


## Acknowledgements

This implementation is based on the paper:

* **Universal Distortion Function for Steganography in an Arbitrary Domain** by Vojtěch Holub, Jessica Fridrich and Tomáš Denemark.
"""
    return license_text

def read_me_for_gradio():
    read_me = """
Overview

This tool embeds a hidden message into a JPEG image using a technique called Least Significant Bit (LSB) Steganography. The process involves modifying the least significant bits of the image's Discrete Cosine Transform (DCT) coefficients to store the message without significantly altering the image's visual appearance.

How It Works

Message Conversion: The input message is first converted into a binary format, where each character in the message is represented as an 8-bit binary string.

DCT Coefficient Selection: The JPEG image is loaded, and its DCT coefficients are analyzed. Certain coefficients are selected for modification, specifically those that can be altered with minimal impact on the image quality. The coefficients with absolute values of 0 or 1, as well as DC coefficients, are excluded from this selection.

Seed-Based Shuffling: A seed value is provided by the user, which is used to initialize a pseudorandom number generator. This generator shuffles the indices of the selected DCT coefficients. By shuffling these indices, the embedding positions are obfuscated, making it more difficult for an unintended observer to locate and extract the hidden message.

Message Embedding: The binary bits of the message are embedded into the least significant bits of the shuffled DCT coefficients. This step subtly modifies the image, encoding the message within the image data.

Image Saving: The modified image, containing the hidden message, is saved to a temporary file. The user is then provided with a link to download the image.

The Role of the Seed

The seed value is crucial for the obfuscation process. It controls the pseudorandom shuffling of the DCT coefficient indices, ensuring that the message bits are embedded in unpredictable locations within the image. The same seed value must be used during the message extraction process to correctly reverse the shuffling and retrieve the embedded message. Without the correct seed, even if an observer suspects that a message is hidden within the image, they would have a much harder time extracting it.
Usage

    Embedding a Message:
        Upload a JPEG image using the file upload interface.
        Enter the message you want to embed in the image.
        Provide a numerical seed for shuffling the embedding locations.
        Click the "Embed Message" button to start the embedding process.
        Download the image with the embedded message using the provided link.

    Extracting a Message:
        To extract the message, use the same seed that was used for embedding. The extraction tool will reverse the shuffling and retrieve the hidden message from the image.

Important Notes

No Encryption: The message is not encrypted before embedding. For added security, consider encrypting the message before embedding it.
Image Quality: The tool is designed to minimize the impact on image quality, but very large messages may still cause noticeable changes.

"""
    return read_me

def process_file(file_obj):
    # Get the original file path
    file_path = file_obj.name
    print(f"Original file path: {file_path}")

    # You can also access the file contents using file_obj.file
    # For example, to display the image:
    return gr.Image(value=file_obj.name)

def about_tab():
    gr.Markdown("## 🕵️‍♂️ Stegano 🕵️‍♂️")
    gr.Markdown(format_license_for_gradio)
    gr.Markdown(read_me_for_gradio)

def read_stegano_tab():
    with gr.Column():
        with gr.Row():
            # image = gr.Textbox(label="Image Path")  # Using Textbox to accept image path
            image = gr.File(type="filepath", label="Image Path")
            decoded_message = gr.Textbox(label="Decoded Message")
            seed = gr.Number(label="Seed", value=0)
            button = gr.Button("Reveal", variant='primary')
            button.click(image_analysis, inputs=[image,seed], outputs=[decoded_message])

def write_stegano_tab():
    with gr.Column():
        with gr.Row():
            image = gr.File(type="filepath", label="Upload File")
            message = gr.Textbox(lines=5, placeholder="Enter the message to embed")
            seed = gr.Number(label="Seed", value=0)
            download_button = gr.File(label="Download Image with Embedded Message")
            button = gr.Button("Embed Message", variant='primary')
            
            # Trigger the embedding and provide a download link
            button.click(encode_image, inputs=[image, message, seed], outputs=download_button)

def add_tab():
    with gr.Blocks(analytics_enabled=False) as ui:
        with gr.Tab("Hide"):
            write_stegano_tab()
        with gr.Tab("Reveal"):
            read_stegano_tab()
        with gr.Tab("About"):
            about_tab()

    return [(ui, "Stegano", "stegano")]

script_callbacks.on_ui_tabs(add_tab)

