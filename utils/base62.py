import string
import random

BASE62 = string.digits + string.ascii_lowercase + string.ascii_uppercase

def generate_short_code(length=6):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def encode_base62(num: int) -> str:
    if num == 0:
        return BASE62[0]

    base62 = []
    base = len(BASE62)

    while num > 0:
        remainder = num % base
        base62.append(BASE62[remainder])
        num = num // base

    return ''.join(reversed(base62))