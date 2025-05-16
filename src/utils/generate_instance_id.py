import hashlib
import os

def hash_string_sha1_salt(input_string: str, salt: str | None = None) -> str:
    """
    使用 SHA1 和盐值哈希字符串。

    参数:
        input_string: 要哈希的字符串。
        salt: 要使用的盐值。如果为 None，将生成一个随机盐值。

    返回:
        哈希后的字符串。
    """
    if salt is None:
        salt = os.urandom(16).hex()  # 生成一个16字节的随机盐值并转换为十六进制
    
    salted_string = salt + input_string
    hashed_string = hashlib.sha1(salted_string.encode('utf-8')).hexdigest()
    return f"{hashed_string}"

def generate_instance_id(instance_name: str) -> str:
    """
    为实例名称生成一个唯一的 ID (使用 SHA1 和随机盐值)。
    即使实例名称相同，由于使用了随机盐值，此函数也会生成不同的 ID。

    参数:
        instance_name: 实例的名称。

    返回:
        一个唯一的 ID 字符串。
    """
    return hash_string_sha1_salt(instance_name)

