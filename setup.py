from setuptools import setup, find_packages

with open("README.md", "r") as f:
    long_description = f.read()

setup(
    name="himawaripy",
    version="3.0.0",
    url="http://labs.boramalper.org/himawaripy",
    author="Bora M. Alper, Jaerin Lee",
    author_email="bora@boramalper.org, jarin.lee@gmail.com",
    license="MIT",
    description="himawaripy is a Python 3 script that fetches near-realtime (10 minutes delayed) picture of Earth "
                "as its taken by Himawari 8 (ひまわり8号) and sets it as your desktop background.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    install_requires=["appdirs", "pillow", "python-dateutil", "numpy"],
    include_package_data=True,
    packages=find_packages(),
    entry_points={"console_scripts": ["himawaripy=himawaripy.__main__:main"]},
)
