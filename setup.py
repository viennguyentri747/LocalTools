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
    ],
    python_requires=">=3.6",
)