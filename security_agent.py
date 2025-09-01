# backend/security_agent/security_agent.py
import hashlib
import re
import logging
from typing import Tuple
from cryptography.fernet import Fernet


class SecurityAgent:
    def __init__(self) -> None:
        # Allowed users (username: hashed_password) — md5("admin") shown for demo only
        self.allowed_users = {"admin": "21232f297a57a5a743894a0e4a801fc3"}

        # Logging
        logging.basicConfig(
            filename="security.log",
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
        )

        # One-time symmetric key for demo (regenerated on each run)
        self.key = Fernet.generate_key()
        self.cipher = Fernet(self.key)

    # 1) Authentication
    def authenticate_user(self, username: str, password: str) -> bool:
        hashed_pw = hashlib.md5(password.encode()).hexdigest()
        if username in self.allowed_users and self.allowed_users[username] == hashed_pw:
            logging.info("User %s authenticated successfully.", username)
            return True
        logging.warning("Failed login attempt for user %s.", username)
        return False

    # 2) Input validation / block-list
    def validate_input(self, user_input: str) -> bool:
        bad_words = [
            "hack", "attack", "drop database", "delete", "shutdown",
            "poison", "make drug", "kill", "bomb"
        ]
        for w in bad_words:
            if w in (user_input or "").lower():
                logging.warning("Blocked harmful input: %s", user_input)
                return False
        return True

    # 3) Privacy masking (10-digit sequences)
    def mask_sensitive_data(self, text: str) -> str:
        return re.sub(r"\d{10}", "**********", text or "")

    # 4) Encrypt
    def encrypt_data(self, text: str) -> bytes:
        encrypted = self.cipher.encrypt((text or "").encode())
        logging.info("Data encrypted successfully.")
        return encrypted

    # 5) Decrypt
    def decrypt_data(self, encrypted_text: bytes) -> str:
        decrypted = self.cipher.decrypt(encrypted_text).decode()
        logging.info("Data decrypted successfully.")
        return decrypted

    # 6) Responsible-AI quick filter
    def responsible_ai_filter(self, user_input: str) -> Tuple[bool, str]:
        unsafe = [
            "suicide", "kill myself", "harm myself", "poison",
            "self medicate", "what medicine should i take",
            "overdose", "illegal drugs"
        ]
        low = (user_input or "").lower()
        for p in unsafe:
            if p in low:
                logging.error("Blocked unsafe health query: %s", user_input)
                return False, "⚠️ This question may be unsafe. Please consult a certified doctor or helpline."
        return True, user_input
