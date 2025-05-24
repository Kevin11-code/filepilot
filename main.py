import sys
from sftp_client import upload_file_in_chunks

if len(sys.argv) != 3:
    print("Usage: python main.py <local_file_path> <remote_file_path>")
    sys.exit(1)

local_path = sys.argv[1]
remote_path = sys.argv[2]

upload_file_in_chunks(local_path, remote_path)
