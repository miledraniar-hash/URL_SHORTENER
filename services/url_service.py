import string
import hashlib

characters = string.ascii_letters + string.digits


def generate_short_code(id: int):

    # Convert ID to string
    value = str(id)

    # Hash the ID
    hash_value = hashlib.sha256(value.encode()).hexdigest()

    # Convert hexadecimal hash to integer
    number = int(hash_value, 16)

    # Base62 conversion
    code = ""

    while number > 0:
        number, remainder = divmod(number, 62)
        code = characters[remainder] + code

    # Keep exactly 6 characters
    return code[:6]