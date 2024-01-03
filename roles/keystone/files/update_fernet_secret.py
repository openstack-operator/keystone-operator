import os
import sys
import base64

from kubernetes import client, config


def update_secret(name, namespace, keys):

    config.load_incluster_config()

    v1 = client.CoreV1Api()

    secret = client.V1Secret()
    secret.metadata = client.V1ObjectMeta(name=name)
    secret.data = keys

    v1.replace_namespaced_secret(name, namespace, secret)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('usage: python3 update_fernet_secret.py <name> <namespace> [fernet_keys_dir]')
        sys.exit()

    name = sys.argv[1]
    namespace = sys.argv[2]

    try:
        fernet_keys_dir = sys.argv[3]
    except IndexError:
        fernet_keys_dir = "/etc/keystone/fernet-keys"

    files = os.listdir(fernet_keys_dir)
    keys = {}

    for file in files:
        key_path = os.path.join(fernet_keys_dir, file)

        with open(key_path, 'r', encoding='utf-8') as f:
            content = f.read()
            keys[file] = base64.b64encode(content.encode()).decode()

    update_secret(name, namespace, keys)
