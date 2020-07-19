from base64 import urlsafe_b64decode
from base64 import urlsafe_b64encode
from functools import wraps
from sys import argv

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


def serialize(b):
    return urlsafe_b64encode(b).decode("utf8")


def deserialize(s):
    return urlsafe_b64decode(s.encode("utf8"))


def aes_encrypt(key, data):
    cipher = AES.new(deserialize(key), AES.MODE_EAX)
    ciphertext, tag = cipher.encrypt_and_digest(data.encode("utf8"))
    return cipher.nonce, ciphertext, tag


@throwable("Incorrect key!")
def aes_decrypt(key, nonce, ciphertext, tag):
    cipher = AES.new(deserialize(key), AES.MODE_EAX, nonce=nonce)
    plaintext = cipher.decrypt(ciphertext).decode("utf8")
    cipher.verify(tag)
    return plaintext


def reset_secrets(new_username, new_password):
    for doc in ENCRYPTED_COLLECTION.stream():
        doc.reference.delete()
    new_key = serialize(get_random_bytes(32))
    username = aes_encrypt(new_key, new_username)
    password = aes_encrypt(new_key, new_password)
    ENCRYPTED_COLLECTION.document("credentials").set(
        {
            "username_nonce": username[0],
            "username": username[1],
            "username_tag": username[2],
            "password_nonce": password[0],
            "password": password[1],
            "password_tag": password[2],
        }
    )
    return new_key


def read_credentials(key):
    credentials = ENCRYPTED_COLLECTION.document("credentials").get().to_dict()
    return (
        aes_decrypt(
            key,
            credentials["username_nonce"],
            credentials["username"],
            credentials["username_tag"],
        ),
        aes_decrypt(
            key,
            credentials["password_nonce"],
            credentials["password"],
            credentials["password_tag"],
        ),
    )


if __name__ == "__main__":
    if "--reset-secrets" in argv:
        print(
            "This will clear all saved credentials and cards. To continue, fill out the following prompts."
        )
        secret_key = reset_secrets(
            input("Enter your Amazon username: "), input("Enter your Amazon password: ")
        )
        print(f'Your secret key is "{secret_key}".')
        print(
            "Keep this safe! If you forget this you will need to reset secrets again."
        )
    else:
        print(read_credentials(input("Enter key to retrieve credentials: ")))
