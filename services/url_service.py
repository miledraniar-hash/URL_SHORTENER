from utils.base62 import encode_base62

# 62**4 is the smallest integer whose Base62 representation needs 5 characters.
# Offsetting the row ID by this value guarantees a code of at least 5 chars,
# and at most 7 up to ~3.5 x 10^12 URLs.
OFFSET = 62 ** 4


def generate_short_code(id: int) -> str:
    """Encode the row ID as offset Base62.

    Base62 encoding is bijective, so two distinct IDs can never produce the
    same code: no collision is possible, unlike a truncated hash.
    """
    return encode_base62(id + OFFSET)
