# JPEG LSB Steganography Tool

# Overview

This tool embeds a hidden message into a JPEG image using a technique called Least Significant Bit (LSB) Steganography. The process involves modifying the least significant bits of the image's Discrete Cosine Transform (DCT) coefficients to store the message without significantly altering the image's visual appearance.
How It Works

    Message Conversion: The input message is first converted into a binary format, where each character in the message is represented as an 8-bit binary string.

    DCT Coefficient Selection: The JPEG image is loaded, and its DCT coefficients are analyzed. Certain coefficients are selected for modification, specifically those that can be altered with minimal impact on the image quality. The coefficients with absolute values of 0 or 1, as well as DC coefficients, are excluded from this selection.

    Seed-Based Shuffling: A seed value is provided by the user, which is used to initialize a pseudorandom number generator. This generator shuffles the indices of the selected DCT coefficients. By shuffling these indices, the embedding positions are obfuscated, making it more difficult for an unintended observer to locate and extract the hidden message.

    Message Embedding: The binary bits of the message are embedded into the least significant bits of the shuffled DCT coefficients. This step subtly modifies the image, encoding the message within the image data.

    Image Saving: The modified image, containing the hidden message, is saved to a temporary file. The user is then provided with a link to download the image.

# The Role of the Seed

The seed value is crucial for the obfuscation process. It controls the pseudorandom shuffling of the DCT coefficient indices, ensuring that the message bits are embedded in unpredictable locations within the image. The same seed value must be used during the message extraction process to correctly reverse the shuffling and retrieve the embedded message. Without the correct seed, even if an observer suspects that a message is hidden within the image, they would have a much harder time extracting it.
Usage

#    Embedding and Hiding a Message:
        Upload a JPEG image using the file upload interface.
        Enter the message you want to embed in the image.
        Provide a numerical seed for shuffling the embedding locations.
        Click the "Embed Message" button to start the embedding process.
        Download the image with the embedded message using the provided link.

#    Extracting and Revealing a Message:
        To extract the message, use the same seed that was used for embedding. The extraction tool will reverse the shuffling and retrieve the hidden message from the image.

# Important Notes

    No Encryption: The message is not encrypted before embedding. For added security, consider encrypting the message before embedding it.
    Image Quality: The tool is designed to minimize the impact on image quality, but very large messages may still cause noticeable changes.
