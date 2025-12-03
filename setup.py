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
        "readable-number==0.1.3",
        "gitingest==0.3.1",
        "prompt_toolkit==3.0.52",
        "thefuzz==0.22.1",
        "tabulate==0.9.0",
        "PyYAML==6.0.2",
        "pathvalidate==3.3.1",
        "matplotlib==3.10.6",
    ],
    extras_require={
        ':sys_platform == "win32"': [ #Install this on win by `pip install .[win32]`
            "windows-curses>=2.4.0",
        ],
    },
    python_requires=">=3.6",
)
