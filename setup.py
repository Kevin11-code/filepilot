from setuptools import setup, find_packages

setup(
    name="filepilot",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "paramiko>=2.7.0",
        "PyQt5>=5.15.0",
        "keyring>=21.0.0",
        "cryptography>=3.0"
    ],
    entry_points={
        "console_scripts": [
            "filepilot=filepilot.main:main",
        ],
    },
    author="FilePilot Team",
    author_email="admin@filepilot.example.com",
    description="Cross-platform SFTP client with GUI and CLI interfaces",
    keywords="sftp, file transfer, gui, cli",
    python_requires=">=3.7",
)