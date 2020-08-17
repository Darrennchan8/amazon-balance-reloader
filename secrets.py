from argparse import ArgumentParser
from base64 import urlsafe_b64decode
from base64 import urlsafe_b64encode
from functools import lru_cache
from functools import wraps
from json import dumps
from re import match

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from google.cloud import firestore

ENCRYPTED_COLLECTION = firestore.Client().collection("secrets")


class SecurityException(Exception):
    def __init__(self, message, exception):
        self.message = message
        self.exception = exception

    def __str__(self):
        return f"SecurityException: {self.message}\n{self.exception}"


def throwable(message):
    def throwable(f):
        @wraps(f)
        def wrapper(*args, **kwds):
            try:
                return f(*args, **kwds)
            except Exception as inst:
                raise SecurityException(message, inst)

        return wrapper

    return throwable


def gen_new_key():
    return urlsafe_b64encode(get_random_bytes(32)).decode("utf8")


def is_encrypted_data(data):
    return (
        isinstance(data, dict)
        and isinstance(data.get("nonce", None), bytes)
        and isinstance(data.get("value", None), bytes)
        and isinstance(data.get("tag", None), bytes)
    )


def aes_encrypt(key, data):
    cipher = AES.new(urlsafe_b64decode(key.encode("utf8")), AES.MODE_EAX)
    ciphertext, tag = cipher.encrypt_and_digest(data.encode("utf8"))
    return {"nonce": cipher.nonce, "value": ciphertext, "tag": tag}


@throwable("Incorrect key or invalid data!")
def aes_decrypt(key, data):
    cipher = AES.new(
        urlsafe_b64decode(key.encode("utf8")), AES.MODE_EAX, nonce=data["nonce"]
    )
    plaintext = cipher.decrypt(data["value"]).decode("utf8")
    cipher.verify(data["tag"])
    return plaintext


def get_document(key, document_name):
    def decrypt_recursive(d):
        return {
            k: aes_decrypt(key, v)
            if is_encrypted_data(v)
            else decrypt_recursive(v)
            if isinstance(v, dict)
            else v
            for (k, v) in (d or {}).items()
        }

    return decrypt_recursive(
        ENCRYPTED_COLLECTION.document(document_name).get().to_dict()
    )


def set_document(key, document_name, data):
    def encrypt_recursive(d):
        return {
            k: encrypt_recursive(v) if isinstance(v, dict) else aes_encrypt(key, v)
            for (k, v) in d.items()
        }

    ENCRYPTED_COLLECTION.document(document_name).set(encrypt_recursive(data))


def get_credentials(key):
    return get_document(key, "credentials")


@lru_cache
def get_card_names():
    return ENCRYPTED_COLLECTION.document("cards").get().to_dict().keys()


def get_cards(key):
    return get_document(key, "cards")


def reset_secrets(new_username, new_password):
    for doc in ENCRYPTED_COLLECTION.stream():
        doc.reference.delete()
    new_key = gen_new_key()
    set_document(
        new_key, "credentials", {"username": new_username, "password": new_password}
    )
    return new_key


def add_card(key, name, card):
    get_credentials(key)
    cards = get_document(key, "cards")
    if name in cards:
        raise ValueError(
            f'A card with the name "{name}" ==> {cards["name"]} already exists! Try deleting and re-adding the card!'
        )
    if not match(r"^\d{16}$", card):
        raise ValueError(f"Please specify a 16 digit card number!")
    set_document(key, "cards", {name: card, **cards})


if __name__ == "__main__":
    argparser = ArgumentParser(
        description="A utility library for managing encrypted db secrets.",
        allow_abbrev=False,
    )
    actions = argparser.add_mutually_exclusive_group(required=True)
    actions.add_argument(
        "--read", action="store_true", help="print json representation of saved secrets"
    )
    actions.add_argument(
        "--reset",
        action="store_true",
        help="reset all saved credentials and cards, generate a secret key",
    )
    actions.add_argument(
        "--add-cards", action="store_true", help="add cards to db secrets"
    )
    args = argparser.parse_args()
    if args.read:
        secret_key = input("Enter key to retrieve secrets: ")
        print(
            dumps(
                {
                    doc.id: get_document(secret_key, doc.id)
                    for doc in ENCRYPTED_COLLECTION.stream()
                }
            )
        )
    if args.reset:
        secret_key = reset_secrets(
            input("Enter your Amazon username: "), input("Enter your Amazon password: ")
        )
        print(f'Your secret key is "{secret_key}".')
        print(
            "Keep this safe! If you forget this you will need to reset secrets again."
        )
    if args.add_cards:
        secret_key = input("Enter your encryption key: ")
        get_credentials(secret_key)
        while True:
            try:
                add_card(
                    secret_key,
                    input("Enter a name for this card (press CTRL-D when finished): "),
                    input("Enter the full card number: "),
                )
            except EOFError:
                break
