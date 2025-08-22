from setuptools import setup, find_packages

setup(
    name="local_tools",
    version="0.1.0",
    author="Unknown",
    description="Local tools for development",
    packages=find_packages(),
    install_requires=[
        "pyperclip==1.9.0",
        "python_gitlab==4.13.0",
        "plyer==2.1.0",
        "tiktoken==0.7.0",
        "readable-number==0.1.3"
    ],
    python_requires=">=3.6",
)