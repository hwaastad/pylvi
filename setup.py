import os
from setuptools import setup,find_packages

VERSION='0.1.0'
tag = os.getenv('BUILD_TAG')

long_description = None
with open("README.md", 'r') as fp:
    long_description = fp.read()

setup(
    name = 'lviheater',
    packages = find_packages(exclude=['tests']),
    install_requires=['aiohttp>=3.0.6','numpy'],
    version='0.1.0',
    description='A python3 library to communicate with LVI',
    long_description=long_description,
    python_requires='>=3.5.3',
    author='Helge Waastad',
    author_email='helge@waastad.org',
    url='https://x.x.x.x',
    license="MIT",
    classifiers=[
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Topic :: Home Automation',
        'Topic :: Software Development :: Libraries :: Python Modules'
        ],
    test_require=['nose']       
)