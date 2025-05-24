import paramiko
import os
import json
import logging

# Configure logging
logging.basicConfig(
    filename='logs/transfer.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

CHUNKS = 10

def load_config(path="config/sftp_config.json"):
    with open(path, "r") as file:
        return json.load(file)

def connect_sftp(config):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if config["key_file"]:
        key = paramiko.RSAKey.from_private_key_file(config["key_file"])
        ssh.connect(config["host"], port=config["port"], username=config["username"], pkey=key)
    else:
        ssh.connect(config["host"], port=config["port"], username=config["username"], password=config["password"])
    return ssh.open_sftp()

def upload_file_in_chunks(local_path, remote_path):
    config = load_config()
    file_size = os.path.getsize(local_path)
    chunk_size = file_size // CHUNKS
    chunk_size_mb = chunk_size / (1024 ** 2)

    logging.info(f"Starting upload: '{local_path}' -> '{remote_path}'")
    logging.info(f"File Size: {file_size} bytes (~{file_size / (1024**3):.2f} GB), Chunk Size: {chunk_size} bytes (~{chunk_size_mb:.2f} MB)")

    try:
        sftp = connect_sftp(config)
        with open(local_path, 'rb') as f:
            with sftp.open(remote_path, 'wb') as remote_file:
                for i in range(CHUNKS):
                    chunk_data = f.read(chunk_size)
                    if not chunk_data:
                        break
                    remote_file.write(chunk_data)
                    remote_file.flush()
                    percent = ((i + 1) / CHUNKS) * 100
                    transferred = ((i + 1) * chunk_size) / (1024 ** 3)
                    print(f"{transferred:.2f} GB of {file_size / (1024 ** 3):.2f} GB transferred ({percent:.0f}%)")
                    logging.info(f"Chunk {i + 1}/{CHUNKS} uploaded ({percent:.0f}%)")

        sftp.close()
        logging.info("File upload completed successfully.")
        print("File upload completed successfully.")
    except Exception as e:
        logging.error(f"Upload failed: {e}")
        print(f"Upload failed: {e}")
