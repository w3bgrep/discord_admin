import re

def is_valid_ethereum_address(address: str) -> bool:
    """Проверяет, является ли строка валидным Ethereum адресом"""
    # Проверяем формат: 0x + 40 шестнадцатеричных символов
    pattern = r'^0x[a-fA-F0-9]{40}$'
    return bool(re.match(pattern, address))