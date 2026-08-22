from django.contrib.auth.hashers import PBKDF2PasswordHasher


class TTTFastPBKDF2PasswordHasher(PBKDF2PasswordHasher):
    iterations = 60000